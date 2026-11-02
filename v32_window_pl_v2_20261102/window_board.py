"""Same h_s.4 six-group contract; CPU / AIE / pure-PL. No boot writes here."""
from pathlib import Path
import argparse,csv,json,math,os,platform,statistics,struct,sys,time
import compact_io as io,full_board as base,memory_admission
ROOT=Path(__file__).resolve().parent
BINARIES=('window_cpu','window_parser','window_host_aie','window_host_pl')
def registry():return io.load(ROOT/'WINDOW_VARIANTS.json')
def rows(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def near(a,b):io.need(abs(float(a)-float(b))<.02,'raw CSV aggregate mismatch')
def check_code():
 c=base.check_code();s=io.load(ROOT/'PACKAGE_STATUS.json');io.need(s.get('window_pl_status')=='OFFLINE_VALIDATED_READY_FOR_USER_BOARD_TEST','window/PL offline gates not signed off')
 variants=registry();io.need(set(variants)=={'v32_core_2_pipe','v32_pure_pl_2_pipe'},'variant registry mismatch')
 for name,v in variants.items():
  p=ROOT/'variants'/name;blob=(p/'ckks_hw_boot.xclbin').read_bytes();io.need(len(blob)>=456 and blob[:8]==b'xclbin2\0' and blob[416:432].hex()==v['uuid'] and struct.unpack_from('<HH',blob,332)==(0,0),'variant flat AXLF UUID/action mask');io.need((p/'EXPECTED_BOOT_UUID').read_text().strip()==v['uuid'] and io.sha(p/'boot0001.bin')==v['boot_sha256']==(p/'EXPECTED_BOOT_SHA256').read_text().strip(),'variant boot/metadata mismatch')
 io.need(variants['v32_core_2_pipe']['AIE_compute_tiles']==2 and variants['v32_pure_pl_2_pipe']['AIE_compute_tiles']==0,'AIE counts are not lane counts')
 return dict(**c,status_window='PASS_WINDOW_AND_PURE_PL_CODE',new_firmware_available=True,board_modified_by_check=False)
def check():
 c=check_code();d=io.verify_data(base.data(),full=True,production=True);io.need(d['manifest_sha256']==io.load(ROOT/'PACKAGE_STATUS.json')['data_manifest_sha256'],'wrong real data capture');return dict(**c,data=d,actual_board_performance='PENDING')
def record_build():
 base.board();v=dict(code_manifest_sha256=io.sha(ROOT/'SHA256SUMS_PACKAGE'),architecture=platform.machine(),binaries={n:io.sha(ROOT/'bin'/n) for n in BINARIES},flags='-O3 -std=c++17 -pthread; XRT hosts -I/usr/include/xrt -lxrt_coreutil; purePL -DWINDOW_PURE_PL',utc=base.stamp());io.write_json(ROOT/'bin/window_build_identity.json',v)
def checked_build(c):
 b=io.load(ROOT/'bin/window_build_identity.json');io.need(b['code_manifest_sha256']==c['manifest_sha256'] and b['architecture']=='aarch64' and set(b['binaries'])==set(BINARIES),'rebuild window binaries')
 for n,h in b['binaries'].items():io.need(io.sha(ROOT/'bin'/n)==h,'changed board binary '+n)
 return b
def detected(env):return next((n for n,v in registry().items() if v['uuid']==env['boot_uuid']),None)
def job_order(chunks,layout,ascending):
 gs=list(range(6)) if ascending else list(range(5,-1,-1));return [(g,c) for c in range(chunks) for g in gs] if layout=='chunk' else [(g,c) for g in gs for c in range(chunks)]
def trace_check(p,identity):
 ts=rows(p/'timeline.csv');its=rows(p/'iterations.csv');jobs=job_order(16,identity['layout'],identity['order']=='ascending');checked=0
 for it in its:
  rep=it['repetition'];previous=[]
  for i,(g,c) in enumerate(jobs):
   frame=[x for x in ts if x['repetition']==rep and int(x['job'])==i];io.need(len(frame)==24+int(it['export_only']),'trace missing/additional stages')
   io.need(all(int(x['group'])==g and int(x['chunk'])==c and int(x['bank'])==i%2 and x['warmup']==it['warmup'] and x['export_only']==it['export_only'] for x in frame),'trace group/chunk/bank identity')
   for x in frame:io.need(0<=float(x['begin_ms'])<=float(x['end_ms'])<=float(it['pipeline_wall_ms'])+.02,'trace outside pipeline wall')
   for a,b in zip(frame,frame[1:]):io.need(float(a['end_ms'])<=float(b['begin_ms'])+.02,'same-frame stage overlap')
   ex=next(x for x in frame if x['stage']=='execute');st=next(x for x in frame if x['stage']=='status');finish=next(x for x in frame if x['stage']=='merge_poison')
   if previous:io.need(float(ex['begin_ms'])+.02>=float(previous[-1]['status']['end_ms']) and float(ex['begin_ms'])<=float(previous[-1]['finish']['begin_ms'])+.02,'launch before status or finish-overlap missing')
   if i>=2:io.need(float(frame[0]['begin_ms'])+.02>=float(previous[-2]['done']['end_ms']),'BO bank reused before complete verification/export')
   previous.append(dict(status=st,finish=finish,done=frame[-1]));checked+=1
 io.need(len(ts)==sum((24+int(x['export_only']))*96 for x in its),'unaccounted trace rows');return checked
def verify_outputs(folder,data):
 manifest=io.load(data/'DATA_MANIFEST.json');files=sorted((folder/'hardware_export/outputs').glob('group_*/*_output.bin'));io.need(len(files)==96,'incomplete actual96 outputs');out=[]
 for g in range(6):
  for c in range(16):
   p=folder/f'hardware_export/outputs/group_{g}/chunk_{c}_output.bin';ref=f'group_{g}/chunks/chunk_{c}_expected.bin';io.need(io.sha(p)==manifest[ref]['sha256'],'actual raw output differs '+str(p));io.record(p,2);out.append(dict(group=g,chunk=c,path=str(p.relative_to(folder)),bytes=p.stat().st_size,sha256=io.sha(p)))
 return out
def summarize(folder,emit=True):
 folder=Path(folder);ident=io.load(folder/'run_identity.json');io.need(ident['protocol']=='hs4_window_v2_split_export' and ident['phase_order']==['cpu_before','hardware','cpu_after','hardware_export'],'wrong timing protocol/order');n,w=ident['repetitions'],ident['warmups'];v=registry()[ident['variant']];result={}
 # Retain concrete process commands/timestamps, proving export starts after CPU-after.
 events=io.load(folder/'phase_events.json');io.need([x['phase'] for x in events]==ident['phase_order'],'missing or reordered process events');end=0
 for event in events:io.need(event['completed'] is True and 0<event['begin_monotonic_ns']<=event['end_monotonic_ns'] and event['begin_monotonic_ns']>=end,'incomplete or overlapping phases');end=event['end_monotonic_ns']
 previous=None
 for phase in ident['phase_order']:
  command=io.load(folder/(phase+'.command.json'));io.need(command['returncode']==0,'failed phase');stamp=command['utc'];io.need(previous is None or stamp>=previous,'command chronology');previous=stamp
  args=command['command'];io.need(Path(args[0]).name==('window_cpu' if phase.startswith('cpu_') else 'window_host_pl' if v['AIE_compute_tiles']==0 else 'window_host_aie'),'wrong executed binary')
  if not phase.startswith('cpu_'):io.need(args[-1]==('export' if phase=='hardware_export' else 'measure'),'hardware measurement/export not separated')
 for phase in ident['phase_order']:
  p=folder/phase;hw=not phase.startswith('cpu_');ex=phase=='hardware_export';expected=1 if ex else n+w;its=rows(p/'iterations.csv');resource=[json.loads(x) for x in (p/'resources.jsonl').read_text().splitlines()];io.need(len(its)==len(resource)==expected,'wrong phase row count');values=[];computes=[]
  for i,x in enumerate(its):
   warm=not ex and i<w;io.need(int(x['repetition'])==i and int(x['warmup'])==int(warm) and int(x['export_only'])==int(ex) and int(x['verified_words'])==33030144,'tags/full coverage')
   loads=16 if ident['layout']=='chunk' else 96;fills=loads if not hw else 64 if ident['layout']=='chunk' else 192;release=ident['cache_policy']=='bounded' or ident['cache_policy']=='export_bounded' and ex
   io.need(int(x['baby_loads'])==loads and int(x['baby_BO_fills'])==fills and int(x['retired_records'])==(208 if release else 0),'cache/retirement counts')
   io.need(all(math.isfinite(float(x[k])) and float(x[k])>=0 for k in ['request_wall_ms','shared_validate_ms','pipeline_wall_ms' if hw else 'compute_sum_ms']) and float(x['request_wall_ms'])>0,'invalid elapsed time')
   rr=resource[i];io.need(rr['repetition']==i and rr['warmup']==int(warm) and all(isinstance(a,(int,float)) and math.isfinite(a) and a>=0 for a in rr['process_metrics'].values()),'process metrics')
   if hw:io.need(rr['export_only']==int(ex) and float(x['request_wall_ms'])+.02>=float(x['shared_validate_ms'])+float(x['pipeline_wall_ms']),'export tag or missing measured work')
   if not warm:values.append(float(x['request_wall_ms']));computes.append(float(x['compute_sum_ms'])) if not hw else None
  ss=io.load(p/'summary.json');io.need(ss['layout']==ident['layout'] and ss['cache_policy']==ident['cache_policy'],'phase config')
  if hw:
   io.need(ss['execution_backend']==v['execution_backend'] and ss['AIE_compute_tiles']==v['AIE_compute_tiles'],'software model is not board evidence')
   io.need(ss['phase']==('export' if ex else 'measure') and ss['export_replays']==int(ex) and ss['measured']==(0 if ex else n) and ss['warmups']==(0 if ex else w),'split phase contract')
   near(ss['export_full_recompute_ms'],values[0] if ex else 0);near(ss['request_wall_median_ms'],0 if ex else statistics.median(values));trace_check(p,ident)
   if not ex:io.need(not list((p/'outputs').rglob('*_output.bin')),'measurement phase performed output export')
  else:io.need(ss['execution_backend']=='ARM_CPU_2_THREADS' and ss['measured']==n and ss['warmups']==w,'CPU benchmark');near(ss['request_wall_median_ms'],statistics.median(values));near(ss['compute_sum_median_ms'],statistics.median(computes))
  result[phase]=dict(request_wall_median_ms=statistics.median(values),all_formal_request_ms=[] if ex else values,resources=resource)
  if computes:result[phase]['compute_sum_median_ms']=statistics.median(computes)
 cpu=[result[p]['request_wall_median_ms'] for p in ['cpu_before','cpu_after']];h=result['hardware']['request_wall_median_ms'];drift=100*(cpu[1]/cpu[0]-1);cd=100*(result['cpu_after']['compute_sum_median_ms']/result['cpu_before']['compute_sum_median_ms']-1);review=abs(drift)>5 or abs(cd)>5;eligible=ident['kind']=='formal' and n>=3 and w>=1 and not review;outputs=verify_outputs(folder,Path(ident['data_path']))
 result['hardware']['export_full_recompute_ms']=result['hardware_export']['request_wall_median_ms']
 answer=dict(status='PASS_WINDOW_V2_SPLIT_EXPORT_PENDING_GROUND_RETURN',protocol=ident['protocol'],phase_order=ident['phase_order'],variant=ident['variant'],AIE_compute_tiles=v['AIE_compute_tiles'],layout=ident['layout'],cache_policy=ident['cache_policy'],phases=result,CPU_request_drift_percent=drift,CPU_compute_drift_percent=cd,review_required=review,performance_comparison_eligible=eligible,speedups_vs_adjacent_CPU_request=[c/h for c in cpu] if eligible else None,diagnostic_request_ratios_only=[c/h for c in cpu],actual_output_files=len(outputs),actual_outputs=outputs,scope='Same six-group verified rawMAC. CPU-before, hardware measurement-only, CPU-after, then separate export-only process. No export or export-only retirement between measured CPU samples. Setup/export separate; no forced global cache state; host envelopes are not device cycles. Smoke/CPU-drift runs cannot substantiate speedup. Actual ground return pending.')
 if emit:io.write_json(folder/'comparison.json',answer)
 return answer

def run(kind,layout,policy,reverse=False):
 base.board()
 with base.device_lock():
  code=check();env=base.environment();variant=detected(env);io.need(variant,'wrong boot image');v=registry()[variant];build=checked_build(code);admission=memory_admission.assess(env['meminfo'],os.sysconf('SC_PAGE_SIZE'));n,w=(1,0) if kind=='smoke' else (3,1);order='ascending' if reverse else 'descending';folder=ROOT/f'results_window_v2_{variant}_{layout}_{policy}_{kind}_{base.stamp()}';folder.mkdir();io.write_json(folder/'environment_before.json',env)
  phases=['cpu_before','hardware','cpu_after','hardware_export'];identity=dict(**code,variant=variant,AIE_compute_tiles=v['AIE_compute_tiles'],data_path=str(base.data()),protocol='hs4_window_v2_split_export',phase_order=phases,kind=kind,layout=layout,cache_policy=policy,order=order,repetitions=n,warmups=w,build_identity=build,boot_id=env['boot_id'],boot_uuid=env['boot_uuid'],memory_admission=admission);io.write_json(folder/'run_identity.json',identity)
  events=[]
  def execute(args,name):
   event=dict(phase=name,begin_monotonic_ns=time.monotonic_ns(),end_monotonic_ns=None,completed=False);events.append(event);io.write_json(folder/'phase_events.json',events)
   try:base.command(args,folder,name);event['completed']=True
   finally:event['end_monotonic_ns']=time.monotonic_ns();io.write_json(folder/'phase_events.json',events)
  try:
   binary='window_host_pl' if v['AIE_compute_tiles']==0 else 'window_host_aie';xb=ROOT/'variants'/variant/'ckks_hw_boot.xclbin'
   execute([ROOT/'bin/window_cpu',base.data(),folder/'cpu_before',n,w,order,layout,policy],'cpu_before')
   io.write_json(folder/'environment_before_hardware.json',base.environment())
   execute([ROOT/'bin'/binary,xb,base.data(),folder/'hardware',n,w,order,layout,policy,'measure'],'hardware')
   execute([ROOT/'bin/window_cpu',base.data(),folder/'cpu_after',n,w,order,layout,policy],'cpu_after')
   after=base.environment();io.need(after['boot_id']==env['boot_id'] and after['boot_uuid']==env['boot_uuid'],'boot changed');io.write_json(folder/'environment_after_measurement.json',after)
   execute([ROOT/'bin'/binary,xb,base.data(),folder/'hardware_export',1,0,order,layout,policy,'export'],'hardware_export')
   after=base.environment();io.need(after['boot_id']==env['boot_id'] and after['boot_uuid']==env['boot_uuid'],'boot changed during export');io.write_json(folder/'environment_after.json',after);out=summarize(folder);io.write_json(folder/'status.json',dict(status=out['status'],cryptographic_return='PENDING_ACTUAL_OUTPUT_GROUND_VERIFICATION'));print(json.dumps({k:a for k,a in out.items() if k!='actual_outputs'},indent=2))
  except BaseException as e:io.write_json(folder/'status.json',dict(status='FAILED_OR_INTERRUPTED_RETAIN_ALL',error=str(e)));raise
  finally:print('RESULTS='+str(folder),flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['check','code-check','record-build','detect','smoke','formal','summarize']);p.add_argument('layout',nargs='?',default='chunk');p.add_argument('policy',nargs='?',default='export_bounded');p.add_argument('--reverse',action='store_true');a=p.parse_args()
 if a.action=='check':print(json.dumps(check(),indent=2))
 elif a.action=='code-check':print(json.dumps(check_code(),indent=2))
 elif a.action=='record-build':record_build()
 elif a.action=='detect':base.board();check_code();e=base.environment();print(json.dumps(dict(matching_variant=detected(e),variants=registry(),environment=e),indent=2))
 elif a.action=='summarize':print(json.dumps(summarize(a.layout),indent=2))
 else:io.need(a.layout in ['group','chunk'] and a.policy in ['retain','bounded','export_bounded'],'invalid layout/cache policy');run(a.action,a.layout,a.policy,a.reverse)
if __name__=='__main__':
 try:main()
 except Exception as e:print('FAIL:',e,file=sys.stderr);sys.exit(1)
