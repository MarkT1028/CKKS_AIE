"""Conservative AIE / PL / AIE summary. Never extrapolate sampled coefficients."""
from pathlib import Path
import json
import ga3_board as b
def main():
    runs=[];problems=[]
    for p in sorted(b.ROOT.glob('results_ga3_*')):
        try:
            status=b.load(p/'status.json')['status']
            if status!='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN':problems.append(dict(folder=p.name,status=status));continue
            ident=b.load(p/'identity.json');s=b.summarize(p)
        except Exception as e:problems.append(dict(folder=p.name,status='INCOMPLETE_OR_REVIEW_REQUIRED',reason=str(e)));continue
        if s['mode']!='windows':continue
        env=b.load(p/'environment_before.json');runs.append(dict(folder=p.name,variant=ident['variant'],boot_id=env['boot_id'],utc=env['utc'],order=ident['command'][-2],data_manifest=ident['data_manifest_sha256'],code_manifest=ident['manifest_sha256'],sum_ms=s['resident_window_median_sum_hardware_ms'],CPU_before_sum_ms=s['resident_window_median_sum_cpu_before_ms'],CPU_after_sum_ms=s['resident_window_median_sum_cpu_after_ms'],CPU_drift_percent=s['CPU_window_sum_drift_percent'],review_required=s['review_required'],coefficient_windows=s['coefficient_windows']))
    boots={}
    for r in runs:boots.setdefault(r['boot_id'],[]).append(r)
    ordered=sorted(boots.values(),key=lambda rr:min(x['utc'] for x in rr))
    eligible=len(ordered)==3 and [rr[0]['variant'] for rr in ordered]==['v32_core_2_pipe','v32_native_pl_2_pipe','v32_core_2_pipe']
    eligible=eligible and len({r['data_manifest'] for r in runs})==1 and len({r['code_manifest'] for r in runs})==1
    eligible=eligible and not problems and all(len(rr)==2 and {r['order'] for r in rr}=={'ascending','descending'} and not any(r['review_required'] for r in rr) for rr in ordered)
    comparisons=[];cross_boot_CPU_spread={}
    if len(ordered)==3:
        for order in ('ascending','descending'):
            chosen=[[r for r in rr if r['order']==order] for rr in ordered]
            if all(len(rr)==1 for rr in chosen):
                a,p,z=(rr[0]['sum_ms'] for rr in chosen);comparisons.append(dict(order=order,AIE_before_sum_ms=a,PL_sum_ms=p,AIE_after_sum_ms=z,observed_PL_reduction_percent=[100*(1-p/a),100*(1-p/z)],observed_speed_ratios=[a/p,z/p]))
                anchors=[(rr[0]['CPU_before_sum_ms']+rr[0]['CPU_after_sum_ms'])/2 for rr in chosen];cross_boot_CPU_spread[order]=100*(max(anchors)/min(anchors)-1)
    eligible=eligible and len(cross_boot_CPU_spread)==2 and all(x<=5 for x in cross_boot_CPU_spread.values())
    result=dict(status='ABA_REVIEWED' if eligible else 'PENDING_OR_REVIEW_REQUIRED',performance_comparison_eligible=eligible,cross_boot_CPU_anchor_spread_percent=cross_boot_CPU_spread,review_required_folders=problems,runs=runs,comparisons=comparisons,scope='Observed sum of resident per-window medians for declared coefficient scope. Not full ga3 wall time or live model latency. All runs retained; no fastest-run selection. AIE/PL architecture recommendation still requires ground analysis.')
    b.write(b.ROOT/'campaign_summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
