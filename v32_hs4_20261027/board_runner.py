#!/usr/bin/env python3
"""Board replay orchestrator; never changes firmware, registers or CPU policy."""
from pathlib import Path
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
import record_io as records
ROOT=Path(__file__).resolve().parent

def write(path,data):path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def stamp():return dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def read(path):
    try:return Path(path).read_text().strip().rstrip('\0')
    except OSError:return None
def require(test,message):
    if not test:raise RuntimeError(message)

def check():
    manifest=ROOT/'SHA256SUMS_PACKAGE';expected=[]
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1);p=Path(name)
        require(len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'manifest digest')
        require(not p.is_absolute() and p.parts and all(x not in ('.','..') for x in p.parts) and '\\' not in name and ':' not in name,'unsafe manifest path')
        target=ROOT/p
        require(target.is_file() and not target.is_symlink() and ROOT in target.resolve().parents,'missing/unsafe file: '+name)
        require(all(not parent.is_symlink() for parent in target.parents if parent!=ROOT.parent),'symlink in manifest path')
        require(records.sha(target)==digest,'SHA256 mismatch: '+name)
        expected.append(name)
    require(len(set(expected))==len(expected),'duplicate manifest path')
    status=json.loads((ROOT/'PACKAGE_STATUS.json').read_text())
    require(status['status']=='OFFLINE_VERIFIED_READY_FOR_BOARD' and status['board_tested'] is False,'package readiness state')
    require(sorted(expected)==status['expected_manifest_members'],'manifest member list differs from frozen package inventory')
    coverage=records.inspect_fixture(ROOT/'fixture',canonical=False)
    result=dict(status='PASS_REAL_V32_PACKAGE',files=len(expected),manifest_sha256=records.sha(manifest),
                full_N=coverage['shape']['N'],active_L=coverage['shape']['L'],K=coverage['shape']['K'],
                chunks=coverage['chunks'],firmware_changed=False)
    print(json.dumps(result,indent=2),flush=True)
    return status

def environment():
    return dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),kernel=platform.uname()._asdict(),
                boot_id=read('/proc/sys/kernel/random/boot_id'),boot_uuid=read('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid'),
                model=read('/sys/firmware/devicetree/base/model'),affinity=sorted(os.sched_getaffinity(0)),
                loadavg=read('/proc/loadavg'),meminfo=read('/proc/meminfo'),cpu_policy={p.name:read(p) for p in Path('/sys/devices/system/cpu/cpufreq/policy0').glob('scaling_*')},
                thermal={str(p):read(p) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')})

def board():
    require(platform.machine()=='aarch64','Run hardware commands on VEK280 ARM Linux; PC/WSL timing is not board performance')
    require('vek280' in (read('/sys/firmware/devicetree/base/model') or '').lower(),'Expected VEK280 model')

def detect():
    board();info=environment();matches=[]
    for p in (ROOT/'variants').glob('*/EXPECTED_BOOT_UUID'):
        if read(p)==info['boot_uuid']:matches.append(p.parent.name)
    print(json.dumps(dict(boot_uuid=info['boot_uuid'],matching_variants=matches,environment=info),indent=2))
    return matches

def record_build():
    board()
    binaries={name:records.sha(ROOT/'bin'/name) for name in ['tiled_host','tiled_cpu']}
    write(ROOT/'bin/build_identity.json',dict(package_manifest_sha256=records.sha(ROOT/'SHA256SUMS_PACKAGE'),
          binaries=binaries,architecture=platform.machine(),compiler=subprocess.check_output(['g++','--version'],text=True),
          flags='-O3 -std=c++17 -pthread; host additionally -I/usr/include/xrt -lxrt_coreutil',
          created_utc=dt.datetime.now(dt.timezone.utc).isoformat()))

def command(cmd,log):
    with log.open('w') as f:
        proc=subprocess.run(list(map(str,cmd)),cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    require(proc.returncode==0,'Command failed; inspect '+str(log))
    print(log.read_text(),end='',flush=True)

class Telemetry:
    def __init__(self,path):self.path=path;self.stop=threading.Event();self.samples=[]
    def poll(self):
        while not self.stop.is_set():self.samples.append(environment());self.stop.wait(.5)
    def __enter__(self):self.thread=threading.Thread(target=self.poll,daemon=True);self.thread.start();return self
    def __exit__(self,*exc):self.stop.set();self.thread.join();write(self.path,self.samples)

def run(mode):
    status=check();board()
    marker=read('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid')
    require(marker==status['expected_boot_uuid'],'Boot v32_diag_2_pipe before replay; run detect and the supplied switch check')
    binaries=[ROOT/'bin'/x for x in ['tiled_host','tiled_cpu']]
    for binary in binaries:require(binary.is_file(),'Build first: '+str(binary))
    identity=json.loads((ROOT/'bin/build_identity.json').read_text())
    require(identity['package_manifest_sha256']==records.sha(ROOT/'SHA256SUMS_PACKAGE'),'Binaries belong to an older source package; rebuild')
    for binary in binaries:require(records.sha(binary)==identity['binaries'][binary.name],'Built binary changed: '+str(binary))
    lock=(ROOT/'.board.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require(not (ROOT/'xrt.ini').exists(),'Unexpected root xrt.ini may change diagnostics/performance')
    os.environ.pop('XRT_INI_PATH',None)
    active=sorted(os.sched_getaffinity(0));require(len(active)>=2,'Two CPU cores must be available')
    os.sched_setaffinity(0,set(active[:2]))
    directory=ROOT/f'results_real_v32_{mode}_{stamp()}'
    directory.mkdir(exist_ok=False);write(directory/'environment_before.json',environment())
    write(directory/'run_identity.json',dict(mode=mode,package_manifest_sha256=records.sha(ROOT/'SHA256SUMS_PACKAGE'),
         source_capture=json.loads((ROOT/'fixture/capture_provenance.json').read_text()),scope='single real h_s.4 raw MAC, full ring and active RNS towers',
         excluded='PC export/network/import/relinearization and rest of v32 inference',profiling=False))
    try:
        with Telemetry(directory/'telemetry.json'):
            if mode=='formal':
                command([binaries[1],ROOT/'fixture',directory/'cpu2_before',3,1,2,'nosave'],directory/'cpu2_before.log')
            command([binaries[0],ROOT/'variants/v32_diag_2_pipe/ckks_hw_boot.xclbin',ROOT/'fixture',directory/'hardware',
                     1 if mode=='smoke' else 5,0 if mode=='smoke' else 1],directory/'hardware.log')
            if mode=='formal':
                command([binaries[1],ROOT/'fixture',directory/'cpu2_after',3,1,2,'nosave'],directory/'cpu2_after.log')
        write(directory/'environment_after.json',environment())
        summary=json.loads((directory/'hardware/summary.json').read_text());write(directory/'status.json',dict(status='PASS_REAL_V32_BOARD_RAW_REPLAY',summary=summary,
             remaining='Return this folder for original-context integer/relinearization/decryption/continuation verification'))
    except BaseException as exc:
        write(directory/'status.json',dict(status='FAILED_OR_INTERRUPTED',error=repr(exc)));raise
    print('RESULTS='+str(directory),flush=True)
    print('NEXT: python3 collect_results.py',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','detect','record-build','smoke','formal']);a=p.parse_args()
    if a.action=='check':check()
    elif a.action=='detect':detect()
    elif a.action=='record-build':record_build()
    else:run(a.action)
if __name__=='__main__':
    try:main()
    except Exception as exc:print('FAIL:',exc,file=sys.stderr);raise SystemExit(1)
