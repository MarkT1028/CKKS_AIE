from pathlib import Path
import contextlib,os,sys,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_splitbo_20261109';B=R/'build'
sys.path.insert(0,str(K));import ga3_board as b;import compact_cache as c
T=B/('runner_'+str(time.time_ns()));T.mkdir();b.ROOT=T;d=T/'data';d.mkdir();(d/'SHA256SUMS_DATA').write_text('LOCAL_ONLY\n')
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes())
(T/'configs').mkdir();(T/'configs/baseline.ini').write_bytes((K/'configs/baseline.ini').read_bytes())
b.write(T/'DATA_PROVENANCE.json',dict(manifest_sha256=b.sha(d/'SHA256SUMS_DATA')))
b.write(T/'DATA_CHECK_RECEIPT.json',dict(path=str(d),manifest_sha256=b.sha(d/'SHA256SUMS_DATA'),files={'fixture':[1,2,3,4,5]}))
cache=T/'cache';cache.mkdir()
for n in ('CACHE_INDEX.tsv','CACHE_PLAN.json','CACHE_COMPLETE.json','CACHE_RECEIPT.json'):(cache/n).write_text('LOCAL_ONLY\n')
manifest=T/'SHA256SUMS_PACKAGE';manifest.write_text('LOCAL_ONLY\n');(T/'bin').mkdir()
for p in ('baseline','combined'):(T/'bin'/b.binary_name('v32_core_2_pipe',p)).write_text('LOCAL_ONLY\n')
b.write(T/'BUILD_IDENTITY.json',dict(manifest_sha256=b.sha(manifest),binaries={p.name:b.sha(p) for p in (T/'bin').iterdir()}))
b.board=lambda:None;b.lock=contextlib.nullcontext;b.code_check=lambda:dict(manifest_sha256=b.sha(manifest));b.data=lambda:d;b.data_snapshot=lambda p:{'fixture':[1,2,3,4,5]}
c.checked_identity=lambda:dict(path=str(cache),index_sha256='a'*64)
b.environment=lambda:dict(boot_id='LOCAL_RUNNER_NOT_BOARD',boot_uuid=b.registry()['v32_core_2_pipe']['uuid'],affinity=[0,1],meminfo='MemAvailable: 2000000 kB\nCmaTotal: 524288 kB\n')
b.summarize=lambda f:dict(status='LOCAL_RUNNER_FIXTURE_NOT_BOARD')
captured=[]
class Good:
    pid=99999999
    def __init__(self,args,**kw):captured.append((args,kw));self.stdout=iter(['LOCAL_PROCESS_FIXTURE\n'])
    def wait(self,*a,**k):return 0
    def poll(self):return 0
b.subprocess.Popen=Good
for profile in ('baseline','combined'):
    os.environ['V32_GA3_PROFILE']=profile;os.environ['V32_GA3_PREFETCH']='BAD_INHERITED';os.environ['V32_GA3_READ_MIB']='BAD_INHERITED'
    b.run('smoke','descending');args,kw=captured[-1];cfg=b.TUNINGS[profile]
    assert Path(args[0]).name==b.binary_name('v32_core_2_pipe',profile) and kw['start_new_session'] is True
    assert kw['env']['V32_GA3_PREFETCH']==str(cfg['prefetch']) and kw['env']['V32_GA3_READ_MIB']==str(cfg['read_MiB'])
    f=sorted(T.glob('results_ga3_*'))[-1];assert b.load(f/'status.json')['status']=='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN'
    cp=b.load(f/'controller_profile.json');assert cp['fresh_before_after_identities'] and set(cp['timings_ms'])=={'code_check_ms','source_snapshot_before_ms','source_snapshot_after_ms','cache_snapshot_before_ms','cache_snapshot_after_ms','environment_before_ms','environment_after_ms','binary_identity_ms','child_process_wall_ms'}
class Bad(Good):
    def __init__(self,args,**kw):
        super().__init__(args,**kw);p=Path(args[3]);p.mkdir();(p/'HARDWARE_ENTERED').write_text('MOCK_ONLY\n')
    def wait(self,*a,**k):return 1
    def poll(self):return 1
b.subprocess.Popen=Bad
try:b.run('smoke','ascending')
except ValueError as e:assert 'host failed' in str(e)
else:raise AssertionError('failed child accepted')
assert b.load(T/'RECOVERY_REQUIRED.json')['boot_id']=='LOCAL_RUNNER_NOT_BOARD'
try:b.guard_recovery(b.environment())
except ValueError:pass
else:raise AssertionError('same boot after failure accepted')
b.guard_recovery(dict(boot_id='OTHER_LOCAL_TEST_BOOT'))
b.write(B/'runner_verification.json',dict(status='PASS_MEASURED_CONTROLLER_ENVIRONMENT_AND_RECOVERY_CONTRACTS',real_board=False,real_child_started=False,registers_or_boot_changed=False))
print('PASS_RUNNER_CONTRACTS')
