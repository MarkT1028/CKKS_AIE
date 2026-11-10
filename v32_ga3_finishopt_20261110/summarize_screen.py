"""Compare a fresh, matched merge1/direct1/direct2/merge1 pilot sequence."""
import json,statistics
from pathlib import Path
import finish_board as b

def summarize(root=b.ROOT):
    runs=[]
    for path in sorted(Path(root).glob('results_finish_*_pilot_descending_*')):
        if (path/'status.json').is_file() and b.load(path/'status.json')['status']=='PASS_FINISH_BOARD_REPLAY_PENDING_INDEPENDENT_REVIEW':runs.append((path,b.summarize(path)))
    b.need(len(runs)>=4,'need four successful pilot runs: merge1, direct1, direct2, merge1')
    selected=runs[-4:]
    b.need([s['profile'] for _,s in selected]==['merge1','direct1','direct2','merge1'],'last four pilot runs are not the matched control sequence')
    identities=[b.load(p/'identity.json') for p,_ in selected];envs=[b.load(p/'environment_before.json') for p,_ in selected]
    for name in ('manifest_sha256','parent_manifest_sha256','data_manifest_sha256','compact_cache','effective_environment','build'):
        b.need(all(x[name]==identities[0][name] for x in identities),'screen source/build/cache mismatch '+name)
    b.need(len({e['boot_id'] for e in envs})==1,'screen must use the same boot')
    for key in ('scaling_cur_freq','scaling_governor','scaling_setspeed'):
        b.need(len({e['cpu_policy'].get(key) for e in envs})==1,'screen CPU policy/frequency differs '+key)
    ledgers=[[(r['tower_start'],r['coefficient_start'],r['output_ct'],r['L'],r['digest0'],r['digest1'],r['digest2'],r['digest3']) for r in b.readcsv(p/'replay/windows.csv')] for p,_ in selected]
    b.need(all(x==ledgers[0] for x in ledgers),'profiles used different coordinates or actual output digests')
    walls=[s['resident_batch_wall_sum_ms'] for _,s in selected];baseline=statistics.mean((walls[0],walls[-1]));drift=100*(walls[-1]/walls[0]-1)
    answer=dict(status='MATCHED_PILOT_SCREEN_ONLY_PENDING_BOARD_REVIEW',runs=[dict(folder=p.name,profile=s['profile'],resident_batch_wall_sum_ms=s['resident_batch_wall_sum_ms'],admission_ms=s['admission_ms']) for p,s in selected],
        merge_control_drift_percent=drift,review_required=abs(drift)>5,
        direct1_reduction_percent=100*(1-walls[1]/baseline),direct2_reduction_percent=100*(1-walls[2]/baseline),
        direct2_faster_than_both_controls=walls[2]<min(walls[0],walls[-1]),
        scope='16 declared boundary/RNS/output windows, not full1024 latency; no extrapolated full-layer speedup or CPU/CUDA claim.')
    b.write(Path(root)/'screen_summary.json',answer);return answer

if __name__=='__main__':
    try:print(json.dumps(summarize(),indent=2))
    except Exception as e:print('FAIL:',e);raise SystemExit(1)
