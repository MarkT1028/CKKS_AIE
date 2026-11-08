"""Recompute every result; subset screening is never a whole-layer claim."""
import json
import ga3_board as b

def main():
    rows=[];failures=[]
    for p in sorted(b.ROOT.glob('results_ga3_*')):
        try:
            b.need(b.load(p/'status.json')['status']=='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN','run incomplete/failed')
            s=b.summarize(p);env=b.load(p/'environment_before.json');ident=b.load(p/'identity.json')
            row=dict(folder=p.name,boot_id=env['boot_id'],variant=ident['variant'],profile=s['hostopt_profile'],mode=s['mode'],order=ident['command'][7],resident_ms=s['resident_window_median_sum_hardware_ms'],admission_ms=s['admission_ms'],wall_ms=s['campaign_wall_ms'],verification=s['verification_protocol'],complete_raw_MAC=s['complete_layer_raw_MAC_coverage'],cpu_drift_percent=s.get('CPU_window_sum_drift_percent'),admission=s.get('admission_substages'))
            rows.append(row)
        except Exception as e:failures.append(dict(folder=p.name,reason=str(e)))
    screens=[]
    groups={tuple(r[k] for k in ('boot_id','variant','order')) for r in rows if r['mode']=='probe'}
    for boot,variant,order in sorted(groups):
        rs=[r for r in rows if (r['boot_id'],r['variant'],r['order'],r['mode'])==(boot,variant,order,'probe')]
        for candidate in [r for r in rs if r['profile']!='legacy']:
            before=[r for r in rs if r['profile']=='legacy' and r['folder'].rsplit('_',1)[-1]<candidate['folder'].rsplit('_',1)[-1]]
            after=[r for r in rs if r['profile']=='legacy' and r['folder'].rsplit('_',1)[-1]>candidate['folder'].rsplit('_',1)[-1]]
            if not before or not after:continue
            anchors=[max(before,key=lambda r:r['folder'].rsplit('_',1)[-1]),min(after,key=lambda r:r['folder'].rsplit('_',1)[-1])]
            stable=all(r['cpu_drift_percent'] is not None and abs(r['cpu_drift_percent'])<=5 for r in [candidate,*anchors])
            anchor_change=100*(anchors[1]['resident_ms']/anchors[0]['resident_ms']-1)
            cpu_values=[]
            for r in [candidate,*anchors]:
                s=b.load(b.ROOT/r['folder']/'independently_recomputed_summary.json');cpu_values.extend(s['resident_window_median_sum_'+p+'_ms'] for p in ('cpu_before','cpu_after'))
            cpu_spread=100*(max(cpu_values)/min(cpu_values)-1)
            stable=stable and abs(anchor_change)<=5 and cpu_spread<=5
            screens.append(dict(boot_id=boot,variant=variant,order=order,profile=candidate['profile'],candidate_ms=candidate['resident_ms'],baseline_before_ms=anchors[0]['resident_ms'],baseline_after_ms=anchors[1]['resident_ms'],reductions_percent=[100*(1-candidate['resident_ms']/r['resident_ms']) for r in anchors],baseline_drift_percent=anchor_change,cpu_anchor_spread_percent=cpu_spread,screen_stable=stable,subset_only=True,formal_performance_claim=False,verification_protocol=candidate['verification'],same_verification_as_legacy=candidate['verification']=='FULL_CANONICAL_WORD_COMPARE'))
    result=dict(status='HOSTOPT_RESULTS_RECOMPUTED',runs=rows,subset_screens=screens,retained_failures=failures,board_performance='PENDING_FULL_MATCHED_PROFILE_VARIANT_ABA_AND_GROUND_RETURN',scope='Probe covers 16 selected windows only. Full windows, stream and export are separate. All candidates materialize canonical output and verify every coefficient in their declared scope. SHA256 eliminates reference-file payload reads and changes the verification protocol; CPU/hardware use that same full-output SHA256 check. No GPU speedup is claimed.')
    b.write(b.ROOT/'campaign_summary.json',result)
    for r in rows:print(f"{r['variant']} {r['profile']} {r['mode']} resident={r['resident_ms']:.3f} ms admission={r['admission_ms']:.3f} ms wall={r['wall_ms']:.3f} ms")
    for r in screens:print('SUBSET_SCREEN '+json.dumps(r))
    if failures:print('RETAINED_FAILURES='+json.dumps(failures))
    print('SUMMARY='+str(b.ROOT/'campaign_summary.json'))
if __name__=='__main__':main()
