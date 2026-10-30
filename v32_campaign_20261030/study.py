#!/usr/bin/env python3
"""Run one explicit user-selected research step; never stages or reboots."""
from pathlib import Path
import argparse,csv,fcntl,json,os,sys
import board_runner as r
import cpu_diagnostics as diag
import study_tools as t
R=Path(__file__).resolve().parent
def save(path,data):
    tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp');r.write(tmp,data);os.replace(tmp,path)
def export_summary(data):
    save(R/'study_summary.json',data)
    path=R/'study_summary.csv';tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    fields=['step_id','phase','block','variant','boot_id','mode','samples','wall_median_ms','wall_min_ms','wall_max_ms','CPU_full_min_ms','CPU_full_max_ms','CPU_compute_min_ms','CPU_compute_max_ms','CPU_drift_review']
    with tmp.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for step in data['steps']:
            for mode,m in step['modes'].items():writer.writerow(dict(step_id=step['step_id'],phase=step['phase'],block=step['block'],variant=step['variant'],boot_id=step['boot_id'],mode=mode,samples=m['samples'],wall_median_ms=m['wall_median_ms'],wall_min_ms=m['wall_min_ms'],wall_max_ms=m['wall_max_ms'],CPU_full_min_ms=min(m['cpu_full_medians_ms']),CPU_full_max_ms=max(m['cpu_full_medians_ms']),CPU_compute_min_ms=min(m['cpu_compute_medians_ms']),CPU_compute_max_ms=max(m['cpu_compute_medians_ms']),CPU_drift_review=m['cpu_drift_review']))
    os.replace(tmp,path)
def report(data):
    print('STUDY_PROGRESS='+str(data['completed_steps'])+'/'+str(data['total_steps']),flush=True)
    h=data['host_repeatability'];print('HOST_BOOTS='+str(h['independent_boots'] if h else 0)+'/3')
    print('ABLATION_STEPS='+str(data['completed_ablation_steps'])+'/8')
    print('REVIEW_REQUIRED='+str(data['review_required']))
    if h:
        for row in h['per_boot']:print(row['step_id']+' old_ms='+format(row['before_ms'],'.3f')+' new_ms='+format(row['after_ms'],'.3f')+' reduction='+format(row['reduction_percent'],'+.2f')+'%')
    for block in data['ablation_blocks']:
        if block['wall_median_ms_by_variant']:
            print('ABLATION_BLOCK_'+str(block['block'])+' complete='+str(block['complete']))
            for variant,wall in block['wall_median_ms_by_variant'].items():print('  '+variant+' wall_ms='+format(wall,'.3f'))
    step=data['next_step']
    if step is None:
        print('BOARD_PLAN_COMPLETE: independent analysis and cryptographic verification remain pending.')
        print('COLLECT: python3 collect_results.py --phase host')
        print('COLLECT: python3 collect_results.py --phase ablation --block 1')
        print('COLLECT: python3 collect_results.py --phase ablation --block 2');return
    print('NEXT_STEP='+step['id']+' phase='+step['phase']+' variant='+step['variant'])
    if step['phase']=='ablation':print('FIXED_HOST_MODE=map_pingpong; ablation block='+str(step['block']))
    if sys.platform=='linux' and r.platform.machine()=='aarch64':
        env=r.environment();same=env['boot_uuid']==r.VARIANTS[step['variant']]['uuid']
        used={x['boot_id'] for x in data['steps'] if x['phase']==step['phase']}
        if not same:
            print('NEXT: sh switch_fair_board.sh '+step['variant']+' check')
            print('THEN: sh switch_fair_board.sh '+step['variant']+' arm')
            print('After ARMED_ONLY, run sync && reboot yourself. No automatic boot writes/reboot occur here.')
            return
        if env['boot_id'] in used:
            print('NEED_NEW_BOOT: current boot was already counted for this phase.')
            print('NEXT: sync && reboot');return
    print('RUN: sh run_study.sh '+step['phase'])
def run_step(phase):
    r.board()
    # Lock the entire three-run step, including its gaps, diagnostics and sealing.
    with (R/'.study.lock').open('a') as coordinator:
        fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with r.device_lock():
            print('CHECKING_PACKAGE_AND_SAVED_STEPS',flush=True);checked=r.check();data=t.summarize();step=data['next_step']
            t.need(step is not None,'study complete; collect the results')
            t.need(step['phase']==phase,'next phase is '+step['phase']+'; use sh run_study.sh next')
            env=r.environment();t.need(env['boot_uuid']==r.VARIANTS[step['variant']]['uuid'],'wrong boot variant; use sh run_study.sh next')
            t.need(env['boot_id'] not in {x['boot_id'] for x in data['steps'] if x['phase']==phase},'this boot already counted in this phase; reboot yourself and run detect')
            build=t.load(R/'bin/build_identity.json');sig=t.signature(build)
            t.need(build['package_manifest_sha256']==checked['manifest_sha256'] and build['base_manifest_sha256']==r.BASE_MANIFEST,'rebuild required')
            for name,h in build['binaries'].items():t.need(r.records.sha(R/'bin'/name)==h,'build binary changed: '+name)
            if data['steps']:t.need(sig==data['steps'][0]['build_signature'],'build differs from enrolled study; do not mix binaries')
            attempt=R/'study_runs'/('attempt_'+r.stamp());attempt.mkdir(parents=True)
            identity=dict(schema=t.SCHEMA,attempt_id=attempt.name,step_id=step['id'],phase=phase,variant=step['variant'],block=step['block'],protocol_sha256=r.records.sha(R/'STUDY_PROTOCOL.json'),package_manifest_sha256=checked['manifest_sha256'],base_manifest_sha256=r.BASE_MANIFEST,boot_id=env['boot_id'],boot_uuid=env['boot_uuid'],created_utc=r.stamp(),formal_reverse_flags=step['formal_reverse_flags'])
            r.write(attempt/'attempt_identity.json',identity);r.write(attempt/'build_identity.json',build)
            context={k:identity[k] for k in ('schema','attempt_id','step_id','phase','variant','block','protocol_sha256')}
            results=[];diagnostic=None
            save(attempt/'status.json',dict(status='RUNNING',results=[],diagnostic=None))
            try:
                print('STARTING_STEP='+step['id']+' '+step['variant'],flush=True)
                results.append(r.run('smoke',step['variant'],False,phase,context))
                save(attempt/'status.json',dict(status='RUNNING',results=[x.name for x in results],diagnostic=None))
                for reverse in step['formal_reverse_flags']:
                    results.append(r.run('formal',step['variant'],reverse,phase,context))
                    save(attempt/'status.json',dict(status='RUNNING',results=[x.name for x in results],diagnostic=None))
                if phase=='host':diagnostic=diag.main(perf=False)
                end=r.environment();t.need(end['boot_id']==env['boot_id'] and end['boot_uuid']==env['boot_uuid'],'boot identity changed during step')
                index_sha=t.seal(R,attempt,results,diagnostic)
                save(attempt/'status.json',dict(status='PASS_BOARD_STEP_PENDING_CRYPTO',results=[x.name for x in results],diagnostic=diagnostic.name if diagnostic else None,sealed_index_sha256=index_sha,finished_utc=r.stamp(),cryptographic_return='PENDING',performance_threshold_applied=False))
                t.validate_attempt(attempt,step,t.protocol())
            except BaseException as exc:
                save(attempt/'status.json',dict(status='FAILED_OR_INTERRUPTED',results=[x.name for x in results],diagnostic=diagnostic.name if diagnostic else None,error=repr(exc),finished_utc=r.stamp(),retain_all_partial_results=True));raise
            data=t.summarize();export_summary(data)
            print('STEP_COMPLETE='+step['id']+'; output cryptographic verification pending.',flush=True)
            if step['id']=='H03':print('HOST_PHASE_COMPLETE: python3 collect_results.py --phase host')
            if step['id'] in ('A04','A08'):print('ABLATION_BLOCK_COMPLETE: python3 collect_results.py --phase ablation --block '+str(step['block']))
            report(data)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',nargs='?',default='next',choices=['next','status','summary','host','ablation']);p.add_argument('--json',action='store_true');a=p.parse_args()
    if a.action in ('host','ablation'):run_step(a.action);return
    # Read-only status does not rewrite prior run comparisons or count repeats twice.
    data=t.summarize()
    if a.action=='summary':export_summary(data);print('STUDY_SUMMARY='+str(R/'study_summary.json'))
    print(json.dumps(data,indent=2,ensure_ascii=False)) if a.json else report(data)
if __name__=='__main__':
    try:main()
    except Exception as exc:print('FAIL_STUDY:',exc,file=sys.stderr);raise SystemExit(1)
