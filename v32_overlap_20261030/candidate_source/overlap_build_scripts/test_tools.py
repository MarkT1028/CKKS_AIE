"""Independent accounting/CLI corruption tests, fake files only, no XRT."""
from pathlib import Path
import hashlib,importlib.util,json,os,sys,tempfile
R=Path(__file__).resolve().parent;P=R/'board_files';W=R.parents[1];sys.path.insert(0,str(P))
import board_runner as runner
import summarize_results as summary
import summarize_campaign as campaign
import collect_results as collector
spec=importlib.util.spec_from_file_location('old_test_helpers',W/'integration/v32_bo_20261029/test_tools.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
put,csvfile=old.put,old.csvfile
def reject(fn):
    try:fn()
    except (ValueError,RuntimeError,KeyError,FileNotFoundError):return
    raise AssertionError('corrupt/unsafe case accepted')
def mock_hardware(path,mode):
    trace=[];iterations=[];candidate=mode=='map_finish_overlap'
    for rep in range(7):
        exporting=rep==6;spans=[];period=4. if candidate else 5.
        for i in range(16):
            cursor=0. if i==0 else 2+(i-1)*period+(1.2 if candidate else .2)
            def add(stage,lane,duration=.01):
                nonlocal cursor
                spans.append(dict(chunk=i,bank=i%2,stage=stage,lane=lane,begin=cursor,end=cursor+duration));cursor+=duration+.001
            for lane in (0,1):add('split',lane)
            for lane in (0,1):
                for stage in ('parameter_pack','parameter_write','input_sync','parameter_sync','output_poison','output_poison_sync'):add(stage,lane)
            cursor=2+i*period;add('execute',-1,3.);add('status',-1)
            cursor=(2+(i+1)*period+.02) if candidate and i<15 else cursor+.02
            add('merge_poison',-1)
            for lane in (0,1):add('output_sync',lane);add('merge',lane,.30)
            add('verify',-1,.10)
            if exporting:add('output_save',-1,.10)
        wall=max(x['end'] for x in spans)+.02;sums={k:sum(x['end']-x['begin'] for x in spans if x['stage']==k) for k in summary.STAGES}
        item=dict(repetition=rep,warmup=int(rep==0),export_only=int(exporting),chunks=16,replay_wall_ms=wall,execute_sum_ms=sums['execute'],stage_work_sum_ms=sum(sums.values()))
        item.update({k+'_sum_ms':sums[k] for k in summary.STAGES if k!='execute'});item.update({k+'_during_other_execute_ms':summary.overlap(spans,k) for k in ('split','input_sync')})
        item['finish_during_other_execute_ms']=sum(summary.overlap(spans,k) for k in ('merge_poison','output_sync','merge','verify'));item['verified_words']=summary.WORDS*16;iterations.append(item)
        trace.extend(dict(repetition=rep,warmup=int(rep==0),export_only=int(exporting),chunk=x['chunk'],bank=x['bank'],stage=x['stage'],lane=x['lane'],begin_ms=x['begin'],end_ms=x['end']) for x in spans)
    csvfile(path/'iterations.csv',iterations);csvfile(path/'timeline.csv',trace)
    put(path/'summary.json',dict(status='PASS_VERIFIED_BO_REPLAY',mode=mode,measured=5,warmups=1,chunks=16,export_replays=1,stage_sum_is_not_wall_time=True,firmware_changed=False,timing_protocol='v32_finish_overlap_v1',replay_wall_median_ms=iterations[1]['replay_wall_ms'],host_observed_execute_sum_median_ms=48.))
    put(path/'setup.json',dict(mode=mode,banks=2,input_bytes=896*1024**2,golden_bytes=42*1024**2));put(path.with_suffix('.command.json'),dict(exit_code=0))
    for i in range(16):q=path/f'outputs/chunk_{i}_output.bin';q.parent.mkdir(exist_ok=True);q.write_bytes(b'MOCK_ONLY'+bytes([i]))
def mock_result(root,camp='host',variant='v32_core_2_pipe',boot='boot_test',reverse=False):
    modes=list(summary.MODES) if camp=='host' else ['map_pingpong'];modes=modes[::-1] if reverse else modes
    put(root/'status.json',dict(status='PASS_OVERLAP_BOARD_COMPARISON'))
    put(root/'run_identity.json',dict(mode='formal',campaign=camp,variant=variant,boot_id=boot,boot_uuid=runner.VARIANTS[variant]['uuid'],base_manifest_sha256=runner.BASE_MANIFEST,order=modes))
    for name in ('environment_before.json','environment_after.json'):put(root/name,dict(boot_id=boot,boot_uuid=runner.VARIANTS[variant]['uuid']))
    for mode in modes:
        mock_hardware(root/mode/'hardware',mode)
        for stage in ('cpu2_before','cpu2_after'):old.mock_cpu(root/mode/stage)
    return root
def test_summary(root):
    result=mock_result(root/'results_overlap_host');facts=summary.summarize(result)
    assert facts['modes']['map_finish_overlap']['hardware']['medians_ms']['finish_during_other_execute_ms']>0
    for mode in summary.MODES:
        p=result/mode/'hardware/timeline.csv';original=p.read_text();rows=summary.rows(p)
        for fault in ('missing','duplicate','bank','negative','own_prep','reuse','concurrent_graph','status'):
            items=[dict(x) for x in rows]
            if fault=='missing':items.pop()
            elif fault=='duplicate':items.append(dict(items[0]))
            elif fault=='bank':items[0]['bank']=1
            elif fault=='negative':items[0]['end_ms']=-1
            elif fault=='own_prep':items[0]['end_ms']=99999
            elif fault=='reuse':next(x for x in items if x['chunk']=='2' and x['stage']=='split')['begin_ms']=0
            elif fault=='concurrent_graph':next(x for x in items if x['chunk']=='1' and x['stage']=='execute')['begin_ms']=float(next(x for x in items if x['chunk']=='0' and x['stage']=='execute')['end_ms'])-.10
            else:next(x for x in items if x['chunk']=='0' and x['stage']=='status')['end_ms']=float(next(x for x in items if x['chunk']=='1' and x['stage']=='execute')['begin_ms'])+.01
            csvfile(p,items);reject(lambda:summary.summarize(result));p.write_text(original)
        p=result/mode/'hardware/iterations.csv';original=p.read_text()
        for key in ('export_only','stage_work_sum_ms','finish_during_other_execute_ms'):
            items=summary.rows(p);items[-1 if key=='export_only' else 1][key]=0 if key=='export_only' else 99999;csvfile(p,items);reject(lambda:summary.summarize(result));p.write_text(original)
    p=result/'map_finish_overlap/hardware/outputs/chunk_15_output.bin';b=p.read_bytes();p.write_bytes(b'BAD');reject(lambda:summary.summarize(result));p.write_bytes(b)
    summary.summarize(mock_result(root/'results_overlap_reverse',reverse=True))
    summary.summarize(mock_result(root/'results_overlap_ablation',camp='ablation'))
    return result
def test_runner(root):
    package=root/'cli';base=root/'base';package.mkdir();base.mkdir();(package/'bin').mkdir()
    names=('ROOT','base','check','board','environment','command','Telemetry');saved={n:getattr(runner,n) for n in names};commands=[];affinity=os.sched_getaffinity(0)
    class Quiet:
        def __init__(self,*a):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
    try:
        current='v32_core_2_pipe';runner.ROOT=package;runner.base=lambda:base;runner.check=lambda:dict(manifest_sha256='mock');runner.board=lambda:None;runner.Telemetry=Quiet
        runner.environment=lambda:dict(boot_id='boot_test',boot_uuid=runner.VARIANTS[current]['uuid'],meminfo='MemAvailable: 3000000 kB\nCmaFree: 500000 kB\n');runner.command=lambda a,l:commands.append([str(x) for x in a])
        put(base/'fixture/capture_provenance.json',{});binaries={}
        for n in runner.BINARIES:p=package/'bin'/n;p.write_bytes(n.encode());binaries[n]=runner.records.sha(p)
        put(package/'bin/build_identity.json',dict(package_manifest_sha256='mock',binaries=binaries))
        for current in runner.VARIANTS:
            for kind in ('smoke','formal'):
                for reverse in (False,True):
                    for camp in ('host','ablation'):
                        commands.clear();runner.run(kind,current,reverse,camp);modes=list(summary.MODES) if camp=='host' else ['map_pingpong'];modes=modes[::-1] if reverse else modes
                        assert len(commands)==3*len(modes)+1
                        for i,mode in enumerate(modes):
                            before,hw,after=commands[i*3:i*3+3];assert hw[0].endswith('bo_host_'+current) and hw[-1]==mode
                            assert before[-4:]==after[-4:]==(['1','0','2','nosave'] if kind=='smoke' else ['3','1','2','nosave'])
                        assert commands[-1][1].endswith('summarize_results.py')
        commands.clear();current='v32_core_2_pipe';reject(lambda:runner.run('formal','v32_diag_2_pipe'));assert not commands
        (package/'bin/cached_cpu').write_bytes(b'tamper');reject(lambda:runner.run('formal',current));assert not commands
    finally:
        os.sched_setaffinity(0,affinity)
        for n,x in saved.items():setattr(runner,n,x)
def test_collect_campaign(root):
    package=root/'campaign';package.mkdir();base=root/'dep';(base/'fixture/chunks').mkdir(parents=True)
    for n in ('SHA256SUMS_PACKAGE','fixture/shape.json','fixture/chunks.tsv','fixture/capture_provenance.json'):p=base/n;p.write_text('{}\n')
    for v in runner.VARIANTS:mock_result(package/('results_overlap_ablation_'+v),camp='ablation',variant=v,boot='boot_'+v)
    q=next(package.glob('results_overlap_*'))/'map_pingpong/hardware/outputs'
    for p in q.glob('*'):(base/'fixture/chunks'/p.name.replace('_output','_expected')).write_bytes(p.read_bytes())
    for i in range(3):mock_result(package/('results_overlap_host_'+str(i)),boot='boot_core_'+str(i),reverse=bool(i%2))
    old_roots=campaign.R,collector.ROOT,runner.ROOT,runner.base
    try:
        campaign.R=package;collector.ROOT=package;runner.ROOT=package;runner.base=lambda:base
        campaign.main();facts=json.loads((package/'campaign_summary.json').read_text());assert facts['all_four_ablation_cells_present'] and len(facts['formal_boot_ids_by_variant']['v32_core_2_pipe'])==4
        archive=collector.collect();assert archive.is_file()
        p=q/'chunk_0_output.bin';p.write_bytes(b'BAD');reject(campaign.main)
        (q/'badlink').symlink_to(base/'SHA256SUMS_PACKAGE');reject(collector.collect)
    finally:campaign.R,collector.ROOT,runner.ROOT,runner.base=old_roots
def main():
    assert len(runner.VARIANTS)==4,'Need all four real image definitions before final tests'
    with tempfile.TemporaryDirectory(prefix='finish-overlap-tools-') as t:
        root=Path(t);test_summary(root);test_runner(root);test_collect_campaign(root);old.test_manifest(root)
    facts=dict(status='PASS_ISOLATED_OVERLAP_TOOLS',timeline_bounds_status_bank_lifetime_and_graph_order=True,baseline_vs_finish_overlap_accounting=True,CPU_unchanged_before_after=True,smoke_formal_forward_reverse_host_ablation_commands=True,export_separate_from_primary_samples=True,campaign_boots_and_modes_separate=True,all_four_ablation_cells_accounted=True,corruption_symlinks_and_binary_tampering_rejected=True,archive_index_hash_verified=True,PC_hardware_guard=True,board_tested=False,source_sha256={n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in ('board_runner.py','summarize_results.py','summarize_campaign.py','collect_results.py')})
    (R/'evidence/tools_test.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps(facts,indent=2))
if __name__=='__main__':main()
