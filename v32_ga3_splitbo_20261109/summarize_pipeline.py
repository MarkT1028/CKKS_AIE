"""Matched tuning results. No subset-to-whole-layer or matched-CUDA claim."""
import json,statistics
import ga3_board as b

def main():
    rows=[]
    for f in sorted(b.ROOT.glob('results_ga3_*')):
        if b.load(f/'status.json')['status']!='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN':continue
        s=b.summarize(f)
        if s['mode'] not in ('pilot','stream'):continue
        i=b.load(f/'identity.json');env=b.load(f/'environment_before.json');cfg=i['tuning'];c=s['controller_profile']
        rows.append(dict(folder=f.name,utc=env['utc'],boot_id=env['boot_id'],variant=i['variant'],mode=s['mode'],order=i['command'][7],profile=s['hostopt_profile'],
            runner_ms=s['runner_wall_ms'],request_ms=s['campaign_wall_ms'],setup_ms=s['setup_ms'],admission_critical_ms=s['admission_ms'],
            resident_ms=s['resident_window_median_sum_hardware_ms'],controller_outside_app_ms=s['runner_wall_ms']-s['total_with_setup_ms'],
            controller_timings_ms=c['timings_ms'],input_stats=s['admission_substages'],prefetch=s.get('io_tuning'),cache_index_sha256=i['compact_cache']['index_sha256']))
    results=[]
    for r in rows:
        if r['profile']=='baseline':continue
        anchors=[x for x in rows if x['profile']=='baseline' and all(x[k]==r[k] for k in ('boot_id','variant','mode','order','cache_index_sha256'))]
        before=[x for x in anchors if x['utc']<r['utc']];after=[x for x in anchors if x['utc']>r['utc']]
        if not before or not after:continue
        a=max(before,key=lambda x:x['utc']);z=min(after,key=lambda x:x['utc']);old=statistics.median([a['runner_ms'],z['runner_ms']]);drift=100*(z['runner_ms']/a['runner_ms']-1)
        answer=dict(variant=r['variant'],mode=r['mode'],order=r['order'],profile=r['profile'],baseline_runner_ms=old,candidate_runner_ms=r['runner_ms'],runner_reduction_percent=100*(1-r['runner_ms']/old),
            baseline_drift_percent=drift,review_required=abs(drift)>5 or r['mode']=='pilot',complete_layer_raw_MAC_coverage=r['mode']=='stream',
            source_check_timings_ms=r['controller_timings_ms'],prefetch=r['prefetch'],CUDA_speedup='NOT_ESTABLISHED_DIFFERENT_SCOPE_PARAMETERS',
            scope='Total runner includes fresh identity checks, setup, data read/decode, all transfers, run/wait, full output verification. One-time cache preparation remains separate.')
        results.append(answer);print(json.dumps(answer,indent=2))
    b.need(results,'No baseline/candidate/baseline matched results')
    b.write(b.ROOT/'pipeline_screen_summary.json',dict(status='MATCHED_TUNING_SCREEN',comparisons=results,rows=rows))

if __name__=='__main__':main()
