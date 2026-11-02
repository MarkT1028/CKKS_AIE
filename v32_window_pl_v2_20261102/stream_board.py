"""Board-only streamed fixture experiments. Original v32/keys stay on local PC."""
from pathlib import Path
import argparse,csv,json,math,os,queue,statistics,subprocess,sys,threading,time
import compact_io as io,full_board as base,memory_admission
ROOT=Path(__file__).resolve().parent
BINARIES=('full_cpu','full_host','full_parser','stream_cpu','stream_host','stream_parser')
def rows(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def near(a,b):io.need(abs(float(a)-float(b))<.01,'raw CSV aggregate mismatch')
def record_build():
 base.board();identity=dict(code_manifest_sha256=io.sha(ROOT/'SHA256SUMS_PACKAGE'),architecture='aarch64',binaries={n:io.sha(ROOT/'bin'/n) for n in BINARIES},compiler=subprocess.check_output(['g++','--version'],text=True),flags='-O3 -std=c++17 -pthread; stream_host -I/usr/include/xrt -lxrt_coreutil',utc=base.stamp());io.write_json(ROOT/'bin/stream_build_identity.json',identity)
def checked_build(code):
 build=io.load(ROOT/'bin/stream_build_identity.json');io.need(build['code_manifest_sha256']==code['manifest_sha256'] and build['architecture']=='aarch64' and set(build['binaries'])==set(BINARIES),'rebuild streamed binaries')
 for name,h in build['binaries'].items():
  p=ROOT/'bin'/name;io.need(io.sha(p)==h,'changed binary '+name)
  with p.open('rb') as f:header=f.read(20)
  io.need(header[:6]==b'\x7fELF\x02\x01' and header[18:20]==b'\xb7\x00','ARM64 binary required '+name)
 return build
def command(args,folder,name,input_text=None):
 started=time.monotonic();record=dict(command=list(map(str,args)),utc=base.stamp(),returncode=None);messages=queue.Queue();env=dict(os.environ,XRT_INI_PATH=str(ROOT/'configs/baseline.ini'),PYTHONDONTWRITEBYTECODE='1');child=None
 try:
  with (folder/(name+'.log')).open('w',encoding='utf-8') as log:
   child=subprocess.Popen(list(map(str,args)),cwd=ROOT,env=env,stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1);record['pid']=child.pid
   if input_text is not None:child.stdin.write(input_text);child.stdin.close()
   def read():
    try:
     for line in child.stdout:messages.put(line)
    finally:messages.put(None)
   reader=threading.Thread(target=read,daemon=True);reader.start();ended=False
   while not ended:
    if time.monotonic()-started>3600:child.kill();raise TimeoutError('Own experiment child exceeded3600s; retain folder')
    try:line=messages.get(timeout=.2)
    except queue.Empty:continue
    if line is None:ended=True
    else:log.write(line);log.flush();print(line,end='',flush=True)
   record['returncode']=child.wait(timeout=30);reader.join(timeout=30);io.need(record['returncode']==0,'Stage failed '+name+'; preserve '+str(folder))
 finally:
  if child is not None and child.poll() is None:child.kill();child.wait()
  record['process_wall_seconds_including_setup_export_and_log_flush']=time.monotonic()-started;io.write_json(folder/(name+'.command.json'),record)
def verify_outputs(root):
 manifest=io.load(base.data()/'DATA_MANIFEST.json');seen=[]
 for g in range(6):
  for i in range(16):
   p=root/'outputs'/f'group_{g}/chunk_{i}_output.bin';ref=f'group_{g}/chunks/chunk_{i}_expected.bin';h=io.sha(p);io.need(h==manifest[ref]['sha256'],'stream output mismatch '+str(p));seen.append(dict(group=g,chunk=i,sha256=h,bytes=p.stat().st_size))
 return seen
def check_trace(root):
 groups=rows(root/'groups.csv');timeline=rows(root/'timeline.csv');checked=0
 for row in groups:
  selected=[r for r in timeline if r['repetition']==row['repetition'] and r['group']==row['group']];previous=[]
  for i in range(16):
   ss=[x for x in selected if int(x['chunk'])==i];io.need(len(ss)==22+int(row['export_only']) and all(int(x['bank'])==i%2 for x in ss),'incomplete stream trace/wrong bank')
   for x in ss:io.need(0<=float(x['begin_ms'])<=float(x['end_ms'])<=float(row['group_wall_ms'])+.01,'stream trace outside group wall')
   for x,y in zip(ss,ss[1:]):io.need(float(x['end_ms'])<=float(y['begin_ms'])+.01,'stream same-frame overlap')
   ex=next(x for x in ss if x['stage']=='execute');st=next(x for x in ss if x['stage']=='status');finish=next(x for x in ss if x['stage']=='merge_poison')
   if i:io.need(float(ex['begin_ms'])+.01>=float(previous[-1]['status']['end_ms']) and float(ex['begin_ms'])<=float(previous[-1]['finish']['begin_ms'])+.01,'stream launch/status/finish order')
   if i>=2:io.need(float(ss[0]['begin_ms'])+.01>=float(previous[-2]['done']['end_ms']),'stream bank reused before verification/export')
   previous.append(dict(status=st,finish=finish,done=ss[-1]));checked+=1
 return checked
def summarize(folder,emit=True):
 folder=Path(folder);ident=io.load(folder/'run_identity.json');n,w=ident['repetitions'],ident['warmups'];out={};expected_order=list(range(6)) if ident['order']=='ascending' else list(range(5,-1,-1))
 for phase in ('cpu_before','hardware','cpu_after'):
  p=folder/phase;hardware=phase=='hardware';its=rows(p/'iterations.csv');gs=rows(p/'groups.csv');resource=[json.loads(s) for s in (p/'resources.jsonl').read_text().splitlines()];io.need(len(its)==n+w+int(hardware) and len(resource)==len(its),'stream repetition/resource count');values=[];computes=[];shared=[];anon=[]
  for rep,it in enumerate(its):
   warm=int(it['warmup']);ex=int(it['export_only']);io.need(int(it['repetition'])==rep and warm==int(rep<w) and ex==int(hardware and rep==n+w) and int(it['groups'])==6 and int(it['verified_words'])==33030144,'stream tags/coverage')
   group=[x for x in gs if int(x['repetition'])==rep];io.need([int(x['group']) for x in group]==expected_order and [int(x['ordinal']) for x in group]==list(range(6)) and all(int(x['verified_words'])==5505024 and int(x['warmup'])==warm for x in group),'stream group order/coverage')
   near(sum(float(x['group_wall_ms']) for x in group),it['group_wall_sum_ms']);near(sum(float(x['pack_work_ms']) for x in group),it['pack_work_sum_ms']);near(sum(float(x['verify_work_ms']) for x in group),it['verify_work_sum_ms']);io.need(float(it['request_wall_ms'])+.01>=float(it['shared_validate_ms'])+float(it['group_wall_sum_ms']),'shared/input work excluded from request wall')
   if hardware:io.need(all(int(x['export_only'])==ex for x in group),'stream export group tags');near(sum(float(x['execute_envelope_sum_ms']) for x in group),it['execute_envelope_sum_ms'])
   else:near(sum(float(x['compute_ms']) for x in group),it['compute_sum_ms'])
   rs=resource[rep];io.need(int(rs['repetition'])==rep and int(rs['warmup'])==warm,'stream resource tags');io.need(all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in rs['process_metrics'].values()),'invalid process metrics')
   if not warm and not ex:values.append(float(it['request_wall_ms']));shared.append(float(it['shared_validate_ms']));anon.append(rs['process_metrics']['RssAnon_kib']);computes.append(float(it['compute_sum_ms'])) if not hardware else None
  io.need(len(values)==n,'stream measured count');summary=io.load(p/'summary.json');near(statistics.median(values),summary['request_wall_median_ms']);out[phase]=dict(measured=n,request_wall_median_ms=statistics.median(values),request_wall_samples_ms=values,shared_validate_median_ms=statistics.median(shared),max_formal_RssAnon_kib=max(anon),resources=resource)
  if computes:near(statistics.median(computes),summary['compute_sum_median_ms']);out[phase]['compute_sum_median_ms']=statistics.median(computes)
 hw=out['hardware']['request_wall_median_ms'];cpu=[out[k]['request_wall_median_ms'] for k in ('cpu_before','cpu_after')];drift=100*(cpu[1]/cpu[0]-1);compute_drift=100*(out['cpu_after']['compute_sum_median_ms']/out['cpu_before']['compute_sum_median_ms']-1);outputs=verify_outputs(folder/'hardware');trace=check_trace(folder/'hardware')
 io.need(io.load(folder/'hardware/summary.json')['execution_backend']=='XRT_AIE','software model is NOT board evidence')
 result=dict(status='PASS_STREAM_SIX_GROUPS_PENDING_GROUND_RETURN',protocol='stream_request_v1',capture_id=ident['data']['capture_id'],phases=out,speedups_vs_adjacent_CPU_request=[x/hw for x in cpu],CPU_request_drift_percent=drift,CPU_compute_drift_percent=compute_drift,review_required=abs(drift)>5 or abs(compute_drift)>5,actual_output_files=len(outputs),actual_outputs=outputs,trace_chunks_checked=trace,scope='Request includes shared validation, mapped pack/faults, hardware transfers and full verification. Setup and separate export retained. mmap file RSS can be large; do not label0 whole-group heap as0 totalRAM. Not full original h_s.4 live end-to-end latency.')
 if emit:io.write_json(folder/'comparison.json',result)
 return result
def run(kind,reverse=False):
 base.board()
 with base.device_lock():
  code=base.check(True);env=base.environment();io.need(env['boot_uuid']==base.UUID,'wrong boot UUID');admission=memory_admission.assess(env['meminfo'],os.sysconf('SC_PAGE_SIZE'));build=checked_build(code);n,w=(1,0) if kind=='smoke' else (3,1);folder=ROOT/('results_stream_'+kind+'_'+base.stamp());folder.mkdir();io.write_json(folder/'environment_before.json',env);io.write_json(folder/'run_identity.json',dict(**code,protocol='stream_request_v1',kind=kind,repetitions=n,warmups=w,order='ascending' if reverse else 'descending',build_identity=build,boot_id=env['boot_id'],boot_uuid=env['boot_uuid'],memory_admission=admission,original_v32_location='LOCAL_PC_NOT_REMOTE_WINDOWS',scope='Actual FPGA streamed fixture test; no original v32/OpenFHE execution on remote Windows.'))
  try:
   order='ascending' if reverse else 'descending';command([ROOT/'bin/stream_cpu',base.data(),folder/'cpu_before',n,w,order],folder,'cpu_before');io.write_json(folder/'environment_before_hardware.json',base.environment());command([ROOT/'bin/stream_host',ROOT/'variants/v32_core_2_pipe/ckks_hw_boot.xclbin',base.data(),folder/'hardware',n,w,order],folder,'hardware');command([ROOT/'bin/stream_cpu',base.data(),folder/'cpu_after',n,w,order],folder,'cpu_after');after=base.environment();io.need(after['boot_id']==env['boot_id'] and after['boot_uuid']==base.UUID,'boot changed');io.write_json(folder/'environment_after.json',after);result=summarize(folder);io.write_json(folder/'status.json',dict(status=result['status'],cryptographic_layer_return='PENDING_DOWNLOAD_AND_GROUND_VERIFICATION'));print(json.dumps({k:v for k,v in result.items() if k!='actual_outputs'},indent=2))
  except BaseException as e:io.write_json(folder/'environment_on_failure.json',base.environment());io.write_json(folder/'status.json',dict(status='FAILED_OR_INTERRUPTED_RETAIN_ALL',error=str(e)));raise
  finally:print('RESULTS='+str(folder),flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['check','code-check','record-build','detect','smoke','formal','summarize']);p.add_argument('folder',nargs='?');p.add_argument('--reverse',action='store_true');a=p.parse_args()
 if a.action=='check':print(json.dumps(base.check(True),indent=2))
 elif a.action=='code-check':print(json.dumps(base.check_code(),indent=2))
 elif a.action=='record-build':record_build()
 elif a.action=='detect':base.board();env=base.environment();print(json.dumps(dict(matching_variant='v32_core_2_pipe' if env['boot_uuid']==base.UUID else None,expected_boot_uuid=base.UUID,environment=env),indent=2))
 elif a.action=='summarize':io.need(a.folder,'result folder required');print(json.dumps(summarize(a.folder),indent=2))
 else:run(a.action,a.reverse)
if __name__=='__main__':
 try:main()
 except Exception as e:print('FAIL:',e,file=sys.stderr);sys.exit(1)
