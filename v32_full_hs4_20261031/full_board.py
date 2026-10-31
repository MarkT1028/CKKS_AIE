"""Full-layer raw-MAC board orchestration; never writes boot media/registers."""
from pathlib import Path
from contextlib import contextmanager
import argparse,csv,datetime,hashlib,json,os,platform,statistics,struct,subprocess,sys,time
import compact_io as io
ROOT=Path(__file__).resolve().parent;UUID='050ea5cc23fb5038bad0aca23cbd240b';BASE_SHA='db3bcc84a5cd925868e476ba2e6a2a4feb56fd4806fd3344a5f9940aba999d3b'
def stamp():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def data():return Path(os.environ.get('V32_HS4_DATA',str(ROOT.parent/'v32_full_hs4_20261031_data'))).resolve()
def base():return Path(os.environ.get('V32_BASE_PACKAGE',str(ROOT.parent/'v32_hs4_20261027'))).resolve()
def board():
 io.need(platform.machine()=='aarch64','Run hardware/build/detect on VEK280 ARM Linux, not this PC')
 io.need('vek280' in Path('/sys/firmware/devicetree/base/model').read_text().lower(),'VEK280 model required')
def text(p):
 try:return Path(p).read_text().strip().rstrip('\0')
 except OSError:return None
def environment():
 p=Path('/sys/devices/system/cpu/cpufreq/policy0');return dict(utc=stamp(),boot_id=text('/proc/sys/kernel/random/boot_id'),boot_uuid=text('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid'),kernel=platform.uname()._asdict(),affinity=sorted(os.sched_getaffinity(0)),loadavg=text('/proc/loadavg'),meminfo=text('/proc/meminfo'),cpu_policy={x.name:text(x) for x in p.glob('scaling_*')},thermal={str(x):text(x) for x in Path('/sys/class/thermal').glob('thermal_zone*/temp')})
def check_code():
 manifest=ROOT/'SHA256SUMS_PACKAGE';io.need(manifest.is_file(),'code package not sealed')
 names={}
 for line in manifest.read_text(encoding='utf-8').splitlines():
  h,n=line.split('  ',1);p=io.safe(ROOT,n);io.need(p.is_file() and io.sha(p)==h,'code checksum: '+n);io.need(n not in names,'duplicate code manifest');names[n]=h
 io.need(io.load(ROOT/'PACKAGE_STATUS.json')['status']=='OFFLINE_VERIFIED_FULL_HS4_MEAN_READY_FOR_BOARD','package not ready')
 return dict(status='PASS_FULL_HS4_CODE_PACKAGE',files=len(names),manifest_sha256=io.sha(manifest),firmware_changed=False)
def check(full_data=True):
 c=check_code();d=io.verify_data(data(),full=full_data,production=True);io.need(d['manifest_sha256']==io.load(ROOT/'PACKAGE_STATUS.json')['data_manifest_sha256'],'wrong full-layer data capture: use this release matching data archive');return dict(**c,data=d,board_performance='PENDING',ground_layer_verification='PENDING_ACTUAL_OUTPUTS')
def record_build():
 board();rows={n:io.sha(ROOT/'bin'/n) for n in ('full_cpu','full_host','full_parser')};io.write_json(ROOT/'bin/build_identity.json',dict(code_manifest_sha256=io.sha(ROOT/'SHA256SUMS_PACKAGE'),binaries=rows,architecture=platform.machine(),compiler=subprocess.check_output(['g++','--version'],text=True),flags='-O3 -std=c++17 -pthread; host -I/usr/include/xrt -lxrt_coreutil',utc=stamp()))
@contextmanager
def device_lock():
 import fcntl
 b=base();io.need((b/'SHA256SUMS_PACKAGE').is_file() and io.sha(b/'SHA256SUMS_PACKAGE')==BASE_SHA,'same original base required for cross-package board lock; set V32_BASE_PACKAGE')
 with (b/'.board.lock').open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError('Another CKKS experiment owns the board; do not run in parallel')
  yield
def command(args,where,name):
 start=time.monotonic();ident=dict(command=list(map(str,args)),utc=stamp(),returncode=None)
 try:
  env=dict(os.environ,XRT_INI_PATH=str(ROOT/'configs/baseline.ini'),PYTHONDONTWRITEBYTECODE='1')
  with (where/(name+'.log')).open('w') as f:
   p=subprocess.run(list(map(str,args)),cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=3600)
  ident['returncode']=p.returncode;io.need(p.returncode==0,'Stage failed: '+name+'; preserve folder and read log')
 finally:ident['wall_seconds_including_process']=time.monotonic()-start;io.write_json(where/(name+'.command.json'),ident)
 print((where/(name+'.log')).read_text(),end='',flush=True)
def rows(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def near(a,b):io.need(abs(float(a)-float(b))<.003,'stored aggregate differs from raw CSV')
def summarize(folder,emit=True):
 folder=Path(folder);ident=io.load(folder/'run_identity.json');n,w=ident['repetitions'],ident['warmups'];out={};capture=ident['data']['capture_id']
 for phase in ('cpu_before','hardware','cpu_after'):
  root=folder/phase;whole=rows(root/'iterations.csv');gs=rows(root/'groups.csv');hardware=phase=='hardware';io.need(len(whole)==n+w+int(hardware),'wrong replay count');values=[];computes=[];residents=[];admissions=[]
  for rep,it in enumerate(whole):
   warm=int(it['warmup']);export=int(it['export_only']) if hardware else 0;io.need(int(it['repetition'])==rep and warm==int(rep<w) and export==int(hardware and rep==n+w),'wrong warmup/export tags')
   group=[x for x in gs if int(x['repetition'])==rep];expected=list(range(6)) if ident['order']=='ascending' else list(range(5,-1,-1));io.need([int(x['group']) for x in group]==expected and [int(x['ordinal']) for x in group]==list(range(6)),'missing/duplicate/reordered group');io.need(all(int(x['warmup'])==warm for x in group),'group warmup differs')
   if hardware:io.need(all(int(x['export_only'])==export for x in group),'group export differs')
   io.need(all(int(x['verified_words'])==5505024 for x in group) and int(it['verified_words'])==33030144,'not all six full outputs verified');near(sum(float(x['admission_ms']) for x in group),it['admission_sum_ms'])
   if hardware:near(sum(float(x['resident_verified_wall_ms']) for x in group),it['resident_wall_sum_ms']);near(sum(float(x['host_execute_envelope_sum_ms']) for x in group),it['host_execute_envelope_sum_ms'])
   else:near(sum(float(x['compute_ms']) for x in group),it['compute_sum_ms']);near(sum(float(x['verified_call_ms']) for x in group),it['verified_call_sum_ms']);near(sum(float(x['resident_verified_wall_ms']) for x in group),it['resident_wall_sum_ms'])
   if not warm and not export:values.append(float(it['full_six_streamed_wall_ms']));residents.append(float(it['resident_wall_sum_ms']));admissions.append(float(it['admission_sum_ms']));computes.append(float(it['compute_sum_ms'])) if not hardware else None
  io.need(len(values)==n,'formal sample count');summary=io.load(root/'summary.json');near(statistics.median(values),summary['full_six_streamed_wall_median_ms'])
  near(statistics.median(residents),summary['resident_verified_wall_sum_median_ms']);out[phase]=dict(measured=n,full_six_streamed_wall_median_ms=statistics.median(values),all_formal_wall_ms=values,resident_verified_wall_sum_median_ms=statistics.median(residents),all_formal_resident_sum_ms=residents,admission_sum_median_ms=statistics.median(admissions))
  if computes:near(statistics.median(computes),summary['compute_sum_median_ms']);out[phase]['compute_sum_median_ms']=statistics.median(computes)
 # Exact saved raw bytes are tied to THIS capture/data manifest, never older output.
 outputs=[]
 for g in range(6):
  for i in range(16):
   p=folder/'hardware/outputs'/f'group_{g}'/f'chunk_{i}_output.bin';expected=f'group_{g}/chunks/chunk_{i}_expected.bin';io.need(io.sha(p)==io.load(data()/'DATA_MANIFEST.json')[expected]['sha256'],'actual board output mismatch '+str(p));outputs.append(dict(group=g,chunk=i,sha256=io.sha(p),bytes=p.stat().st_size))
 cpu=[out[x]['full_six_streamed_wall_median_ms'] for x in ('cpu_before','cpu_after')];hw=out['hardware']['full_six_streamed_wall_median_ms'];drift=100*(out['cpu_after']['compute_sum_median_ms']/out['cpu_before']['compute_sum_median_ms']-1)
 full_drift=100*(cpu[1]/cpu[0]-1);resident_drift=100*(out['cpu_after']['resident_verified_wall_sum_median_ms']/out['cpu_before']['resident_verified_wall_sum_median_ms']-1);hw_resident=out['hardware']['resident_verified_wall_sum_median_ms']
 result=dict(status='PASS_RECOMPUTED_SIX_MAC_GROUPS_PENDING_GROUND_LAYER_RETURN',capture_id=capture,phases=out,speedups_vs_adjacent_CPU_full=[x/hw for x in cpu],speedups_vs_adjacent_CPU_resident=[out[x]['resident_verified_wall_sum_median_ms']/hw_resident for x in ('cpu_before','cpu_after')],CPU_compute_drift_percent=drift,CPU_full_streamed_drift_percent=full_drift,CPU_resident_drift_percent=resident_drift,review_required=any(abs(x)>5 for x in (drift,full_drift,resident_drift)),actual_output_files=len(outputs),actual_outputs=outputs,scope='Six streamed raw MACs including data admission; NOT full h_s.4 end-to-end time. Resident sums exclude admission in both CPU and hardware. Setup/export separate; OS page cache not forced, full-stream CPU drift explicitly retained. Host envelopes are not device cycles. No proof of live model acceleration.')
 if emit:io.write_json(folder/'comparison.json',result)
 return result
def run(kind,reverse=False,mode='map_finish_overlap'):
 board()
 with device_lock():
  checked=check(True);before=environment();io.need(before['boot_uuid']==UUID,'boot UUID mismatch; use the existing campaign switch to v32_core_2_pipe; do not force runtime programming')
  for field,limit in [('MemAvailable:',1800*1024),('CmaFree:',160*1024)]:io.need(int(before['meminfo'].split(field)[1].split()[0])>=limit,'insufficient '+field)
  build=io.load(ROOT/'bin/build_identity.json');io.need(build['code_manifest_sha256']==checked['manifest_sha256'] and all(io.sha(ROOT/'bin'/x)==h for x,h in build['binaries'].items()),'rebuild: code/binary identity changed');n,w=(1,0) if kind=='smoke' else (3,1);order='ascending' if reverse else 'descending';folder=ROOT/('results_full_hs4_'+kind+'_'+stamp());folder.mkdir();io.write_json(folder/'environment_before.json',before)
  identity=dict(**checked,kind=kind,repetitions=n,warmups=w,order=order,mode=mode,build_identity=build,boot_id=before['boot_id'],boot_uuid=before['boot_uuid'],utc=stamp(),scope='All six groups from one real complete h_s.4(mean) capture; CPU and hardware use same compact loader and full validation; ground full layer return pending.')
  io.write_json(folder/'run_identity.json',identity)
  try:
   command([ROOT/'bin/full_cpu',data(),folder/'cpu_before',n,w,order],folder,'cpu_before');command([ROOT/'bin/full_host',ROOT/'variants/v32_core_2_pipe/ckks_hw_boot.xclbin',data(),folder/'hardware',n,w,order,mode],folder,'hardware');command([ROOT/'bin/full_cpu',data(),folder/'cpu_after',n,w,order],folder,'cpu_after');after=environment();io.need(after['boot_id']==before['boot_id'] and after['boot_uuid']==UUID,'boot changed during experiment');io.write_json(folder/'environment_after.json',after);result=summarize(folder);io.write_json(folder/'status.json',dict(status=result['status'],cryptographic_layer_return='PENDING_DOWNLOAD_AND_GROUND_VERIFICATION',finished_utc=stamp()));print(json.dumps({k:v for k,v in result.items() if k!='actual_outputs'},indent=2))
  except BaseException as e:io.write_json(folder/'status.json',dict(status='FAILED_OR_INTERRUPTED_RETAIN_ALL',error=str(e),utc=stamp()));raise
  finally:print('RESULTS='+str(folder),flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['check','code-check','data-path','record-build','detect','smoke','formal','summarize']);p.add_argument('folder',nargs='?');p.add_argument('--reverse',action='store_true');p.add_argument('--mode',choices=['map_pingpong','map_finish_overlap'],default='map_finish_overlap');a=p.parse_args()
 if a.action=='check':print(json.dumps(check(True),indent=2))
 elif a.action=='code-check':print(json.dumps(check_code(),indent=2))
 elif a.action=='data-path':print(data())
 elif a.action=='record-build':record_build()
 elif a.action=='detect':board();e=environment();print(json.dumps(dict(matching_variant='v32_core_2_pipe' if e['boot_uuid']==UUID else None,expected_boot_uuid=UUID,environment=e),indent=2))
 elif a.action=='summarize':io.need(a.folder,'result folder required');print(json.dumps(summarize(a.folder),indent=2))
 else:run(a.action,a.reverse,a.mode)
if __name__=='__main__':
 try:main()
 except Exception as e:print('FAIL:',e,file=sys.stderr);sys.exit(1)
