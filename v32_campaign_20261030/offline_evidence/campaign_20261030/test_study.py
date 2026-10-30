"""Exercise the complete 11-step plan and faults using synthetic, non-XRT data."""
from pathlib import Path
import copy,fcntl,hashlib,importlib.util,json,os,sys,tarfile,tempfile,uuid
R=Path(__file__).resolve().parent;W=R.parents[1];P=R/'board_files';sys.path.insert(0,str(P))
import board_runner as runner
import summarize_results as s
import study_tools as t
import study as driver
import study_collect as collector
spec=importlib.util.spec_from_file_location('overlap_helpers',W/'integration/v32_overlap_20261029/test_tools.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
put=h.put
PKG_SHA=''
def reject(fn):
    try:fn()
    except (ValueError,RuntimeError,KeyError,FileNotFoundError,BlockingIOError):return
    raise AssertionError('unsafe/corrupt case accepted')
def boot(i):return str(uuid.uuid5(uuid.NAMESPACE_URL,'offline-synthetic-boot-'+str(i)))
def build():return dict(package_manifest_sha256=PKG_SHA,base_manifest_sha256=runner.BASE_MANIFEST,architecture='aarch64',flags='-O3 -std=c++17 -pthread; host additionally -I/usr/include/xrt -lxrt_coreutil',compiler='OFFLINE_FAKE_COMPILER_NOT_ARM_PERFORMANCE',binaries={n:'mock_'+n for n in runner.BINARIES})
def convert_smoke(folder):
    for mode in t.load(folder/'run_identity.json')['order']:
        hw=folder/mode/'hardware'
        for name in ('iterations.csv','timeline.csv'):
            rows=s.rows(hw/name);selected=[]
            for row in rows:
                if row['repetition'] in ('1','6'):
                    row['repetition']='0' if row['repetition']=='1' else '1';row['warmup']='0';selected.append(row)
            h.csvfile(hw/name,selected)
        data=t.load(hw/'summary.json');data.update(measured=1,warmups=0);put(hw/'summary.json',data)
        for name in ('cpu2_before','cpu2_after'):
            cpu=folder/mode/name
            for file in ('chunks.csv','iterations.csv'):
                rows=[dict(x,repetition=0,warmup=0) for x in s.rows(cpu/file) if x['repetition']=='1'];h.csvfile(cpu/file,rows)
            data=t.load(cpu/'summary.json');data.update(measured=1,warmups=0);put(cpu/'summary.json',data)
def make_attempt(root,step,ordinal,boot_id=None):
    attempt=root/'study_runs'/f'attempt_{ordinal:03}';attempt.mkdir(parents=True)
    ident=dict(schema=t.SCHEMA,attempt_id=attempt.name,step_id=step['id'],phase=step['phase'],variant=step['variant'],block=step['block'],protocol_sha256=hashlib.sha256((root/'STUDY_PROTOCOL.json').read_bytes()).hexdigest(),package_manifest_sha256=PKG_SHA,base_manifest_sha256=runner.BASE_MANIFEST,boot_id=boot_id or boot(ordinal),boot_uuid=runner.VARIANTS[step['variant']]['uuid'])
    put(attempt/'attempt_identity.json',ident);put(attempt/'build_identity.json',build());context={k:ident[k] for k in ('schema','attempt_id','step_id','phase','variant','block','protocol_sha256')};results=[]
    for i in range(3):
        folder=root/f'results_overlap_{step["phase"]}_{step["id"]}_{ordinal:03}_{i}';h.mock_result(folder,camp=step['phase'],variant=step['variant'],boot=ident['boot_id'],reverse=False if i==0 else step['formal_reverse_flags'][i-1]);rid=t.load(folder/'run_identity.json')
        rid.update(manifest_sha256=PKG_SHA,profiling=False,study_context=context,build_identity=build(),reverse_order=False if i==0 else step['formal_reverse_flags'][i-1]);put(folder/'run_identity.json',rid)
        for mode in rid['order']:
            file=folder/mode/'hardware/setup.json';data=t.load(file);data['setup_ms']=3.;put(file,data)
        if i==0:
            rid['mode']='smoke';put(folder/'run_identity.json',rid);convert_smoke(folder)
        s.summarize(folder)
        results.append(folder)
    diag=None
    if step['phase']=='host':
        diag=root/f'results_cpu_diag_{ordinal:03}';put(diag/'status.json',dict(status='PASS_CPU_DIAGNOSTIC',measured=12,all_formal_compute_samples_ms=[100.]*12,compute_first6_median_ms=100.,compute_last6_median_ms=100.,drift_percent=0.,review=False));put(diag/'identity.json',dict(diagnostic_only=True,perf_requested=False,boot_id=ident['boot_id'],cpu_sha256=build()['binaries']['cached_cpu'],manifest_sha256=PKG_SHA))
        for n in ('environment_before.json','environment_after.json'):put(diag/n,dict(boot_id=ident['boot_id']))
    index=t.seal(root,attempt,results,diag);put(attempt/'status.json',dict(status='PASS_BOARD_STEP_PENDING_CRYPTO',results=[x.name for x in results],diagnostic=diag.name if diag else None,sealed_index_sha256=index));return attempt,results
def reseal(attempt,results):
    status=t.load(attempt/'status.json');diag=attempt.parents[1]/status['diagnostic'] if status['diagnostic'] else None
    status['sealed_index_sha256']=t.seal(attempt.parents[1],attempt,results,diag);put(attempt/'status.json',status)
def rebind_boot(attempt,results,new_boot):
    ident=t.load(attempt/'attempt_identity.json');ident['boot_id']=new_boot;put(attempt/'attempt_identity.json',ident)
    for folder in results:
        for name in ('run_identity.json','environment_before.json','environment_after.json'):
            p=folder/name;d=t.load(p);d['boot_id']=new_boot;put(p,d)
    diag=t.load(attempt/'status.json')['diagnostic']
    if diag:
        for name in ('identity.json','environment_before.json','environment_after.json'):
            p=attempt.parents[1]/diag/name;d=t.load(p);d['boot_id']=new_boot;put(p,d)
    reseal(attempt,results)
def main():
    global PKG_SHA
    saved=(t.R,driver.R,collector.ROOT,runner.base,runner.records.sha,s.summarize);real_sha=runner.records.sha;real_summary=s.summarize
    checks=[]
    with tempfile.TemporaryDirectory(prefix='research-study-test-') as tmp:
        root=Path(tmp);base=root/'base';(base/'fixture/chunks').mkdir(parents=True);(root/'STUDY_PROTOCOL.json').write_bytes((P/'STUDY_PROTOCOL.json').read_bytes());(root/'SHA256SUMS_PACKAGE').write_text('fake manifest')
        for name in ('SHA256SUMS_PACKAGE','fixture/shape.json','fixture/chunks.tsv','fixture/capture_provenance.json'):q=base/name;q.parent.mkdir(exist_ok=True);q.write_text('{}\n')
        for i in range(16):(base/'fixture/chunks'/f'chunk_{i}_expected.bin').write_bytes(b'MOCK_ONLY'+bytes([i]))
        PKG_SHA=real_sha(root/'SHA256SUMS_PACKAGE')
        try:
            t.R=driver.R=collector.ROOT=root;runner.base=lambda:base
            p=t.protocol();assert t.summarize()['completed_steps']==0
            attempts=[]
            for i,step in enumerate(p['steps']):
                attempt,results=make_attempt(root,step,i+1);attempts.append((attempt,results));out=t.summarize();assert out['completed_steps']==i+1
                if i<10:assert out['next_step']['id']==p['steps'][i+1]['id']
                else:assert out['next_step'] is None
            out=t.summarize();assert out['host_repeatability']['completed'] and out['all_four_variants_in_both_ablation_blocks'] and all(x['complete'] for x in out['ablation_blocks'])
            assert out['ablation_blocks'][0]['additive_wall_interaction_ms']==0;assert out['crypto_return']=='PENDING_ACTUAL_BOARD_OUTPUTS';checks.append('all_11_steps_with_distinct_boots_and_two_reverse_ablation_blocks')
            tracked=attempts[0][1][1]/'comparison.json';before=tracked.read_bytes();t.summarize();assert tracked.read_bytes()==before;checks.append('status_does_not_rewrite_raw_run_comparisons')
            # A repeated Linux boot cannot be counted as independent, even after a
            # valid reseal. A changed CPU/build or run context is also rejected.
            a,results=attempts[1];rebind_boot(a,results,boot(1));t.validate_attempt(a,p['steps'][1],p);reject(t.summarize);rebind_boot(a,results,boot(2))
            # Individually consistent and freshly sealed builds must still not mix
            # different CPU binaries across study steps.
            a,results=attempts[-1];paths=[a/'build_identity.json',*[x/'run_identity.json' for x in results]];before={q:q.read_bytes() for q in paths}
            for q in paths:
                data=t.load(q);b=data if q.name=='build_identity.json' else data['build_identity'];b['binaries']['cached_cpu']='different_CPU';put(q,data)
            reseal(a,results);t.validate_attempt(a,p['steps'][-1],p);reject(t.summarize)
            for q,data in before.items():q.write_bytes(data)
            reseal(a,results)
            file=attempts[0][1][1]/'map_pingpong/hardware/outputs/chunk_0_output.bin';old=file.read_bytes();file.write_bytes(b'corruption');reject(t.summarize);file.write_bytes(old)
            checks.append('boot_build_context_and_output_integrity_rejections')
            # Incomplete attempts remain visible and do not acquire a progress slot.
            failed=root/'study_runs/attempt_999';put(failed/'attempt_identity.json',dict(step_id='H01',phase='host',block=0));put(failed/'status.json',dict(status='FAILED_OR_INTERRUPTED',results=[],error='synthetic interruption'))
            assert t.summarize()['review_required'] and len(t.summarize()['failed_attempts'])==1;checks.append('failed_attempts_retained_not_counted_as_success')
            # Incremental collection includes nested offline evidence and only the
            # requested phase/block. Every compressed member is rehashed.
            put(root/'offline_evidence/nested/routed.json',dict(mock=True));archive=collector.collect('ablation',1)
            with tarfile.open(archive) as tar:
                names=tar.getnames();assert 'offline_evidence/nested/routed.json' in names
                assert any('A01' in n for n in names) and not any('results_overlap_host_' in n for n in names) and not any('A08' in n for n in names)
            checks.append('phase_block_gzip_index_sha_nested_evidence_and_failure_retention')
            link=root/'offline_evidence/badlink';link.symlink_to(root/'SHA256SUMS_PACKAGE');reject(lambda:collector.collect('host'));link.unlink()
            checks.append('unsafe_symlink_collection_rejected')
            # Reentrant device locking retains the one cross-package lock, and an
            # independent open file description cannot take it during any stage.
            with runner.device_lock():
                with runner.device_lock():
                    with (base/'.board.lock').open('a') as held:reject(lambda:fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB))
            assert runner._DEVICE_LOCK is None;checks.append('whole_step_cross_package_device_lock_reentrancy_and_release')
            duplicate,_=make_attempt(root,p['steps'][0],1000);t.validate_attempt(duplicate,p['steps'][0],p);reject(t.summarize);checks.append('duplicate_success_rejected_without_fastest_sample_selection')
            # Logical progress must remain correct if board UTC/file timestamps go
            # backwards across boots. IDs deliberately sort in the opposite order.
            clock=root/'clock_rollback';clock.mkdir();(clock/'SHA256SUMS_PACKAGE').write_text('fake manifest');(clock/'STUDY_PROTOCOL.json').write_bytes((P/'STUDY_PROTOCOL.json').read_bytes());t.R=driver.R=collector.ROOT=clock
            for step,ordinal in zip(p['steps'][:3],(303,202,101)):make_attempt(clock,step,ordinal)
            out=t.summarize();assert [x['step_id'] for x in out['steps']]==['H01','H02','H03'];checks.append('UTC_clock_rollback_does_not_reorder_independent_boots')
        finally:t.R,driver.R,collector.ROOT,runner.base,runner.records.sha,s.summarize=saved
    facts=dict(status='PASS_SYNTHETIC_STUDY_PROTOCOL_AND_FAULT_TESTS',checks=checks,synthetic_data_only=True,hardware_executed=False,board_performance='PENDING')
    (R/'evidence/study_test.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps(facts,indent=2))
if __name__=='__main__':main()
