"""Recompute samples before comparing I/O request walls and resident costs."""
import ga3_board as b

def main():
    runs=[];failures=[]
    for folder in sorted(b.ROOT.glob('results_ga3_*')):
        try:
            b.need(b.load(folder/'status.json')['status']=='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN','incomplete/failed run retained')
            s=b.summarize(folder);i=b.load(folder/'identity.json');env=b.load(folder/'environment_before.json')
            runs.append(dict(folder=folder.name,stamp=folder.name.rsplit('_',1)[-1],boot_id=env['boot_id'],variant=i['variant'],profile=s['hostopt_profile'],
                mode=s['mode'],order=i['command'][7],verification=s['verification_protocol'],
                resident_ms=s['resident_window_median_sum_hardware_ms'],admission_ms=s['admission_ms'],request_ms=s['campaign_wall_ms'],
                complete_layer_raw_MAC=s['complete_layer_raw_MAC_coverage'],verified_words=s['verified_words'],
                admission_substages=s.get('admission_substages'),CPU_drift_percent=s.get('CPU_window_sum_drift_percent')))
        except Exception as e:failures.append(dict(folder=folder.name,reason=str(e)))
    screens=[]
    for candidate in [r for r in runs if r['mode']=='pilot' and r['profile']!='legacy']:
        anchors=[r for r in runs if r['mode']=='pilot' and r['profile']=='legacy'
                 and all(r[k]==candidate[k] for k in ('boot_id','variant','order','verified_words'))]
        before=[r for r in anchors if r['stamp']<candidate['stamp']];after=[r for r in anchors if r['stamp']>candidate['stamp']]
        if not before or not after:continue
        first=max(before,key=lambda r:r['stamp']);last=min(after,key=lambda r:r['stamp'])
        screens.append(dict(profile=candidate['profile'],boot_id=candidate['boot_id'],variant=candidate['variant'],
            subset_windows=16,request_ms=candidate['request_ms'],legacy_before_ms=first['request_ms'],legacy_after_ms=last['request_ms'],
            request_reductions_percent=[100*(1-candidate['request_ms']/r['request_ms']) for r in (first,last)],
            legacy_request_drift_percent=100*(last['request_ms']/first['request_ms']-1),
            verification_protocol=candidate['verification'],verification_protocol_changed=candidate['profile']=='sha256',
            formal_performance_claim=False,CPU_speedup_claim=False,whole_layer_latency_claim=False))
    b.write(b.ROOT/'campaign_summary.json',dict(status='IOOPT_REQUEST_AND_RESIDENT_RESULTS_RECOMPUTED',runs=runs,pilot_screens=screens,
        retained_failures=failures,board_performance='PENDING_FULL_MATCHED_VARIANT_PROFILE_ABA_AND_GROUND_RETURN',
        scope='Pilot is one verified 16-window subset request including admission. Probe/windows also include CPU anchors and repetitions in campaign wall. SHA256 avoids gold payload I/O while hashing all canonical output bytes; arithmetic and hardware are unchanged. Protocol changes are declared. No CUDA speedup or full original-layer latency is claimed.'))
    for row in runs:
        print(f"{row['profile']} {row['mode']}: request={row['request_ms']:.3f} ms admission={row['admission_ms']:.3f} ms resident={row['resident_ms']:.3f} ms verification={row['verification']}")
    for row in screens:print('IO_PILOT_SCREEN='+str(row))
    if failures:print('RETAINED_FAILURES='+str(failures))
    print('SUMMARY='+str(b.ROOT/'campaign_summary.json'))

if __name__=='__main__':main()
