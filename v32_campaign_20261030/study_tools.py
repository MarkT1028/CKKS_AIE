"""Frozen protocol and append-only attempt accounting; no XRT or boot writes."""
from pathlib import Path
import json,math,os,statistics,uuid
import board_runner as r
import summarize_results as s
R=Path(__file__).resolve().parent
CORE='v32_core_2_pipe';DIAG='v32_diag_2_pipe';AIE='v32_aie_only_2_pipe';RED='v32_reducer_only_2_pipe'
SCHEMA='v32_research_campaign_v1'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def safe(root,name):
    need(isinstance(name,str) and name,'unsafe study path');p=Path(name);need(not p.is_absolute() and '\\' not in name and ':' not in name and all(x not in ('.','..') for x in p.parts),'unsafe study path')
    q=root/p;need(q.resolve().is_relative_to(root.resolve()) and not any(x.is_symlink() for x in (q,*q.parents)),'unsafe study symlink/path');return q
def protocol():
    p=load(R/'STUDY_PROTOCOL.json');need(p['schema']==SCHEMA,'protocol schema')
    expected=[('H01','host',CORE,0),('H02','host',CORE,0),('H03','host',CORE,0),*[(f'A{i+1:02}','ablation',v,1 if i<4 else 2) for i,v in enumerate((CORE,AIE,RED,DIAG,DIAG,RED,AIE,CORE))]]
    need([(x['id'],x['phase'],x['variant'],x['block']) for x in p['steps']]==expected,'wrong frozen study sequence')
    need(p['formal_hardware_repetitions_per_run']==5 and p['formal_runs_per_step']==2 and p['hardware_warmups_per_formal']==1 and p['cpu_repetitions_per_adjacent_stage']==3 and p['cpu_threads']==2,'protocol counts changed')
    need(p['host_target_independent_boots']==3 and p['ablation_mode']=='map_pingpong','protocol controls changed')
    for step in p['steps']:
        need(step['formal_reverse_flags']==([True,False] if step['id']=='H02' else [False,True]),'formal counterbalancing flags')
    return p
def signature(build):
    need(build['architecture']=='aarch64' and build['flags']=='-O3 -std=c++17 -pthread; host additionally -I/usr/include/xrt -lxrt_coreutil','compiler target/flags differ')
    need(set(build['binaries'])==set(r.BINARIES),'binary inventory')
    return dict(compiler=build['compiler'],flags=build['flags'],architecture=build['architecture'],binaries=build['binaries'])
def seal(root,attempt,result_dirs,diagnostic):
    entries={};paths=[attempt/'attempt_identity.json',attempt/'build_identity.json']
    for directory in [*result_dirs,*([diagnostic] if diagnostic else [])]:
        need(directory.is_dir() and directory.resolve().is_relative_to(root.resolve()),'invalid attempt result dir')
        paths+=list(directory.rglob('*'))
    for path in paths:
        need(not path.is_symlink(),'unsafe sealed result symlink')
        if path.is_file():
            name=path.relative_to(root).as_posix();safe(root,name);entries[name]=dict(bytes=path.stat().st_size,sha256=r.records.sha(path))
        else:need(path.is_dir(),'nonregular result member')
    r.write(attempt/'sealed_index.json',entries)
    return r.records.sha(attempt/'sealed_index.json')
def verify_seal(attempt,status):
    index=attempt/'sealed_index.json';need(r.records.sha(index)==status['sealed_index_sha256'],'sealed index changed')
    data=load(index);need(data,'empty result seal')
    for name,row in data.items():
        p=safe(R,name);need(p.is_file() and p.stat().st_size==row['bytes'] and r.records.sha(p)==row['sha256'],'sealed study file changed: '+name)
    return data
def validate_attempt(attempt,step,p):
    identity=load(attempt/'attempt_identity.json');status=load(attempt/'status.json')
    need(status['status']=='PASS_BOARD_STEP_PENDING_CRYPTO','incomplete study attempt')
    index=verify_seal(attempt,status)
    need(identity['schema']==SCHEMA and identity['attempt_id']==attempt.name and identity['step_id']==step['id'] and identity['phase']==step['phase'] and identity['variant']==step['variant'] and identity['block']==step['block'],'attempt enrollment mismatch')
    need(identity['protocol_sha256']==r.records.sha(R/'STUDY_PROTOCOL.json') and identity['package_manifest_sha256']==r.records.sha(R/'SHA256SUMS_PACKAGE') and identity['base_manifest_sha256']==r.BASE_MANIFEST,'attempt package/protocol/dependency mismatch')
    boot=identity['boot_id'];need(str(uuid.UUID(boot))==boot,'invalid Linux boot id')
    need(identity['boot_uuid']==r.VARIANTS[step['variant']]['uuid'],'attempt firmware UUID')
    build=load(attempt/'build_identity.json');sig=signature(build)
    need(build['package_manifest_sha256']==identity['package_manifest_sha256'] and build['base_manifest_sha256']==r.BASE_MANIFEST,'attempt build package identity')
    refs=status['results'];need(len(refs)==3 and len(set(refs))==3,'expected smoke and two formal result folders')
    expected_context={k:identity[k] for k in ('schema','attempt_id','step_id','phase','variant','block','protocol_sha256')}
    result=[];referenced={attempt.relative_to(R).as_posix()+'/attempt_identity.json',attempt.relative_to(R).as_posix()+'/build_identity.json'}
    for i,name in enumerate(refs):
        need(name.startswith('results_overlap_') and '/' not in name,'result must be a top-level runner folder')
        folder=safe(R,name);rid=load(folder/'run_identity.json');before=load(folder/'environment_before.json');after=load(folder/'environment_after.json')
        need(rid['study_context']==expected_context,'result belongs to a different attempt')
        need(rid['variant']==step['variant'] and rid['campaign']==step['phase'] and rid['mode']==('smoke' if i==0 else 'formal'),'wrong runner condition')
        need(rid['boot_id']==before['boot_id']==after['boot_id']==boot,'boot changed inside a study step')
        need(rid['boot_uuid']==before['boot_uuid']==after['boot_uuid']==identity['boot_uuid'],'firmware changed inside a study step')
        need(rid['manifest_sha256']==identity['package_manifest_sha256'] and rid['base_manifest_sha256']==r.BASE_MANIFEST and rid['profiling'] is False,'runner package/profiling mismatch')
        need(signature(rid['build_identity'])==sig,'build changed within step')
        if i:need(rid['reverse_order']==step['formal_reverse_flags'][i-1],'formal order differs from protocol')
        else:need(rid['reverse_order'] is False,'unexpected smoke order')
        recomputed=s.summarize(folder,emit=False)
        for mode,m in recomputed['modes'].items():
            for filename,h in m['hardware']['output_sha256'].items():
                gold=r.base()/'fixture/chunks'/filename.replace('_output','_expected');need(h==r.records.sha(gold),'raw output differs from golden')
        result.append((folder,recomputed));referenced|={x.relative_to(R).as_posix() for x in folder.rglob('*') if x.is_file()}
    diag=status.get('diagnostic');diagnostic_data=None
    if step['phase']=='host':
        need(isinstance(diag,str) and diag.startswith('results_cpu_diag_') and '/' not in diag,'host step CPU diagnostic missing')
        folder=safe(R,diag);d=load(folder/'status.json');di=load(folder/'identity.json')
        need(d['status']=='PASS_CPU_DIAGNOSTIC' and d['measured']==12 and di['diagnostic_only'] is True and di['perf_requested'] is False,'CPU diagnostic protocol')
        need(di['boot_id']==load(folder/'environment_before.json')['boot_id']==load(folder/'environment_after.json')['boot_id']==boot and di['cpu_sha256']==build['binaries']['cached_cpu'],'CPU diagnostic boot/binary')
        need(di['manifest_sha256']==identity['package_manifest_sha256'],'diagnostic package identity')
        vals=d['all_formal_compute_samples_ms'];need(len(vals)==12 and all(math.isfinite(v) and v>0 for v in vals),'CPU diagnostic values')
        first,last=statistics.median(vals[:6]),statistics.median(vals[6:]);drift=(last/first-1)*100
        for key,want in [('compute_first6_median_ms',first),('compute_last6_median_ms',last),('drift_percent',drift)]:need(math.isclose(d[key],want,rel_tol=1e-7,abs_tol=.002),'CPU diagnostic aggregate changed')
        need(d['review']==(abs(drift)>5),'CPU diagnostic review flag')
        diagnostic_data=dict(first6_median_ms=first,last6_median_ms=last,drift_percent=drift,review=d['review'],not_part_of_primary_CPU_reference=True)
        referenced|={x.relative_to(R).as_posix() for x in folder.rglob('*') if x.is_file()}
    else:need(diag is None,'diagnostic sampling is not part of ablation step')
    need(set(index)==referenced,'sealed file inventory differs from referenced results')
    modes={}
    for mode in result[1][1]['modes']:
        formal=[x[1]['modes'][mode] for x in result[1:]]
        walls=[v['replay_wall_ms'] for m in formal for v in m['hardware']['all_samples'] if not v['warmup'] and not v['export_only']]
        need(len(walls)==10,'formal per-boot count')
        median=statistics.median(walls);cpu_full=[m[k]['recomputed_ms']['full_replay_median_ms'] for m in formal for k in ('cpu2_before','cpu2_after')];cpu_compute=[m[k]['recomputed_ms']['compute_sum_median_ms'] for m in formal for k in ('cpu2_before','cpu2_after')]
        modes[mode]=dict(samples=10,wall_median_ms=median,wall_min_ms=min(walls),wall_max_ms=max(walls),all_wall_ms=walls,cpu_full_medians_ms=cpu_full,cpu_compute_medians_ms=cpu_compute,cpu_drift_percent=[m['cpu_compute_drift_percent'] for m in formal],cpu_drift_review=any(m['drift_over_5_percent'] for m in formal),hardware_wall_speedup_vs_adjacent_CPU_full=[x/median for x in cpu_full],hardware_wall_speedup_vs_adjacent_CPU_compute=[x/median for x in cpu_compute],setup_ms=[m['hardware']['setup']['setup_ms'] for m in formal],export_wall_ms=[v['replay_wall_ms'] for m in formal for v in m['hardware']['all_samples'] if v['export_only']])
    out=dict(step_id=step['id'],phase=step['phase'],variant=step['variant'],block=step['block'],boot_id=boot,attempt=attempt.name,modes=modes,result_directories=refs,diagnostic=diag,diagnostic_statistics=diagnostic_data,build_signature=sig)
    if step['phase']=='host':
        a,b=(modes[m]['wall_median_ms'] for m in ('map_pingpong','map_finish_overlap'));out['paired_host_improvement']=dict(before_ms=a,after_ms=b,saved_ms=a-b,reduction_percent=(1-b/a)*100,speedup=a/b)
    return out
def summarize(phase='all'):
    need(phase in ('all','host','ablation'),'invalid phase');p=protocol();selected={};failed=[];incomplete=[];ordered=[];all_attempts=[];sig=None
    steps={x['id']:x for x in p['steps']}
    for attempt in sorted((R/'study_runs').glob('attempt_*')):
        need(attempt.is_dir() and not attempt.is_symlink(),'unsafe study attempt directory');all_attempts.append(attempt.name)
        identity=load(attempt/'attempt_identity.json');need(identity['step_id'] in steps,'unknown study step')
        status=load(attempt/'status.json') if (attempt/'status.json').exists() else {}
        if status.get('status')!='PASS_BOARD_STEP_PENDING_CRYPTO':
            (failed if status.get('status')=='FAILED_OR_INTERRUPTED' else incomplete).append(dict(attempt=attempt.name,step_id=identity['step_id'],phase=identity['phase'],status=status.get('status','MISSING_STATUS')));continue
        row=validate_attempt(attempt,steps[identity['step_id']],p)
        need(row['step_id'] not in selected,'duplicate successful attempts for one step; do not select fastest')
        if sig is None:sig=row['build_signature']
        need(row['build_signature']==sig,'CPU or host build differs across enrolled steps')
        selected[row['step_id']]=row;ordered.append(row['step_id'])
    # Board UTC can jump after reboot/NTP. Enrollment uses the fixed logical step
    # sequence, not lexicographic timestamps or file mtimes.
    wanted=[x['id'] for x in p['steps']];need(set(ordered)==set(wanted[:len(ordered)]),'successful steps leave a gap in frozen sequence')
    selected={step_id:selected[step_id] for step_id in wanted[:len(ordered)]}
    for ph in ('host','ablation'):
        boots=[row['boot_id'] for row in selected.values() if row['phase']==ph];need(len(boots)==len(set(boots)),'repeated boot counted within '+ph)
    host=[row for row in selected.values() if row['phase']=='host'];ab=[row for row in selected.values() if row['phase']=='ablation']
    host_stats=None
    if host:
        host_stats=dict(independent_boots=len(host),target_boots=3,completed=len(host)==3,per_boot=[dict(step_id=x['step_id'],boot_id=x['boot_id'],**x['paired_host_improvement']) for x in host],median_reduction_percent_across_boots=statistics.median(x['paired_host_improvement']['reduction_percent'] for x in host),all_boots_improve=all(x['paired_host_improvement']['saved_ms']>0 for x in host),boot_equal_weight_wall_medians_ms={m:statistics.median(x['modes'][m]['wall_median_ms'] for x in host) for m in ('map_pingpong','map_finish_overlap')},aggregation='Equal weight to each independent boot median. Never pool all repeats across boots as independent experiments.')
    blocks=[]
    for block in (1,2):
        rows=[x for x in ab if x['block']==block];values={x['variant']:x['modes']['map_pingpong']['wall_median_ms'] for x in rows}
        item=dict(block=block,complete=len(rows)==4,execution_order=[x['variant'] for x in rows],wall_median_ms_by_variant=values)
        if item['complete']:
            t00,t10,t01,t11=(values[v] for v in (DIAG,AIE,RED,CORE))
            item.update(AIE_speedup_with_old_reducer=t00/t10,reducer_speedup_with_old_AIE=t00/t01,AIE_speedup_with_new_reducer=t01/t11,reducer_speedup_with_new_AIE=t10/t11,combined_speedup=t00/t11,additive_wall_interaction_ms=t11-t10-t01+t00,interaction_scope='Descriptive 2x2 contrast in wall milliseconds; negative means extra reduction under an additive-time model. Variants run on distinct boots, so this alone is not a causal cycle-level attribution.')
        blocks.append(item)
    refs={x for row in selected.values() for x in row['result_directories']};un_enrolled=[q.name for q in sorted(R.glob('results_overlap_*')) if q.is_dir() and q.name not in refs]
    review=bool(failed or incomplete or un_enrolled or any(m['cpu_drift_review'] for row in selected.values() for m in row['modes'].values()) or any(row['diagnostic_statistics'] and row['diagnostic_statistics']['review'] for row in selected.values()))
    next_step=p['steps'][len(selected)] if len(selected)<len(p['steps']) else None
    filtered=[x for x in selected.values() if phase=='all' or x['phase']==phase]
    return dict(schema=SCHEMA,status='BOARD_DATA_COMPLETE_PENDING_INDEPENDENT_CRYPTO' if next_step is None else 'STUDY_IN_PROGRESS',package_manifest_sha256=r.records.sha(R/'SHA256SUMS_PACKAGE'),protocol_sha256=r.records.sha(R/'STUDY_PROTOCOL.json'),selected_phase=phase,completed_steps=len(selected),total_steps=len(p['steps']),next_step=next_step,steps=filtered,host_repeatability=host_stats,ablation_blocks=blocks,completed_ablation_steps=len(ab),all_four_variants_in_both_ablation_blocks=len(ab)==8,failed_attempts=failed,incomplete_attempts=incomplete,un_enrolled_result_folders=un_enrolled,review_required=review,crypto_return='PENDING_ACTUAL_BOARD_OUTPUTS',scope='One fixed real v32 workload, N131072 L14 K16. Full resident verified wall is primary; setup/export separate. CPU diagnostic and host envelopes are not device events. All failures and raw repeats are retained. No predicted improvement, optimal-CPU or full-model claim.')
