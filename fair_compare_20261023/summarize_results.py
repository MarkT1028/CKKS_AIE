#!/usr/bin/env python3
"""Validate complete CPU/HW board runs and report qualified timing comparisons."""
from pathlib import Path
import argparse,csv,datetime as dt,json,math,statistics
from board_experiment import ROOT,VARIANTS,FLAGS,sha,require,check_package

def rows(p):
 with Path(p).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def stats(v):
 require(bool(v) and all(math.isfinite(x) and x>=0 for x in v),'invalid timing samples')
 s=sorted(v);return {'n':len(v),'median':statistics.median(v),'p95':s[math.ceil(.95*len(s))-1],
 'min':min(v),'max':max(v),'mean':statistics.mean(v),'sample_stdev':statistics.stdev(v) if len(v)>1 else None}
def case_statistics(base,cpu,reps,warmups,k,threads=None,mode=None,variant=None):
 data=rows(base/'host/iterations.csv');summary=rows(base/'host/summary.csv');require(len(summary)==1,'invalid summary')
 summary=summary[0];require(len(data)==reps+warmups,'incorrect number of repetitions')
 for i,r in enumerate(data):
  require(int(r['repetition'])==i and int(r['warmup'])==int(i<warmups),'repetition order / warmup mismatch')
  require(int(r['K'])==k and int(r['verified_words'])==73728,'K / verification count mismatch')
  if cpu:
   require(int(r['threads'])==threads,'CPU thread count mismatch')
   names=['poison_ms','compute_ms','validation_ms'];total='verified_call_ms'
  else:
   require(r['variant']==variant and r['mode']==mode,'hardware variant / mode mismatch')
   names=['upload_ms','poison_ms','execution_ms','status_ms','readback_ms','merge_ms','validation_ms'];total='transaction_ms'
   require(0<=float(r['launch_ms'])<=float(r['execution_ms']),'launch is not inside execution')
  values=[float(r[n]) for n in names];require(all(math.isfinite(x) and x>=0 for x in values),'invalid phase sample')
  require(abs(sum(values)-float(r[total]))<=.000010,'phase sum does not equal call/transaction')
 measured=data[warmups:];names=names+[total]
 result={n:stats([float(r[n]) for r in measured]) for n in names}
 require(int(summary['K'])==k and int(summary['repetitions'])==reps and int(summary['warmups'])==warmups,'summary count mismatch')
 mapping=({'compute_median_ms':('compute_ms','median'),'compute_p95_ms':('compute_ms','p95'),
           'compute_min_ms':('compute_ms','min'),'compute_max_ms':('compute_ms','max'),
           'verified_call_median_ms':('verified_call_ms','median'),'validation_median_ms':('validation_ms','median')} if cpu else
          {'execution_median_ms':('execution_ms','median'),'execution_p95_ms':('execution_ms','p95'),
           'execution_min_ms':('execution_ms','min'),'execution_max_ms':('execution_ms','max'),
           'transaction_median_ms':('transaction_ms','median'),'validation_median_ms':('validation_ms','median')})
 for field,(phase,s) in mapping.items():require(abs(float(summary[field])-result[phase][s])<=.0000011,'summary statistic mismatch: '+field)
 if cpu:require(int(summary['threads'])==threads and int(summary['N'])==8192 and int(summary['L'])==3,'CPU scope mismatch')
 else:require(summary['scope']=='raw_ckks_mac' and summary['format']=='raw' and int(summary['cores'])==(1 if variant in ('baseline_1','raw_1_pipe') else 2),'hardware scope mismatch')
 return result,measured

def taiwan_day(value):return dt.datetime.fromisoformat(value).astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
def inspect_run(directory,fixtures):
 directory=Path(directory).resolve();m=json.loads((directory/'experiment.json').read_text(encoding='utf-8'))
 require(m['schema']=='ckks_fair_board_v1' and m['status']=='PASS_ALL_12_CASES' and m['board_run'] is True,'not a completed board experiment')
 require(not m.get('synthetic_fixture_for_tests',False),'synthetic fixtures are not measured board results')
 require((directory/'STATUS.txt').read_text().strip()=='PASS_ALL_12_CASES','status file mismatch')
 v=m['variant'];require(v in VARIANTS and len(m['cases'])==12,'variant/case coverage mismatch')
 reps=int(m['repetitions']);warm=int(m['warmups']);require(reps>=1 and warm==3,'repetition settings')
 expected_uuid=(ROOT/'variants'/v/'EXPECTED_BOOT_UUID').read_text().strip()
 require(m['environment_before']['boot_uuid']==m['environment_after']['boot_uuid']==expected_uuid,'running hardware UUID mismatch')
 boot_id=m['environment_before']['boot_id'];require(boot_id and m['environment_after']['boot_id']==boot_id,'boot changed mid experiment')
 for name,h in m['fixture_sha256'].items():require(sha(fixtures/name)==h,'fixture changed: '+name)
 for key in ['cpu_build','hardware_host_build']:
  b=m[key];require(b['architecture']=='aarch64' and b['flags']==FLAGS,'not an ARM comparison build')
  for name,h in b['source_files'].items():require(sha(ROOT/name)==h,'source mismatch: '+name)
 require(m['cpu_build']['compiler_version']==m['hardware_host_build']['compiler_version'],'compiler mismatch')
 require(m['cpu_build']['package_manifest_sha256']==m['hardware_host_build']['package_manifest_sha256']==m['package']['manifest_sha256']==sha(ROOT/'SHA256SUMS_PACKAGE'),'package identity mismatch')
 cases={};environment=[m['environment_before'],m['environment_after']]
 for c in m['cases']:
  relative=Path(c['path']);require(not relative.is_absolute() and '..' not in relative.parts,'unsafe case path')
  base=directory/relative;require(json.loads((base/'case.json').read_text())==c and c['status']=='PASS','case metadata mismatch')
  k=int(c['K']);require(k in [1,16],'unsupported K');cpu=c['kind']!='hardware'
  require(c['kind'] in ['cpu_before','hardware','cpu_after'],'unknown case kind')
  key=(c['kind'],k,c['threads'] if cpu else c['mode']);require(key not in cases,'duplicate case')
  golden=fixtures/('expected_raw.bin' if k==1 else 'expected_k16_raw.bin');output=base/'host/output_last.bin'
  require(sha(output)==c['output_sha256'] and output.read_bytes()==golden.read_bytes(),'output does not match complete golden')
  log=(base/'host.log').read_text();require(('PASS CPU_FULL_MAC' if cpu else 'PASS FULL_MAC') in log,'missing PASS in log')
  if not cpu:
   ini=(base/'xrt.ini').read_text().replace(' ','');require('aie_profile=false' in ini and 'aie_trace=false' in ini,'profiling was enabled')
  st,measured=case_statistics(base,cpu,reps,warm,k,c['threads'],c['mode'],v)
  cases[key]={'statistics':st,'measured':measured}
  for s in [c['environment_before'],c['environment_after']]:
   require(s['boot_id']==boot_id and s['boot_uuid']==expected_uuid,'case hardware changed')
   require(s['kernel']['machine']=='aarch64' and 'vek280' in s['model'].lower(),'case is not VEK280 ARM')
   environment.append(s)
 for k in [1,16]:
  for phase in ['cpu_before','cpu_after']:
   for t in [1,2]:require((phase,k,t) in cases,'missing CPU case')
  for mode in ['resident','transfer']:require(('hardware',k,mode) in cases,'missing hardware case')
 clock_profiles=[]
 clock_snapshots_available=True
 for s in environment:
  clock_snapshots_available=clock_snapshots_available and bool(s['cpu_policies']) and all(
   (p.get('scaling_cur_freq') or '').isdigit() and int(p['scaling_cur_freq'])>0 and bool(p.get('scaling_governor')) for p in s['cpu_policies'].values())
  clock_profiles.append(json.dumps({'policies':s['cpu_policies'],'affinity':s['affinity'],'kernel':s['kernel']['release']},sort_keys=True))
 output_rows=[]
 for k in [1,16]:
  for t in [1,2]:
   before=cases['cpu_before',k,t];after=cases['cpu_after',k,t]
   compute=stats([float(r['compute_ms']) for q in [before,after] for r in q['measured']])
   call=stats([float(r['verified_call_ms']) for q in [before,after] for r in q['measured']])
   drift=100*(after['statistics']['compute_ms']['median']/before['statistics']['compute_ms']['median']-1)
   for mode in ['resident','transfer']:
    hw=cases['hardware',k,mode]['statistics'];e=hw['execution_ms']['median'];tr=hw['transaction_ms']['median']
    output_rows.append({'variant':v,'session':m['session_label'],'boot_id':boot_id,'taiwan_day':taiwan_day(m['started_at_utc']),
     'K':k,'cpu_threads':t,'hardware_mode':mode,'hardware_samples':reps,'cpu_samples':compute['n'],
     'cpu_compute_median_ms':compute['median'],'hardware_execution_median_ms':e,'mainloop_speedup_cpu_over_hardware':compute['median']/e,
     'cpu_verified_call_median_ms':call['median'],'hardware_transaction_median_ms':tr,'verified_call_speedup_cpu_over_hardware':call['median']/tr,
     'cpu_before_to_after_change_percent':drift,'environment_snapshots_constant_in_run':clock_snapshots_available and len(set(clock_profiles))==1,
     'formal_30_or_more':reps>=30})
 return {'directory':str(directory),'variant':v,'boot_id':boot_id,'session':m['session_label'],'repetitions':reps,
         'taiwan_day':taiwan_day(m['started_at_utc']),'end_taiwan_day':taiwan_day(m['completed_at_utc']),
         'compiler':m['cpu_build']['compiler_version'],'cpu_source_hash':m['cpu_build']['source_files']['cpu/cpu_bench.cpp'],
         'clock_profiles':list(set(clock_profiles)),'clock_snapshots_available':clock_snapshots_available,'rows':output_rows}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('results',nargs='+',type=Path);ap.add_argument('--output-dir',required=True,type=Path)
 ap.add_argument('--fixtures',type=Path,default=ROOT/'fixtures');a=ap.parse_args();check_package()
 require(not a.output_dir.exists(),'choose a new output directory')
 require(len({p.resolve() for p in a.results})==len(a.results),'duplicate result directory')
 runs=[inspect_run(p,a.fixtures) for p in a.results];formal=[r for r in runs if r['repetitions']>=30]
 coverage={v:{'formal_runs':sum(r['variant']==v for r in formal),'distinct_boots':len({r['boot_id'] for r in formal if r['variant']==v}),
              'days':sorted({r['taiwan_day'] for r in formal if r['variant']==v and r['taiwan_day']==r['end_taiwan_day']})} for v in VARIANTS}
 common_days=set.intersection(*(set(coverage[v]['days']) for v in VARIANTS))
 source_consistent=len({(r['compiler'],r['cpu_source_hash']) for r in runs})==1
 clocks_consistent=all(r['clock_snapshots_available'] for r in runs) and len({p for r in runs for p in r['clock_profiles']})==1
 complete=bool(common_days) and source_consistent and clocks_consistent and all(coverage[v]['distinct_boots']>=2 for v in VARIANTS)
 out={'status':'VALIDATED_COMPLETE_REPEATED_COMPARISON' if complete else 'VALIDATED_PARTIAL_OR_QUALIFIED_COVERAGE',
      'all_saved_outputs_and_iteration_statistics_verified':True,'coverage':coverage,'all_four_same_day_formal_dates':sorted(common_days),
      'compiler_and_CPU_source_consistent':source_consistent,'CPU_frequency_governor_affinity_snapshots_consistent':clocks_consistent,
      'claim_boundary':'CPU reference implementations, not best possible CPU performance. Mainloop includes differing control paths; verified raw-call costs are separately compared. Input file I/O, one-time setup and OpenFHE postprocessing excluded.',
      'environment_boundary':'Only before/after case snapshots. No continuous frequency/temperature or electrical power measurement.',
      'runs':runs}
 a.output_dir.mkdir(parents=True);(a.output_dir/'comparison.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 allrows=[row for r in runs for row in r['rows']]
 with (a.output_dir/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
 md=['# 同板 CPU／硬體比較','',f"狀態：{out['status']}",'',
     '速度比＝CPU時間÷硬體時間；大於1表示該比較中硬體較快。CPU為1／2執行緒參考實作，不能稱為最佳化CPU上限。',
     'CPU樣本合併同session的before與after；硬體各模式單獨統計。暖機排除。兩種計時邊界分開，不把硬體execution當成完整應用。','',
     '| 版本／session | K | CPU執行緒 | 硬體模式 | CPU運算ms | 硬體主流程ms | 主流程速度比 | CPU完整核對呼叫ms | 硬體交易ms | 呼叫速度比 |',
     '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
 for r in allrows:md.append(f"| {r['variant']}/{r['session']} | {r['K']} | {r['cpu_threads']} | {r['hardware_mode']} | {r['cpu_compute_median_ms']:.6f} | {r['hardware_execution_median_ms']:.6f} | {r['mainloop_speedup_cpu_over_hardware']:.4f} | {r['cpu_verified_call_median_ms']:.6f} | {r['hardware_transaction_median_ms']:.6f} | {r['verified_call_speedup_cpu_over_hardware']:.4f} |")
 md+=['','## 覆蓋與限制','',f'四架構均有正式測試的共同台灣日期：{sorted(common_days)}。',f'CPU來源／編譯器一致：{source_consistent}；頻率／governor／affinity快照一致：{clocks_consistent}。',
      '不同boot/session及硬體映像依原始紀錄區分；CPU前後變化見CSV。超過5%的變化建議重跑確認，原樣本不刪除。',
      '尚未納入原應用資料準備、relin／rescale、解密與功耗。']
 (a.output_dir/'比較摘要.md').write_text('\n'.join(md)+'\n',encoding='utf-8');print(out['status']);print('SUMMARY='+str(a.output_dir))

if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('FAIL: '+str(e))
