#!/usr/bin/env python3
"""VEK280-only build/run driver. No boot writes, programming or resets here."""
from pathlib import Path, PurePosixPath
import argparse, datetime as dt, hashlib, json, os, platform, re, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parent
VARIANTS=('baseline_1','raw_1_pipe','raw_2_full','raw_2_pipe')
FLAGS=['-std=c++17','-O3','-Wall','-Wextra','-pthread']

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def require(ok,message):
 if not ok:raise RuntimeError(message)
def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(p):
 try:return Path(p).read_text(errors='replace').strip('\x00\r\n')
 except OSError:return None
def check_package(root=ROOT):
 root=Path(root);lines=(root/'SHA256SUMS_PACKAGE').read_text(encoding='utf-8').splitlines();seen=set()
 for line in lines:
  m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(m is not None,'invalid SHA manifest line')
  rel=PurePosixPath(m[2]);require(not rel.is_absolute() and '..' not in rel.parts and m[2] not in seen,'unsafe/duplicate manifest path')
  seen.add(m[2]);p=root.joinpath(*rel.parts)
  require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()),f'missing/unsafe file: {rel}')
  require(sha(p)==m[1],f'SHA mismatch: {rel}')
 for v in VARIANTS:
  d=root/'variants'/v;manifest=json.loads((d/'manifest.json').read_text())
  require(sha(d/'boot0001.bin')==(d/'EXPECTED_BOOT_SHA256').read_text().strip()==manifest['candidate_sha256'],f'{v}: boot identity')
  require((d/'EXPECTED_BOOT_UUID').read_text().strip()==manifest['xclbin_uuid_hex'],f'{v}: UUID identity')
  require(sha(d/'ckks_hw_boot.xclbin')==manifest['metadata_sha256'],f'{v}: metadata identity')
 for name in ['perf_host.cpp','timed_base.hpp','expected_reader.hpp']:
  require(len({sha(root/'variants'/v/'host'/name) for v in VARIANTS})==1,f'common host changed across variants: {name}')
 require(sha(root/'cpu/parser/timed_base.hpp')==sha(root/'variants/baseline_1/host/timed_base.hpp'),'CPU/HW input parser mismatch')
 require(sha(root/'cpu/parser/expected_reader.hpp')==sha(root/'variants/baseline_1/host/expected_reader.hpp'),'CPU/HW expected reader mismatch')
 for name in ['timed_base.hpp','expected_reader.hpp','variant_config.hpp']:
  require(sha(root/'profile_host'/name)==sha(root/'variants/raw_2_pipe/host'/name),'profile/HW header mismatch: '+name)
 return {'status':'PASS_PACKAGE','files':len(seen),'manifest_sha256':sha(root/'SHA256SUMS_PACKAGE'),'firmware_changed':False}
def board_check():
 require(platform.machine()=='aarch64','Expected VEK280 ARM Linux. PC/WSL timings are not board results.')
 require(os.geteuid()==0,'Run as root on the board')
 require('vek280' in (read('/sys/firmware/devicetree/base/model') or '').lower(),'Expected VEK280 device tree')
 require(len(os.sched_getaffinity(0))>=2,'Two online/allowed CPU cores required for the 1/2-thread comparison')
def boot_uuid():return read('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid')
def snapshot():
 data={'utc':stamp(),'kernel':platform.uname()._asdict(),'boot_id':read('/proc/sys/kernel/random/boot_id'),
       'model':read('/sys/firmware/devicetree/base/model'),'boot_uuid':boot_uuid(),'affinity':sorted(os.sched_getaffinity(0)),
       'online_cpus':read('/sys/devices/system/cpu/online'),'loadavg':read('/proc/loadavg'),'cpu_policies':{},'thermal':{}}
 for p in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')):
  data['cpu_policies'][p.name]={n:read(p/n) for n in ['scaling_cur_freq','scaling_governor','scaling_min_freq','scaling_max_freq']}
 for p in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
  data['thermal'][p.name]={'type':read(p/'type'),'temp_millidegC':read(p/'temp')}
 return data
def logged(argv,log,cwd=None,env=None,timeout=300):
 p=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 Path(log).write_text(p.stdout,encoding='utf-8')
 require(p.returncode==0,f'{Path(log).name}: command failed with exit {p.returncode}; inspect saved log')
 return p.stdout
def build(choice):
 check_package();board_check();bin_dir=ROOT/'bin';bin_dir.mkdir(exist_ok=True)
 compiler=subprocess.check_output(['g++','--version'],text=True)
 targets=['cpu']+list(VARIANTS if choice=='all' else [choice])
 for target in targets:
  if target=='cpu':src=ROOT/'cpu/cpu_bench.cpp';sources=[src]+list((ROOT/'cpu/parser').glob('*.hpp'));libs=[];name='cpu_bench'
  else:src=ROOT/'variants'/target/'host/perf_host.cpp';sources=list(src.parent.glob('*.hpp'))+[src];libs=['-lxrt_coreutil'];name='perf_host_'+target
  with tempfile.TemporaryDirectory(prefix='build_',dir=bin_dir) as td:
   temporary=Path(td)/name;command=['g++',*FLAGS,str(src),*libs,'-o',str(temporary)]
   logged(command,bin_dir/(name+'.compile.log'))
   if target=='cpu':logged([temporary,'--self-test'],bin_dir/'cpu_selftest.log')
   ldd=logged(['ldd',temporary],bin_dir/(name+'.ldd.log'))
   destination=bin_dir/name;os.replace(temporary,destination)
   record={'target':target,'built_at_utc':stamp(),'architecture':platform.machine(),'compiler_version':compiler,'flags':FLAGS,
           'libraries':libs,'binary_sha256':sha(destination),'package_manifest_sha256':sha(ROOT/'SHA256SUMS_PACKAGE'),
           'source_files':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(sources)},'linked_libraries':ldd}
   (bin_dir/(name+'.build.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
   print('BUILD_READY='+str(destination),flush=True)
 print('BUILD_READY: CPU self-test passed; no PL/AIE execution, boot write or reset performed.')
def binary_record(name):
 p=ROOT/'bin'/name;record=json.loads((ROOT/'bin'/(name+'.build.json')).read_text())
 require(sha(p)==record['binary_sha256'],f'{name}: binary changed')
 require(record['architecture']=='aarch64' and record['flags']==FLAGS,f'{name}: build settings mismatch')
 require(record['package_manifest_sha256']==sha(ROOT/'SHA256SUMS_PACKAGE'),f'{name}: stale build')
 for n,h in record['source_files'].items():require(sha(ROOT/n)==h,f'{name}: source changed: {n}')
 return record
def run_experiment(variant,reps,session):
 check=check_package();board_check()
 require(re.fullmatch(r'[A-Za-z0-9_-]{1,40}',session) is not None,'session must be a short ASCII label')
 require(1<=reps<=10000,'repetitions outside 1..10000')
 expected=(ROOT/'variants'/variant/'EXPECTED_BOOT_UUID').read_text().strip()
 require(boot_uuid()==expected,f'BOOT_MISMATCH for {variant}; no CPU/hardware test started')
 require(os.environ.get('PERF_PROFILE','none')=='none','Unset PERF_PROFILE for performance comparisons')
 cpu_build=binary_record('cpu_bench');hw_build=binary_record('perf_host_'+variant)
 require(cpu_build['compiler_version']==hw_build['compiler_version'],'CPU and HW host compiler versions differ')
 result=Path(tempfile.mkdtemp(prefix=f'results_fair_{variant}_{session}_',dir=ROOT))
 print('FAIR_RESULTS='+str(result),flush=True)
 metadata={'schema':'ckks_fair_board_v1','status':'RUNNING','variant':variant,'session_label':session,'repetitions':reps,'warmups':3,
           'started_at_utc':stamp(),'scope':'raw_ckks_mac','board_run':True,'new_firmware':False,'package':check,
           'cpu_algorithm':'u128_accumulate_mod_after_sum','cpu_compute_threads':[1,2],
           'timing_boundaries':{'cpu_compute_ms':'integer MAC and modulus; 2-thread dispatch/wait included',
            'cpu_verified_call_ms':'output poison + compute + full verification; input parsing, allocation and thread-pool creation excluded',
            'hardware_execution_ms':'XRT launches, PL/AIE dataflow and completion waits',
            'hardware_transaction_ms':'round upload if transfer + poison + execution + status + readback + merge + verification'},
           'cpu_build':cpu_build,'hardware_host_build':hw_build,
           'fixture_sha256':{p.name:sha(p) for p in sorted((ROOT/'fixtures').glob('*.bin'))},
           'environment_before':snapshot(),'cases':[]}
 def save(): (result/'experiment.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
 save();env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',PERF_PROFILE='none')
 try:
  def run_case(kind,k,threads=None,mode=None):
   input_name='inputs.bin' if k==1 else 'inputs_k16.bin';expected_name='expected_raw.bin' if k==1 else 'expected_k16_raw.bin'
   input_path=ROOT/'fixtures'/input_name;golden=ROOT/'fixtures'/expected_name
   rel=f'{kind}/k{k}_t{threads}' if threads else f'hardware/k{k}_{mode}'
   case=result/rel;case.mkdir(parents=True);before=snapshot()
   if threads:command=[ROOT/'bin/cpu_bench',input_path,golden,case/'host',reps,3,threads]
   else:
    require(boot_uuid()==expected,'Boot UUID changed during the session')
    ini=case/'xrt.ini';ini.write_text('[Debug]\naie_profile=false\naie_trace=false\n',encoding='ascii');env['XRT_INI_PATH']=str(ini)
    command=[ROOT/'bin'/('perf_host_'+variant),ROOT/'variants'/variant/'ckks_hw_boot.xclbin',input_path,golden,case/'host',reps,3,mode,'run']
   log=logged(command,case/'host.log',cwd=case,env=env,timeout=300+120*(reps+3))
   print(log,end='',flush=True)
   output=case/'host/output_last.bin';require(output.read_bytes()==golden.read_bytes(),f'{rel}: saved output differs from golden')
   item={'kind':kind,'K':k,'threads':threads,'mode':mode,'path':rel,'status':'PASS','output_sha256':sha(output),
         'environment_before':before,'environment_after':snapshot()}
   (case/'case.json').write_text(json.dumps(item,indent=2),encoding='utf-8');metadata['cases'].append(item);save()
  for phase in ['cpu_before','hardware','cpu_after']:
   for k in [1,16]:
    if phase=='hardware':
     for mode in ['resident','transfer']:run_case(phase,k,mode=mode)
    else:
     for threads in [1,2]:run_case(phase,k,threads=threads)
  metadata.update(status='PASS_ALL_12_CASES',completed_at_utc=stamp(),environment_after=snapshot());save()
  (result/'STATUS.txt').write_text('PASS_ALL_12_CASES\n',encoding='ascii')
  print('DOWNLOAD_ENTIRE_RESULTS='+str(result),flush=True)
 except Exception as e:
  metadata.update(status='FAIL_STOPPED',error=str(e),environment_after=snapshot());save()
  (result/'STATUS.txt').write_text('FAIL_STOPPED\n',encoding='ascii');raise

def main():
 ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
 sub.add_parser('check');sub.add_parser('detect')
 p=sub.add_parser('build');p.add_argument('variant',nargs='?',default='all',choices=['all',*VARIANTS])
 p=sub.add_parser('run');p.add_argument('variant',choices=VARIANTS);p.add_argument('reps',nargs='?',type=int,default=30);p.add_argument('session',nargs='?',default='round1')
 a=ap.parse_args()
 if a.command=='check':print(json.dumps(check_package(),indent=2));return
 if a.command=='detect':
  check_package();board_check();actual=boot_uuid();matching=[v for v in VARIANTS if (ROOT/'variants'/v/'EXPECTED_BOOT_UUID').read_text().strip()==actual]
  print(json.dumps({'boot_uuid':actual,'matching_variants':matching,'environment':snapshot()},indent=2));return
 if a.command=='build':build(a.variant);return
 if a.command=='run':run_experiment(a.variant,a.reps,a.session)
if __name__=='__main__':
 try:main()
 except Exception as e:print('FAIL: '+str(e),file=sys.stderr);sys.exit(1)
