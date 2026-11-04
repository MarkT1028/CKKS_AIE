"""Recompute actual current-kit formal runs; keep each boot and order separate."""
import json,statistics
from collections import defaultdict
import compact_io as io,window_board as wb
def compare(root):
 groups=defaultdict(list);attempts=[]
 for p in sorted(root.glob('results_window_native_*')):
  if not p.is_dir():continue
  status=io.load(p/'status.json') if (p/'status.json').is_file() else {'status':'INCOMPLETE'}
  attempts.append(dict(folder=p.name,status=status))
  if status.get('status')!='PASS_WINDOW_V2_SPLIT_EXPORT_PENDING_GROUND_RETURN':continue
  ident=io.load(p/'run_identity.json');s=wb.summarize(p)
  io.need(ident['manifest_sha256']==io.sha(root/'SHA256SUMS_PACKAGE'),'cross-release result cannot be pooled')
  if ident['kind']!='formal':continue
  io.need(ident['repetitions']>=3 and ident['warmups']>=1,'formal sample requirements')
  key=(ident['variant'],ident['boot_id'],ident['order'],ident['layout'],ident['cache_policy'],ident['data']['manifest_sha256'],ident['data']['capture_id'])
  groups[key].append((ident,s,p))
 cohorts=[]
 for key,values in groups.items():
  samples=[a for _,s,_ in values for a in s['phases']['hardware']['all_formal_request_ms']]
  cohorts.append(dict(variant=key[0],boot_id=key[1],order=key[2],layout=key[3],policy=key[4],data_manifest_sha256=key[5],capture_id=key[6],runs=len(values),samples_ms=samples,median_ms=statistics.median(samples),CPU_review_required=any(s['review_required'] for _,s,_ in values),utc=min(io.load(p/'environment_before.json')['utc'] for _,_,p in values)))
 comparisons=[]
 for native in [c for c in cohorts if c['variant']=='v32_native_pl_2_pipe']:
  matches=[c for c in cohorts if c['variant']=='v32_core_2_pipe' and all(c[k]==native[k] for k in ['order','layout','policy','data_manifest_sha256','capture_id'])]
  before=[c for c in matches if c['utc']<native['utc']];after=[c for c in matches if c['utc']>native['utc']]
  eligible=len({c['boot_id'] for c in matches})>=2 and bool(before) and bool(after) and not native['CPU_review_required'] and all(not c['CPU_review_required'] for c in matches)
  comparisons.append(dict(native=native,matched_AIE_cohorts=matches,AIE_to_native_time_ratios=[c['median_ms']/native['median_ms'] for c in matches],native_faster_than_each_matched_AIE=bool(matches) and all(native['median_ms']<c['median_ms'] for c in matches),has_AIE_before_and_after=bool(before and after),formal_cross_boot_claim_eligible=eligible,review_required=not eligible,scope='Numeric observations only until balanced AIE-before/native/AIE-after, same capture/protocol and CPU stability pass. Do not pool smoke, different orders, policies or boots. Ground verification of actual outputs remains separate.'))
 return dict(status='RECOMPUTED_NATIVE_PL_AND_AIE_CAMPAIGN',cohorts=cohorts,comparisons=comparisons,attempts=attempts)
def main():
 wb.check_code();answer=compare(wb.ROOT);io.need(answer['attempts'],'no current-kit attempts');io.write_json(wb.ROOT/'native_campaign.json',answer)
 for c in answer['cohorts']:print(f"{c['variant']} boot={c['boot_id']} order={c['order']} n={len(c['samples_ms'])} request_ms={c['median_ms']:.6f} CPU_review={c['CPU_review_required']}")
 for c in answer['comparisons']:print(json.dumps(c,indent=2))
 print('NATIVE_CAMPAIGN='+str(wb.ROOT/'native_campaign.json'))
if __name__=='__main__':main()
