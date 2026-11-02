"""Recompute each actual run; never pool smoke/formal or different boots."""
from collections import defaultdict
from pathlib import Path
import json,statistics
import compact_io as io,window_board as wb
def main():
 groups=defaultdict(list);attempts=[]
 for p in sorted(wb.ROOT.glob('results_window_*')):
  if not p.is_dir():continue
  status=io.load(p/'status.json') if (p/'status.json').is_file() else {'status':'INCOMPLETE_NO_STATUS'}
  row=dict(folder=p.name,status=status)
  if status.get('status')=='PASS_WINDOW_V2_SPLIT_EXPORT_PENDING_GROUND_RETURN':
   identity=io.load(p/'run_identity.json');s=wb.summarize(p);row['recomputed']=s
   key=tuple(identity[k] for k in ['variant','layout','cache_policy','order','kind','boot_id']);groups[key].append(s)
  attempts.append(row)
 io.need(attempts,'no window attempts found');cohorts=[]
 for key,runs in groups.items():
  samples=[x for r in runs for x in r['phases']['hardware']['all_formal_request_ms']]
  cohorts.append(dict(zip(['variant','layout','cache_policy','order','kind','boot_id'],key),runs=len(runs),samples=len(samples),hardware_request_median_ms=statistics.median(samples),all_request_ms=samples,export_full_recompute_ms=[r['phases']['hardware']['export_full_recompute_ms'] for r in runs],review_required=any(r['review_required'] for r in runs),performance_comparison_eligible=all(r['performance_comparison_eligible'] for r in runs),adjacent_CPU_request_speedup_ranges=[r['speedups_vs_adjacent_CPU_request'] for r in runs]))
 answer=dict(status='RECOMPUTED_WINDOW_CAMPAIGN_PENDING_GROUND_RETURN',cohorts=cohorts,attempts=attempts,scope='Each boot,order,layout,policy and smoke/formal kept separate. Includes failed/incomplete attempts. New and previous protocols are not blindly pooled. Resources are routed totals; no inference of bottleneck from area.')
 io.write_json(wb.ROOT/'window_campaign.json',answer);print(json.dumps({'cohorts':cohorts,'attempts':len(attempts)},indent=2));print('CAMPAIGN_SUMMARY='+str(wb.ROOT/'window_campaign.json'))
if __name__=='__main__':main()
