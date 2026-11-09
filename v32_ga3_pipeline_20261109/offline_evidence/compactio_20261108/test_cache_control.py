from pathlib import Path
import contextlib,hashlib,json,os,shutil,subprocess,sys
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_compactio_20261108'
sys.path.insert(0,str(K));import compact_cache as c
B=R/'build';D=B/'synthetic';T=B/'controller';T.mkdir(exist_ok=True);(T/'bin').mkdir(exist_ok=True)
shutil.copyfile(B/'compact_tool',T/'bin/compact_tool')
c.b.board=lambda:None;c.b.ROOT=T;c.b.data=lambda:D;c.b.code_check=lambda:dict(manifest_sha256='LOCAL_CONTROL_TEST_ONLY')
c.b.lock=contextlib.nullcontext
c.b.write(T/'BUILD_IDENTITY.json',dict(manifest_sha256='LOCAL_CONTROL_TEST_ONLY',compact_tool_sha256=c.b.sha(T/'bin/compact_tool')))
c.b.write(T/'DATA_CHECK_RECEIPT.json',dict(path=str(D),manifest_sha256=c.b.sha(D/'SHA256SUMS_DATA'),files=c.b.data_snapshot(D)))
cache=B/'synthetic_cache';os.environ['V32_GA3_CACHE']=str(cache)
c.prepare('full',8);first=c.checked_identity();c.prepare('full',8);assert c.checked_identity()['index_sha256']==first['index_sha256']
# Simulate an interruption after rename but before checkpoint, and resume by
# independently verifying the already-created actual file.
state=c.b.load(cache/'PREPARATION_STATE.json');state['completed'].pop(next(iter(state['completed'])))
c.atomic(cache/'PREPARATION_STATE.json',state);c.prepare('full',8);c.checked_identity()
cases=[]
def reject(name,fn):
    try:fn()
    except Exception:cases.append(name);return
    raise AssertionError('accepted '+name)
index=cache/'CACHE_INDEX.tsv';raw=index.read_bytes();index.write_bytes(raw.replace(b'canonical_',b'Xanonical_',1));reject('modified index',c.checked_identity);index.write_bytes(raw)
entry=next((cache/'inputs').glob('*.qpk'));data=entry.read_bytes();entry.write_bytes(data[:-1]);reject('truncated cache identity',c.checked_identity)
proc=subprocess.run([str(B/'compact_tool'),'verify',str(D/c.b.load(cache/'CACHE_PLAN.json')['entries'][entry.stem]['original']),str(entry),entry.stem],capture_output=True);assert proc.returncode!=0;cases.append('truncated actual packed data rejected by decoder')
entry.write_bytes(data);c.prepare('full',8,verify=True);c.checked_identity()
raw=index.read_bytes();bad=raw.decode().splitlines();bad.append(bad[1]);index.write_text('\n'.join(bad)+'\n');reject('duplicate cache index',c.checked_identity);index.write_bytes(raw)
# C++ rejects every changed prefix/header/reserved/source-id/length class,
# as well as a canonical payload mutation whose final expanded SHA differs.
plan=c.b.load(cache/'CACHE_PLAN.json');original=D/plan['entries'][entry.stem]['original'];temp=B/'corrupt.qpk'
for at in (0,8,12,16,24,32,96,128,144,len(data)-1):
    blob=bytearray(data);blob[at]^=1;temp.write_bytes(blob)
    p=subprocess.run([str(B/'compact_tool'),'verify',str(original),str(temp),entry.stem],capture_output=True)
    assert p.returncode!=0,at;cases.append(f'packed corruption byte {at}')
temp.unlink()
# Entire original-file digest is checked before cache creation.
p=subprocess.run([str(B/'compact_tool'),'prepare',str(original),str(B/'wrong_original.qpk'),'0'*64],capture_output=True)
assert p.returncode!=0 and not (B/'wrong_original.qpk').exists();cases.append('wrong original SHA256 before creation')
# Missing declared entry cannot silently fall back to raw.
saved=entry.with_suffix('.saved');entry.rename(saved)
env=dict(os.environ,V32_GA3_CACHE=str(cache));out=B/'missing_declared_run'
p=subprocess.run([str(B/'model_1'),'unused',str(D),str(out),'smoke','1','0','descending','2'],capture_output=True,env=env)
assert p.returncode!=0;cases.append('missing declared cache entry fails replay');saved.rename(entry)
c.prepare('full',8,verify=True);c.checked_identity()
c.b.write(B/'cache_control_verification.json',dict(status='PASS_CACHE_PREPARATION_RESUME_IDENTITY_CORRUPTION_CONTROLS',cases=cases,board_executed=False))
print('PASS_CACHE_CONTROLS',len(cases))
