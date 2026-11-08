"""Report request + setup, separate preparation, paired drift and break-even."""
from pathlib import Path
import json,math,statistics
import ga3_board as b

def compare(raw,packed,prep):
    b.need(raw and packed,'both raw SHA and packed requests are required')
    # setup is included in the primary time; trials/admission are never
    # mistaken for pure device cycles. One-time cache construction is extra.
    old=statistics.median(raw);new=statistics.median(packed);saving=old-new
    return dict(raw_total_runner_median_ms=old,packed_total_runner_median_ms=new,
        request_reduction_percent=100*saving/old,cache_preparation_work_ms=prep,
        first_use_cache_plus_request_ms=prep+new,first_use_improves=(prep+new)<old,
        break_even_requests=(math.floor(prep/saving)+1 if saving>0 else None),
        scope='Break-even applies ONLY to repeated requests with this same declared workload and cache. Pilot timing cannot be projected to full g_a.3.')

def main():
    rows=[]
    for f in sorted(b.ROOT.glob('results_ga3_*')):
        if b.load(f/'status.json')['status']!='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN':continue
        s=b.summarize(f)
        if s['mode'] not in ('pilot','stream'):continue
        i=b.load(f/'identity.json');e=b.load(f/'environment_before.json');ad=s['admission_substages']
        rows.append(dict(folder=f.name,variant=i['variant'],profile=s['hostopt_profile'],boot_id=e['boot_id'],mode=s['mode'],stamp=e['utc'],
            order=i['command'][7],cache_index_sha256=(i.get('compact_cache') or {}).get('index_sha256'),
            setup_ms=s['setup_ms'],request_ms=s['campaign_wall_ms'],total_ms=s['runner_wall_ms'],application_setup_plus_request_ms=s['total_with_setup_ms'],
            admission_ms=s['admission_ms'],decode_ms=ad['decode_ms'],logical_input_bytes=ad['logical_input_bytes'],read_payload_bytes=ad['bytes'],
            cache_preparation_ms=(i.get('compact_cache') or {}).get('preparation_work_ms',0)))
    b.need(rows,'no pilot/stream rows')
    groups={}
    for row in rows:groups.setdefault((row['variant'],row['boot_id'],row['mode']),[]).append(row)
    results=[]
    for (variant,boot,mode),rs in groups.items():
        packed=[x for x in rs if x['profile']=='packed'];raw=[x for x in rs if x['profile']=='sha256']
        if not raw or not packed:continue
        for index in sorted({x['cache_index_sha256'] for x in packed}):
            candidates=sorted((x for x in packed if x['cache_index_sha256']==index),key=lambda x:x['stamp'])
            before=[x for x in raw if x['stamp']<candidates[0]['stamp']];after=[x for x in raw if x['stamp']>candidates[-1]['stamp']]
            anchors=([max(before,key=lambda x:x['stamp'])] if before else [])+([min(after,key=lambda x:x['stamp'])] if after else [])
            if not anchors:continue
            drift=100*(anchors[-1]['total_ms']/anchors[0]['total_ms']-1) if len(anchors)==2 else None
            result=compare([x['total_ms'] for x in anchors],[x['total_ms'] for x in candidates],max(x['cache_preparation_ms'] for x in candidates))
            result.update(variant=variant,boot_id=boot,mode=mode,cache_index_sha256=index,baseline_drift_percent=drift,review_required=mode=='pilot' or drift is None or abs(drift)>5,
                same_source_and_output_protocol=True,CUDA_comparison='NOT_ESTABLISHED',all_rows=anchors+candidates)
            results.append(result)
            print(json.dumps({k:v for k,v in result.items() if k!='all_rows'},indent=2))
    b.need(results,'no matched raw/packed requests')
    b.write(b.ROOT/'compact_screen_summary.json',dict(status='DECLARED_RAW_MAC_REQUEST_REVIEW_NOT_LIVE_LAYER_LATENCY',groups=results))
if __name__=='__main__':main()
