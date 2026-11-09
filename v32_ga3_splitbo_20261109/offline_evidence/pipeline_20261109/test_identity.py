from pathlib import Path
import hashlib,importlib.util,json,os,stat,sys,tempfile,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_pipeline_20261109';sys.path.insert(0,str(K));import ga3_board as b;import identity_fast as fast
B=R/'build';T=Path(tempfile.mkdtemp(prefix='identity_',dir=B));(T/'sub').mkdir()
files={}
for i in range(300):
    name=f'sub/f{i}.bin';p=T/name;p.write_bytes(bytes([i%256])*64);files[name]=name
(T/'SHA256SUMS_DATA').write_text(''.join(hashlib.sha256((T/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in files))
assert b.legacy_data_snapshot(T)==fast.data_snapshot(T)
cases=[]
def reject(name,fn):
    try:fn()
    except (ValueError,OSError):cases.append(name);return
    raise AssertionError('accepted '+name)
reject('parent traversal',lambda:fast.snapshot(T,{'x':'../x'}));reject('absolute path',lambda:fast.snapshot(T,{'x':'/tmp/x'}));reject('backslash',lambda:fast.snapshot(T,{'x':'sub\\f1.bin'}))
(T/'link').symlink_to(T/'sub',target_is_directory=True);reject('intermediate directory symlink',lambda:fast.snapshot(T,{'x':'link/f1.bin'}))
(T/'leaf').symlink_to(T/'sub/f1.bin');reject('leaf symlink',lambda:fast.snapshot(T,{'x':'leaf'}));reject('directory instead of file',lambda:fast.snapshot(T,{'x':'sub'}))
old=fast.data_snapshot(T);p=T/'sub/f1.bin';p.write_bytes(b'changed');assert fast.data_snapshot(T)!=old;cases.append('mutation changes fresh identity')
# Replacing a directory after its FD is pinned must fail its final namespace
# check, even if the old file still exists through the descriptor.
original_stat=fast.os.stat;swapped=False
def swapped_stat(path,*args,**kwargs):
    global swapped
    result=original_stat(path,*args,**kwargs)
    if str(path)=='f0.bin' and not swapped:
        swapped=True;(T/'sub').rename(T/'sub_old');(T/'sub').mkdir()
    return result
fast.os.stat=swapped_stat
reject('parent namespace replacement',lambda:fast.snapshot(T,{'x':'sub/f0.bin'}));fast.os.stat=original_stat
real=Path('/mnt/d/CodexBuilds/v32_ga3_20261104/public_data_v2');timings=[]
for method in ('legacy','fast','fast','legacy'):
    t=time.perf_counter();result=b.legacy_data_snapshot(real) if method=='legacy' else fast.data_snapshot(real)
    elapsed=(time.perf_counter()-t)*1000
    if timings:assert result==reference
    else:reference=result
    timings.append(dict(method=method,ms=elapsed,files=len(result)))
(B/'identity_verification.json').write_text(json.dumps(dict(status='PASS_FRESH_IDENTITY_EQUIVALENCE_AND_NAMESPACE_NEGATIVES',cases=cases,real_files=len(reference),local_timings_ms=timings,board_performance=False),indent=2)+'\n')
print('PASS_IDENTITY_EQUIVALENCE_NEGATIVES',len(cases),json.dumps(timings))
