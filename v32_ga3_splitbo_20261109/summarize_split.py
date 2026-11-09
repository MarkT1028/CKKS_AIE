"""Compare matching scope and order; retain cold-upload and total-wall costs."""
import argparse,csv,json,statistics
import ga3_board as b
def main():
 p=argparse.ArgumentParser();p.add_argument('--baseline',default='v32_native_lazy8_2_pipe',choices=['v32_core_2_pipe','v32_native_pl_2_pipe','v32_native_lazy8_2_pipe']);a=p.parse_args()
 rows=[]
 for f in sorted(b.ROOT.glob('results_ga3_*')):
  if b.load(f/'status.json')['status']!='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN':continue
  s=b.summarize(f);i=b.load(f/'identity.json');env=b.load(f/'environment_before.json')
  if s['mode'] not in ('pilot','probe','stream'):continue
  first=sum(float(z['wall_ms']) for z in csv.DictReader((f/'replay/samples.csv').open()) if z['phase']=='hardware' and int(z['repetition'])==0)
  rows.append(dict(folder=f.name,variant=i['variant'],boot_id=env['boot_id'],utc=env['utc'],mode=s['mode'],profile=i['hostopt_profile'],order=i['command'][7],windows=s['windows'],reps=s['repetitions_per_window'],warmups=s['warmups_per_window'],data_sha=i['data_manifest_sha256'],cache_sha=i['compact_cache']['index_sha256'],runner_ms=s['runner_wall_ms'],request_ms=s['campaign_wall_ms'],admission_ms=s['admission_ms'],resident_ms=s['resident_window_median_sum_hardware_ms'],first_trial_window_wall_sum_ms=first,split_input_cache=s.get('split_input_cache'),CPU_drift_percent=s.get('CPU_window_sum_drift_percent'),complete_layer_raw_MAC_coverage=s['complete_layer_raw_MAC_coverage']))
 comps=[]
 for x in rows:
  if x['variant']!='v32_native_splitbo_2_pipe' or x['profile']!='guard':continue
  matches=[r for r in rows if r['variant']==a.baseline and all(r[k]==x[k] for k in ('mode','profile','order','windows','reps','warmups','data_sha','cache_sha'))]
  if not matches:continue
  med=lambda k:statistics.median(r[k] for r in matches)
  old=med('resident_ms');rr=med('runner_ms');request=med('request_ms')
  aba=any(r['utc']<x['utc'] and r['boot_id']!=x['boot_id'] for r in matches) and any(r['utc']>x['utc'] and r['boot_id']!=x['boot_id'] for r in matches) and len({r['boot_id'] for r in matches})>=2
  comps.append(dict(mode=x['mode'],order=x['order'],baseline=a.baseline,candidate=x['variant'],baseline_folders=[r['folder'] for r in matches],candidate_folder=x['folder'],baseline_resident_ms=old,candidate_resident_ms=x['resident_ms'],resident_reduction_percent=100*(1-x['resident_ms']/old),baseline_runner_ms=rr,candidate_runner_ms=x['runner_ms'],runner_reduction_percent=100*(1-x['runner_ms']/rr),baseline_request_ms=request,candidate_request_ms=x['request_ms'],request_reduction_percent=100*(1-x['request_ms']/request),baseline_first_trial_window_sum_ms=med('first_trial_window_wall_sum_ms'),candidate_first_trial_window_sum_ms=x['first_trial_window_wall_sum_ms'],candidate_device_cache=x['split_input_cache'],same_source_compact_cache_and_trials=True,complete_layer_raw_MAC_coverage=x['complete_layer_raw_MAC_coverage'],cross_boot_ABA_completed=aba,review_required=True,scope='pilot is first-use measured request including uploads; probe resident formal trials may reuse uploaded inputs, so warmup/first-trial accounting and total wall are retained. Scope/order/trials matched, not device cycles or matched CUDA latency.'))
 b.need(comps,'No matched baseline/split rows yet. Run the SAME run_short.sh on both images first.')
 ablations=[]
 for x in rows:
  if x['variant']!='v32_native_splitbo_2_pipe' or x['profile']!='guard':continue
  matches=[r for r in rows if r['variant']==x['variant'] and r['profile']=='refresh' and all(r[k]==x[k] for k in ('boot_id','mode','order','windows','reps','warmups','data_sha','cache_sha'))]
  if matches:
   baseline=statistics.median(r['resident_ms'] for r in matches)
   ablations.append(dict(mode=x['mode'],order=x['order'],guard_folder=x['folder'],refresh_folders=[r['folder'] for r in matches],refresh_resident_ms=baseline,reuse_resident_ms=x['resident_ms'],resident_reduction_percent=100*(1-x['resident_ms']/baseline),scope='Same image, boot and trial policy; reload all five inputs each hardware trial vs retained read-only BO reuse.'))
 b.write(b.ROOT/'split_comparison_summary.json',dict(status='MATCHED_SCOPE_SPLIT_BO_SCREEN_PENDING_REVIEW',comparisons=comps,reuse_ablations=ablations,rows=rows))
 for r in comps:
  print(f"{r['mode']} {r['order']}: resident {r['baseline_resident_ms']:.3f} -> {r['candidate_resident_ms']:.3f} ms ({r['resident_reduction_percent']:+.2f}%); TOTAL runner {r['baseline_runner_ms']:.3f} -> {r['candidate_runner_ms']:.3f} ms ({r['runner_reduction_percent']:+.2f}%); ABA={r['cross_boot_ABA_completed']}")
 print('Scope and data admission are retained. Return collected archive for independent review.')
if __name__=='__main__':main()
