from pathlib import Path
import json,os,subprocess
R=Path(__file__).resolve().parent;W=R.parents[1];B=R/'build';O=W/'integration/ga3_compactio_20261108/build'
base=dict(os.environ,V32_GA3_CACHE=str(O/'synthetic_cache'),V32_GA3_PREFETCH='1',V32_GA3_READ_MIB='16')
cases=[]
for name,updates in [('bad_read_size',dict(V32_GA3_READ_MIB='8')),('bad_prefetch',dict(V32_GA3_PREFETCH='2')),('missing_cache',dict(V32_GA3_CACHE=str(B/'does_not_exist'))),('missing_crypto',dict(V32_GA3_DISABLE_CRYPTO='1'))]:
 p=subprocess.run([str(B/'model_candidate'),'unused',str(O/'synthetic'),str(B/name),'smoke','1','0','descending','2'],env=dict(base,**updates),capture_output=True,text=True,timeout=90)
 assert p.returncode!=0,(name,p.stdout);cases.append(dict(case=name,result='REJECTED',error=p.stderr.strip()))
# Both raw fallbacks and packed reads use the same exact next-window queue.
env=dict(base,V32_GA3_CACHE=str(O/'hybrid_cache'))
p=subprocess.run([str(B/'model_candidate'),'unused',str(O/'synthetic'),str(B/'hybrid_prefetch'),'pilot','1','0','descending','0'],env=env,capture_output=True,text=True,timeout=120)
assert p.returncode==0,p.stderr
ad=json.loads((B/'hybrid_prefetch/admission_profile.json').read_text());assert ad['packed_records']>0 and ad['raw_records']>0
io=json.loads((B/'hybrid_prefetch/io_tuning.json').read_text());assert io['prefetched_records']==15
(B/'negative_verification.json').write_text(json.dumps(dict(status='PASS_CAPABILITY_FAILURES_AND_EXACT_HYBRID_PREFETCH',cases=cases,board_executed=False),indent=2)+'\n');print('PASS_NEGATIVE_PREFETCH',len(cases))
