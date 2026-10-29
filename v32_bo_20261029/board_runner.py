#!/usr/bin/env python3
"""Host-only comparison overlay. Never stages firmware or changes CPU policy."""
from pathlib import Path
import argparse, datetime as dt, fcntl, json, os, platform, subprocess, sys, threading, time
import record_io as records
ROOT=Path(__file__).resolve().parent
BASE_MANIFEST='db3bcc84a5cd925868e476ba2e6a2a4feb56fd4806fd3344a5f9940aba999d3b'
UUID='6719127d5f785a7fa4fab0a9869d6ccd'
BINARIES=('bo_host','cached_cpu','schedule_selftest')
MODES=('copy_serial','map_serial','map_pingpong')
def base():return Path(os.environ.get('V32_BASE_PACKAGE',str(ROOT.parent/'v32_hs4_20261027'))).resolve()
def require(ok,message):
    if not ok:raise RuntimeError(message)
def write(p,data):p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def read(p):
    try:return Path(p).read_text().strip().rstrip('\0')
    except OSError:return None
def stamp():return dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def verify_manifest(root):
    root=root.resolve();names=[]
    for line in (root/'SHA256SUMS_PACKAGE').read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1);p=Path(name)
        require(len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'invalid manifest digest')
        require(not p.is_absolute() and p.parts and all(x not in ('.','..') for x in p.parts) and '\\' not in name and ':' not in name,'unsafe manifest path')
        target=root/p
        require(target.is_file() and root in target.resolve().parents and not any(x.is_symlink() for x in [target,*target.parents] if x!=root.parent),'missing/unsafe file: '+name)
        require(records.sha(target)==digest,'SHA256 mismatch: '+name);names.append(name)
    require(len(names)==len(set(names)),'duplicate manifest member')
    status=json.loads((root/'PACKAGE_STATUS.json').read_text())
    require(sorted(names)==status['expected_manifest_members'],'frozen inventory mismatch')
    return status,len(names)
def check():
    status,n=verify_manifest(ROOT)
    require(status['status']=='OFFLINE_VERIFIED_READY_FOR_BOARD' and status['board_tested'] is False,'invalid overlay readiness state')
    require(base()!=ROOT,'base cannot be the overlay')
    provenance=json.loads((ROOT/'SOURCE_PROVENANCE.json').read_text())
    for name,digest in provenance['frozen_reference_files'].items():require(records.sha(ROOT/name)==digest,'reference source changed: '+name)
    require(records.sha(base()/'SHA256SUMS_PACKAGE')==BASE_MANIFEST,'wrong/missing frozen v32_hs4_20261027 dependency')
    _,old_n=verify_manifest(base())
    coverage=records.inspect_fixture(base()/'fixture',canonical=False)
    require(tuple(coverage['shape'][k] for k in ('N','L','K','chunks'))==(131072,14,16,16),'wrong real v32 fixture')
    require(read(base()/'variants/v32_diag_2_pipe/EXPECTED_BOOT_UUID')==UUID,'dependency UUID mismatch')
    result=dict(status='PASS_BO_OVERLAY',files=n,base_files=old_n,base=str(base()),manifest_sha256=records.sha(ROOT/'SHA256SUMS_PACKAGE'),base_manifest_sha256=BASE_MANIFEST,firmware_changed=False,board_performance='PENDING')
    print(json.dumps(result,indent=2),flush=True);return result
def environment():
    return dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),kernel=platform.uname()._asdict(),boot_id=read('/proc/sys/kernel/random/boot_id'),boot_uuid=read('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid'),model=read('/sys/firmware/devicetree/base/model'),affinity=sorted(os.sched_getaffinity(0)),loadavg=read('/proc/loadavg'),meminfo=read('/proc/meminfo'),cpu_policy={p.name:read(p) for p in Path('/sys/devices/system/cpu/cpufreq/policy0').glob('scaling_*')},thermal={str(p):read(p) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')})
def board():
    require(platform.machine()=='aarch64','Hardware/build commands require VEK280 ARM Linux; PC timings are not board performance')
    require('vek280' in (read('/sys/firmware/devicetree/base/model') or '').lower(),'expected VEK280')
def detect():
    board();e=environment();print(json.dumps(dict(boot_uuid=e['boot_uuid'],matching_variants=['v32_diag_2_pipe'] if e['boot_uuid']==UUID else [],environment=e),indent=2))
def record_build():
    board();write(ROOT/'bin/build_identity.json',dict(package_manifest_sha256=records.sha(ROOT/'SHA256SUMS_PACKAGE'),base_manifest_sha256=BASE_MANIFEST,binaries={n:records.sha(ROOT/'bin'/n) for n in BINARIES},compiler=subprocess.check_output(['g++','--version'],text=True),flags='-O3 -std=c++17 -pthread; host additionally -I/usr/include/xrt -lxrt_coreutil',architecture=platform.machine(),utc=stamp()))
class Telemetry:
    def __init__(self,path):self.path=path;self.stop=threading.Event();self.samples=[]
    def poll(self):
        while not self.stop.is_set():self.samples.append(environment());self.stop.wait(.5)
    def __enter__(self):self.thread=threading.Thread(target=self.poll,daemon=True);self.thread.start();return self
    def __exit__(self,*exc):self.stop.set();self.thread.join();write(self.path,self.samples)
def command(args,log):
    begin=time.monotonic()
    with log.open('w') as f:p=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    wall=(time.monotonic()-begin)*1000
    write(log.with_suffix('.command.json'),dict(command=list(map(str,args)),exit_code=p.returncode,whole_subprocess_wall_ms=wall,scope='includes process startup, one-time admission/setup, warmups, measured iterations and final output saving'))
    print(log.read_text(),end='',flush=True);require(p.returncode==0,'command failed: '+str(log))
def run(kind,reverse=False):
    identity=check();board();require(environment()['boot_uuid']==UUID,'Expected already booted v32_diag_2_pipe; this overlay does not switch/reboot firmware')
    build=json.loads((ROOT/'bin/build_identity.json').read_text());require(build['package_manifest_sha256']==identity['manifest_sha256'],'rebuild: source package changed')
    for n in BINARIES:require(records.sha(ROOT/'bin'/n)==build['binaries'][n],'rebuild: binary changed '+n)
    with (base()/'.board.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not any((d/'xrt.ini').exists() for d in (ROOT,base())),'remove unexpected xrt.ini before controlled run')
        os.environ.pop('XRT_INI_PATH',None)
        active=sorted(os.sched_getaffinity(0));require(len(active)>=2,'two available ARM CPU cores required');os.sched_setaffinity(0,set(active[:2]))
        available=int(environment()['meminfo'].split('MemAvailable:')[1].split()[0]);require(available>=1600*1024,'Need >=1600 MiB MemAvailable for admitted fixture and BO banks')
        cma=int(environment()['meminfo'].split('CmaFree:')[1].split()[0]);require(cma>=160*1024,'Need >=160 MiB CmaFree for two BO banks plus allocation margin')
        directory=ROOT/f'results_bo_{kind}_{stamp()}';directory.mkdir()
        order=list(reversed(MODES)) if reverse else list(MODES)
        write(directory/'run_identity.json',dict(**identity,mode=kind,order=order,build_identity=build,profiling=False,source_capture=json.loads((base()/'fixture/capture_provenance.json').read_text()),scope='same fixed real v32 group; CPU equally cached; hardware uses common new timing framework; primary actual replay wall excludes setup/log writes and a separate export replay; stage work sums overlap and are not wall time; no full-model speedup claim'))
        write(directory/'environment_before.json',environment())
        try:
            with Telemetry(directory/'telemetry.json'):
                for mode in order:
                    folder=directory/mode;folder.mkdir()
                    cpu='cached_cpu'
                    for stage in ('cpu2_before','hardware','cpu2_after'):
                        if stage=='hardware':
                            args=[ROOT/'bin/bo_host',base()/'variants/v32_diag_2_pipe/ckks_hw_boot.xclbin',base()/'fixture',folder/stage,1 if kind=='smoke' else 5,0 if kind=='smoke' else 1,mode]
                        else:args=[ROOT/'bin'/cpu,base()/'fixture',folder/stage,1 if kind=='smoke' else 3,0 if kind=='smoke' else 1,2,'nosave']
                        command(args,folder/(stage+'.log'))
            write(directory/'environment_after.json',environment());write(directory/'status.json',dict(status='PASS_BO_BOARD_COMPARISON',return_for='all three final raw outputs, independent analysis and original-context return verification'))
            command([sys.executable,ROOT/'summarize_results.py',directory],directory/'summary.log')
        except BaseException as exc:
            write(directory/'status.json',dict(status='FAILED_OR_INTERRUPTED',error=repr(exc)));raise
        print('RESULTS='+str(directory));print('NEXT: python3 collect_results.py')
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','base-path','detect','record-build','smoke','formal']);p.add_argument('--reverse',action='store_true');a=p.parse_args()
    if a.action=='check':check()
    elif a.action=='base-path':print(base())
    elif a.action=='detect':detect()
    elif a.action=='record-build':record_build()
    else:run(a.action,a.reverse)
if __name__=='__main__':
    try:main()
    except Exception as exc:print('FAIL:',exc,file=sys.stderr);raise SystemExit(1)
