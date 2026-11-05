"""VEK280 g_a.3 raw MAC campaign. No automatic reset, key material or live model."""
from pathlib import Path
import argparse, contextlib, csv, datetime, hashlib, json, math, os, platform, signal, statistics, struct, subprocess, sys

ROOT=Path(__file__).resolve().parent
VARIANTS=('v32_core_2_pipe','v32_native_pl_2_pipe')

def need(ok,msg):
    if not ok:raise ValueError(msg)
def stamp():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def read(p):
    try:return Path(p).read_bytes().replace(b'\0',b'').decode().strip()
    except FileNotFoundError:return None
def registry():
    r=load(ROOT/'WINDOW_VARIANTS.json');return {k:r[k] for k in VARIANTS}
def data():
    p=os.environ.get('V32_GA3_DATA',str(ROOT.parent/'v32_ga3_20261104_data'))
    return Path(p).resolve(strict=True)
def board():
    need(platform.machine()=='aarch64' and os.geteuid()==0 and 'vek280' in (read('/sys/firmware/devicetree/base/model') or '').lower(),'Run as root on VEK280, not Windows/WSL')
def environment():
    p=Path('/sys/devices/system/cpu/cpufreq/policy0')
    return dict(utc=stamp(),boot_id=read('/proc/sys/kernel/random/boot_id'),
        boot_uuid=read('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid'),
        kernel=platform.uname()._asdict(),affinity=sorted(os.sched_getaffinity(0)),
        loadavg=read('/proc/loadavg'),meminfo=read('/proc/meminfo'),
        cpu_policy={x.name:read(x) for x in p.glob('scaling_*')},
        thermal={str(x):read(x) for x in Path('/sys/class/thermal').glob('thermal_zone*/temp')},
        inherited_runtime_environment={k:os.environ.get(k) for k in ('XRT_INI_PATH','XCL_EMULATION_MODE','XRT_VITIS_TRACING')})
@contextlib.contextmanager
def lock():
    import fcntl
    with contextlib.ExitStack() as stack:
        paths=[Path('/run/ckks-ga3-experiment.lock')]
        old=ROOT.parent/'v32_hs4_20261027'
        if old.is_dir():paths.append(old/'.board.lock')
        for p in paths:
            f=stack.enter_context(p.open('a'))
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Another CKKS experiment owns the board; run sequentially')
        yield
def verify_manifest(base,manifest):
    seen=set();total=0
    for i,line in enumerate(Path(manifest).read_text(encoding='ascii').splitlines()):
        digest,name=line.split('  ',1);p=base/name
        need(len(digest)==64 and all(c in '0123456789abcdef' for c in digest) and name not in seen and not p.is_symlink() and p.is_file(),'manifest file unsafe/missing '+name)
        p.resolve().relative_to(base.resolve());need(sha(p)==digest,'hash mismatch '+name);seen.add(name);total+=p.stat().st_size
        if i and i%128==0:print('CHECK_FILES',i,'bytes',total,flush=True)
    need(seen,'empty manifest');return dict(files=len(seen),bytes=total,manifest_sha256=sha(manifest))
def code_check():
    checked=verify_manifest(ROOT,ROOT/'SHA256SUMS_PACKAGE')
    for name,r in registry().items():
        p=ROOT/'variants'/name;blob=(p/'ckks_hw_boot.xclbin').read_bytes()
        need(blob[:8]==b'xclbin2\0' and blob[416:432].hex()==r['uuid'] and struct.unpack_from('<HH',blob,332)==(0,0),'flat xclbin metadata mismatch')
        need(sha(p/'boot0001.bin')==r['boot_sha256'] and sha(p/'ckks_hw_boot.xclbin')==r['metadata_sha256'],'variant binary mismatch')
    return checked
def check(with_data=True):
    c=code_check()
    if with_data:
        d=data();need(sha(d/'SHA256SUMS_DATA')==load(ROOT/'DATA_PROVENANCE.json')['manifest_sha256'],'wrong real ga3 data manifest')
        c['data']=verify_manifest(d,d/'SHA256SUMS_DATA')
        write(ROOT/'DATA_CHECK_RECEIPT.json',dict(path=str(d),manifest_sha256=c['data']['manifest_sha256'],files=data_snapshot(d)))
    return dict(status='PASS_REAL_GA3_PACKAGE',**c,firmware_changed=False,board_performance='PENDING')
def data_snapshot(d):
    result={}
    for line in (d/'SHA256SUMS_DATA').read_text(encoding='ascii').splitlines():
        _,name=line.split('  ',1);p=d/name;need(p.is_file() and not p.is_symlink(),'missing/unsafe data '+name);p.resolve().relative_to(d.resolve());s=p.stat()
        result[name]=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
    return result
def binary(variant):return ROOT/'bin'/('ga3_host_native' if variant=='v32_native_pl_2_pipe' else 'ga3_host_aie')
def guard_recovery(env):
    p=ROOT/'RECOVERY_REQUIRED.json'
    if p.exists():need(load(p)['boot_id']!=env['boot_id'],'Previous host was interrupted while active. Preserve results and reboot the board before another hardware run.')

def stop_owned_child(p):
    """Only stop this runner's new-session child; never enumerate other tasks."""
    if p is None or p.poll() is not None:return False
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait(timeout=3)
    return True
def run(mode,order):
    board()
    with lock():
        identity=code_check();d=data();need(sha(d/'SHA256SUMS_DATA')==load(ROOT/'DATA_PROVENANCE.json')['manifest_sha256'],'wrong ga3 dataset; run check_package first')
        receipt=load(ROOT/'DATA_CHECK_RECEIPT.json');need(receipt['path']==str(d) and receipt['manifest_sha256']==sha(d/'SHA256SUMS_DATA') and receipt['files']==data_snapshot(d),'data changed or not fully checked; run sh check_package.sh')
        before=environment();guard_recovery(before);variant=next((k for k,v in registry().items() if v['uuid']==before['boot_uuid']),None);need(variant is not None,'unknown boot variant; detect/check switch first')
        need(before['affinity']==[0,1],'Both ARM CPUs 0 and 1 must be available in shell affinity; no affinity was changed automatically')
        need(not os.environ.get('XCL_EMULATION_MODE'),'Unset XCL_EMULATION_MODE for actual board tests')
        build=load(ROOT/'BUILD_IDENTITY.json');need(build['manifest_sha256']==identity['manifest_sha256'] and sha(binary(variant))==build['binaries'][binary(variant).name],'rebuild binaries after code changes')
        mem={a:int(b.split()[0]) for a,b in (x.split(':',1) for x in before['meminfo'].splitlines())}
        need(mem['MemAvailable']>650*1024 and mem['CmaTotal']>=192*1024,'insufficient available RAM/CMA total; do not clear global caches')
        folder=ROOT/f'results_ga3_{variant}_{mode}_{order}_{stamp()}';folder.mkdir()
        write(folder/'environment_before.json',before)
        n,w,limit=(1,0,2) if mode=='smoke' else (3,1,0) if mode=='windows' else (1,0,0)
        command=[str(binary(variant)),str(ROOT/'variants'/variant/'ckks_hw_boot.xclbin'),str(d),str(folder/'replay'),mode,str(n),str(w),order,str(limit)]
        run_env=dict(os.environ,XRT_INI_PATH=str(ROOT/'configs/baseline.ini'))
        write(folder/'identity.json',dict(**identity,variant=variant,data_manifest_sha256=sha(d/'SHA256SUMS_DATA'),code_build=build,command=command,baseline_ini_sha256=sha(ROOT/'configs/baseline.ini'),effective_XRT_INI_PATH=run_env['XRT_INI_PATH'],scope='Full real g_a.3 raw MAC comparison, not full original layer latency'))
        write(folder/'status.json',dict(status='RUNNING'))
        p=None
        try:
            with (folder/'execution.log').open('w',encoding='utf-8') as log:
                p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,env=run_env,start_new_session=True)
                for line in p.stdout:print(line,end='',flush=True);log.write(line);log.flush()
                rc=p.wait();need(rc==0,f'host failed rc={rc}; retain result folder')
            after=environment();write(folder/'environment_after.json',after)
            need(before['boot_id']==after['boot_id'] and before['boot_uuid']==after['boot_uuid'],'boot changed')
            need(receipt['files']==data_snapshot(d),'data mutated during run')
            answer=summarize(folder);write(folder/'status.json',dict(status='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN'))
            print(json.dumps(answer,indent=2));print('RESULTS='+str(folder))
        except BaseException as e:
            active=p is not None and p.poll() is None
            if active:write(ROOT/'RECOVERY_REQUIRED.json',dict(boot_id=before['boot_id'],folder=folder.name,reason='Host controller interrupted while child active; hardware quiescence not established',utc=stamp()))
            try:stop_owned_child(p)
            finally:write(folder/'status.json',dict(status='FAILED_RETAINED',error=str(e),interrupted_active_child=active,reboot_required=active))
            raise
def summarize(folder):
    folder=Path(folder);ident=load(folder/'identity.json');s=load(folder/'replay/summary.json');rows=list(csv.DictReader((folder/'replay/samples.csv').open(newline='')))
    r=registry()[ident['variant']];need(s['backend']==r['execution_backend'] and s['AIE_compute_tiles']==r['AIE_compute_tiles'],'software model is not board evidence')
    need(ident['manifest_sha256']==sha(ROOT/'SHA256SUMS_PACKAGE'),'source package version differs from recorded run')
    need(ident['data_manifest_sha256']==load(ROOT/'DATA_PROVENANCE.json')['manifest_sha256'],'data version differs from recorded run')
    command=ident['command'];need(len(command)==9 and Path(command[0]).name==binary(ident['variant']).name and command[4]==s['mode'] and int(command[5])==s['repetitions_per_window'] and int(command[6])==s['warmups_per_window'] and command[7] in ('ascending','descending') and int(command[8])==(2 if s['mode']=='smoke' else 0),'summary differs from executed command')
    before,after=load(folder/'environment_before.json'),load(folder/'environment_after.json');need(before['boot_id']==after['boot_id'] and before['boot_uuid']==after['boot_uuid']==r['uuid'],'boot identity changed or variant mismatched')
    full=load(ROOT/'DATA_PROVENANCE.json');coefficients=[0,122880] if full['coefficient_windows']==2 else list(range(0,131072,8192));expected_windows=16*len(coefficients)*((full['L']+15)//16)
    need(s['L']==full['L'] and s['windows']==(2 if s['mode']=='smoke' else expected_windows),'incomplete RNS/window coverage')
    need(s['coefficient_windows']==full['coefficient_windows'] and s['complete_layer_raw_MAC_coverage']==(s['mode']!='smoke' and full['coefficient_windows']==16),'mislabelled coefficient scope')
    words=0;aggregates={};seen=set()
    for wid in range(s['windows']):
        wr=[x for x in rows if int(x['window'])==wid];need(wr,'missing window samples')
        coords={(int(x['tower_start']),int(x['coefficient_start']),int(x['output_ct']),int(x['L'])) for x in wr};need(len(coords)==1,'window coordinate changed')
        t,c,ct,l=next(iter(coords));need(l==min(16,full['L']-t) and t%16==0 and c%8192==0 and ct<16,'invalid shape')
        need((t,c,ct) not in seen,'repeated coordinate instead of full layer coverage');seen.add((t,c,ct))
        checked=8192*l*3*4;words+=checked
        phases=('cpu_before','hardware','cpu_after') if s['mode'] in ('windows','smoke') else ('hardware',)
        for phase in phases:
            pr=[x for x in wr if x['phase']==phase];need(len(pr)==s['repetitions_per_window']+s['warmups_per_window'],'missing/extra trials')
            measured=[]
            for rep,x in enumerate(pr):
                v=float(x['wall_ms']);need(int(x['repetition'])==rep and int(x['warmup'])==int(rep<s['warmups_per_window']) and int(x['verified_words'])==checked and math.isfinite(v) and v>0,'bad timing/coverage sample')
                if not int(x['warmup']):measured.append(v)
            aggregates[phase]=aggregates.get(phase,0)+statistics.median(measured)
    need(words==s['verified_words'] and (s['mode']=='smoke' or words==full['checked_words']),'word coverage mismatch')
    expected={(0,0,0),(((full['L']-1)//16)*16,122880,15)} if s['mode']=='smoke' else {(t,c,ct) for t in range(0,full['L'],16) for c in coefficients for ct in range(16)}
    need(seen==expected,'missing/extra g_a.3 coordinate')
    for phase,v in aggregates.items():need(abs(v-s[f'resident_window_median_sum_{phase}_ms'])<.05,'summary differs from raw CSV')
    s['performance_claim']='PENDING_ABA_SAME_WORKLOAD_SAME_ORDER_CROSS_BOOT_REVIEW'
    if s['mode']=='export':s['output_witness']=verify_audit(folder)
    if 'cpu_before' in aggregates:
        s['CPU_window_sum_drift_percent']=100*(aggregates['cpu_after']/aggregates['cpu_before']-1)
        s['review_required']=abs(s['CPU_window_sum_drift_percent'])>5 or s['mode']=='smoke' or s['repetitions_per_window']<3 or s['warmups_per_window']<1
    write(folder/'independently_recomputed_summary.json',s);return s
def verify_audit(folder):
    d=data();digest_map=dict(line.split('  ',1)[::-1] for line in (d/'SHA256SUMS_DATA').read_text(encoding='ascii').splitlines())
    actual=0;count=0;expected=set();base=Path(folder)/'replay/outputs'
    for j in csv.DictReader((d/'jobs.tsv').open(newline=''),delimiter='\t'):
        p=base/f"r{j['tower_start']}_c{j['coefficient_start']}_o{j['output_ct']}"/f"group_{j['group']}"/'chunk_0_output.bin'
        h=Path(str(p)+'.sha256');need(h.is_file() and not h.is_symlink(),'missing actual-output digest');expected.add(h.resolve())
        digest=h.read_text(encoding='ascii').strip();need(digest==digest_map[j['expected']],'actual hardware byte digest differs from sealed original CPU output')
        if p.exists():need(not p.is_symlink() and sha(p)==digest,'actual sample differs from digest');actual+=1
        count+=1
    need({p.resolve() for p in base.rglob('*.sha256')}==expected,'unexpected or duplicate output digest')
    need(actual>=8,'first and last window actual bytes missing')
    return dict(status='PASS_ALL_ACTUAL_OUTPUT_SHA256_MATCH_SEALED_ORIGINAL',hash_linked_output_files=count,actual_byte_files=actual,
        ground_return='PENDING_ORIGINAL_CONTEXT_VERIFICATION',scope='Every job in the DECLARED coefficient scope is byte-compared on board and SHA256 linked to its sealed original output. Default download retains actual bytes for both boundary windows; other tested bytes are reconstructed from the sealed hash-identical reference for ground crypto verification. Untested coefficients, if any, are not board evidence. Not all output byte files were downloaded.')
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','code-check','detect','run','record-build','summarize']);p.add_argument('mode',nargs='?',default='smoke');p.add_argument('order',nargs='?',default='descending');a=p.parse_args()
    if a.action=='check':print(json.dumps(check(),indent=2))
    elif a.action=='code-check':print(json.dumps(code_check(),indent=2))
    elif a.action=='detect':board();e=environment();print(json.dumps(dict(matching_variant=next((k for k,v in registry().items() if v['uuid']==e['boot_uuid']),None),environment=e),indent=2))
    elif a.action=='record-build':write(ROOT/'BUILD_IDENTITY.json',dict(**code_check(),compiler=subprocess.run(['g++','--version'],capture_output=True,text=True,check=True).stdout,python=sys.version,declared_build_flags=['-O3','-std=c++17','-pthread','-I/usr/include/xrt','-lxrt_coreutil'],binaries={p.name:sha(p) for p in (ROOT/'bin').glob('ga3_host_*')}))
    elif a.action=='run':need(a.mode in ('smoke','windows','stream','export') and a.order in ('ascending','descending'),'invalid run');run(a.mode,a.order)
    else:print(json.dumps(summarize(a.mode),indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL:',e,file=sys.stderr);sys.exit(1)
