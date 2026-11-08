from pathlib import Path
import hashlib, json, os, shutil, struct, subprocess, time

R=Path(__file__).resolve().parent;B=R/'build';SOURCE=B/'synthetic';T=B/('negative_'+str(time.time_ns()));T.mkdir()
records=[]
def clone(name):
    dest=T/name;shutil.copytree(SOURCE,dest,copy_function=os.link);return dest
def mutate(path,fn):
    data=bytearray(path.read_bytes());path.unlink();fn(data);path.write_bytes(data)
def run(profile,data,result,expected_success=False,env=None):
    call=[str(B/f'model_{profile}'),'unused',str(data),str(result),'smoke','1','0','descending','2']
    done=subprocess.run(call,capture_output=True,text=True,timeout=120,env=env)
    assert (done.returncode==0)==expected_success,(call,done.stdout,done.stderr)
    return done.stderr.strip()

for name,fn,filename in [
    ('input_first',lambda d:d.__setitem__(64+24*16,d[64+24*16]^1),'record_3_16.bin'),
    ('input_last_L5',lambda d:d.__setitem__(-8,d[-8]^1),'record_4_5.bin'),
    ('noncanonical',lambda d:struct.pack_into('<Q',d,64+24*16,struct.unpack_from('<Q',d,64)[0]),'record_4_16.bin'),
    ('truncated',lambda d:d.pop(),'record_3_16.bin'),
    ('wrong_kind',lambda d:d.__setitem__(12,d[12]^1),'record_4_16.bin'),
]:
    data=clone(name);mutate(data/filename,fn)
    for profile in (1,2):records.append(dict(case=name,profile=profile,error=run(profile,data,T/f'{name}_{profile}_result')))

for name,action in [('missing_digest','remove'),('wrong_digest','wrong'),('duplicate_digest','duplicate')]:
    data=clone(name);p=data/'SHA256SUMS_DATA';lines=p.read_text().splitlines();p.unlink()
    target=next(line for line in lines if line.endswith('  record_2_16.bin'))
    if action=='remove':lines.remove(target)
    elif action=='wrong':lines[lines.index(target)]='0'*64+'  record_2_16.bin'
    else:lines.append(target)
    p.write_text('\n'.join(lines)+'\n')
    records.append(dict(case=name,profile=2,error=run(2,data,T/f'{name}_result')))

env=dict(os.environ,V32_GA3_DISABLE_CRYPTO='1')
records.append(dict(case='crypto_explicitly_disabled',profile=2,error=run(2,SOURCE,T/'crypto_result',env=env)))
for profile in (0,1):
    run(profile,SOURCE,T/f'word_without_crypto_{profile}',expected_success=True,env=env)
    records.append(dict(case='word_profile_needs_no_crypto',profile=profile,status='PASS'))

export=B/'sha_export/outputs';actual=0
for sidecar in export.rglob('*.sha256'):
    n=5 if '/r48_' in sidecar.as_posix() else 16
    reference=hashlib.sha256((SOURCE/f'record_2_{n}.bin').read_bytes()).hexdigest()
    assert sidecar.read_text().strip()==reference
    output=Path(str(sidecar)[:-7])
    if output.exists():assert hashlib.sha256(output.read_bytes()).hexdigest()==reference;actual+=1
assert len(list(export.rglob('*.sha256')))==512 and actual==8
answer=dict(status='PASS_IOOPT_CORRUPTION_MANIFEST_CAPABILITY_EXPORT',cases=records,
            complete_synthetic_output_digests=512,actual_byte_samples=actual,
            real_data_mutated=False,board_executed=False)
(B/'negative_verification.json').write_text(json.dumps(answer,indent=2)+'\n')
print(answer['status'],len(records))
