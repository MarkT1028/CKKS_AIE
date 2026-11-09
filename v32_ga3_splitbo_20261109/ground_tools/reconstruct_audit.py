"""Ground-only hash-witness reconstruction; never label reconstructed bytes downloaded.

The caller must first independently validate run CSV/identity and the collection
index. This utility binds EVERY tested job to the sealed original reference.
It does not synthesize or claim evidence for untested coefficient windows.
"""
from pathlib import Path
import argparse,csv,hashlib,json,os,shutil
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def reconstruct(data,actual,dest,manifest_sha256,evidence_kind='actual_board_output_hash_witness'):
    data=Path(data).resolve(strict=True);actual=Path(actual).resolve(strict=True);dest=Path(dest).resolve()
    need(not dest.exists(),'new reconstruction destination required');manifest=data/'SHA256SUMS_DATA';need(sha(manifest)==manifest_sha256,'wrong sealed data manifest')
    hashes=dict(line.split('  ',1)[::-1] for line in manifest.read_text(encoding='ascii').splitlines())
    for p in (data/'jobs.tsv',data/'shape.json'):need(sha(p)==hashes[p.name],'source metadata changed')
    shape=json.loads((data/'shape.json').read_text());rows=list(csv.DictReader((data/'jobs.tsv').open(newline=''),delimiter='\t'));need(len(rows)==shape['jobs'],'declared job count differs')
    expected=set();proof=[]
    for j in rows:
        rel=Path(f"r{j['tower_start']}_c{j['coefficient_start']}_o{j['output_ct']}")/f"group_{j['group']}"/'chunk_0_output.bin';p=actual/rel;h=Path(str(p)+'.sha256')
        need(h.is_file() and not h.is_symlink(),'missing actual-output hash');expected.add(h.resolve());digest=h.read_text(encoding='ascii').strip();need(digest==hashes[j['expected']],'actual output hash differs from original sealed reference')
        reference=data/j['expected'];reference.resolve().relative_to(data);need(reference.is_file() and not reference.is_symlink(),'unsafe reference')
        if p.exists():need(p.is_file() and not p.is_symlink() and sha(p)==digest,'actual sample differs from witness')
        proof.append(dict(path=rel.as_posix(),sha256=digest,reference=j['expected'],origin='downloaded_actual_bytes' if p.exists() else 'hash_identical_sealed_reference_reconstruction'))
    need({p.resolve() for p in actual.rglob('*.sha256')}==expected,'unexpected/duplicate witness file')
    need(sum(x['origin']=='downloaded_actual_bytes' for x in proof)>=8,'boundary sample bytes missing')
    dest.mkdir(parents=True)
    for i,x in enumerate(proof):
        out=dest/x['path'];out.parent.mkdir(parents=True,exist_ok=True)
        if x['origin']=='downloaded_actual_bytes':shutil.copy2(actual/x['path'],out)
        else:
            source=data/x['reference'];need(sha(source)==x['sha256'],'sealed reference payload changed')
            try:os.link(source,out)
            except OSError as e:
                if e.errno==18 or getattr(e,'winerror',None)==17:shutil.copy2(source,out)
                else:raise
        if x['origin']=='downloaded_actual_bytes':need(sha(out)==x['sha256'],'sample copy mismatch')
        if i%128==0:print('HASH_LINKED_RECONSTRUCTION',i,'/',len(proof),flush=True)
    result=dict(status='PASS_DECLARED_SCOPE_OUTPUT_HASH_WITNESS_RECONSTRUCTION',evidence_kind=evidence_kind,
        manifest_sha256=manifest_sha256,coefficient_windows=shape['coefficient_windows'],complete_raw_MAC_coefficient_coverage=shape['coefficient_windows']==16,
        files=len(proof),downloaded_actual_byte_files=sum(x['origin']=='downloaded_actual_bytes' for x in proof),proof=proof,
        scope='Downloaded sample bytes and hash-identical reference reconstructions are explicitly distinguished. This is not an assertion that every output byte file was downloaded. No untested coefficient index is converted into board evidence. Original-context crypto verification remains a separate required step.')
    (dest/'DERIVATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data');p.add_argument('actual_outputs');p.add_argument('dest');p.add_argument('manifest_sha256');a=p.parse_args();print(json.dumps({k:v for k,v in reconstruct(a.data,a.actual_outputs,a.dest,a.manifest_sha256).items() if k!='proof'},indent=2))
