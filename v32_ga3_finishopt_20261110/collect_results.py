"""Collect and read back only measured results and small provenance, gzip level1."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
import finish_board as b

def collect(root=b.ROOT):
    root=Path(root);folders=sorted(root.glob('results_finish_*'));b.need(folders,'no new finishopt results')
    files=[];reviews=[]
    for folder in folders:
        b.need(folder.is_dir() and not folder.is_symlink(),'unsafe result folder')
        try:
            status=b.load(folder/'status.json')['status']
            b.need(status=='PASS_FINISH_BOARD_REPLAY_PENDING_INDEPENDENT_REVIEW','retained incomplete result '+status)
            b.summarize(folder)
        except Exception as e:reviews.append(dict(folder=folder.name,reason=str(e)))
        for p in sorted(folder.rglob('*')):
            b.need(not p.is_symlink(),'result symlink unsupported')
            if p.is_file():files.append(p)
    for name in ('SHA256SUMS_PACKAGE','SOURCE_PROVENANCE.json','OFFLINE_VERIFICATION.json','OPTIMIZATION_PLAN.json','START_HERE.md','screen_summary.json','BUILD_IDENTITY.json','RECOVERY_REQUIRED.json'):
        p=root/name
        if p.is_file():b.need(not p.is_symlink(),'unsafe evidence');files.append(p)
    entries=[]
    for i,p in enumerate(files):
        entries.append(dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=b.sha(p)))
        if i%100==0:print(f'INDEX {i}/{len(files)}',flush=True)
    archive=root/f'collected_ga3_finishopt_{b.stamp()}.tar.gz'
    with archive.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|',dereference=True) as tf:
        for p,e in zip(files,entries):
            b.need(p.stat().st_size==e['bytes'] and b.sha(p)==e['sha256'],'result changed while collecting')
            tf.add(p,arcname=e['path'],recursive=False)
        payload=json.dumps(dict(status='INDEXED_FINISHOPT_RESULTS',review_required_folders=reviews,entries=entries),indent=2).encode()
        member=tarfile.TarInfo('COLLECTION_INDEX.json');member.size=len(payload);tf.addfile(member,io.BytesIO(payload))
    seen={}
    with tarfile.open(archive,'r:gz') as tf:
        for member in tf:
            b.need(member.isfile() and member.name not in seen,'unsafe/duplicate collected member')
            f=tf.extractfile(member);h=hashlib.sha256()
            for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
            seen[member.name]=h.hexdigest()
    b.need(len(seen)==len(entries)+1 and all(seen[e['path']]==e['sha256'] for e in entries),'collection readback mismatch')
    return dict(status='COLLECTED_AND_VERIFIED',review_required_folders=reviews,download_this_file=str(archive),files=len(seen),bytes=archive.stat().st_size,sha256=b.sha(archive))

if __name__=='__main__':
    b.code_check();prior,_,_=b.dependencies();prior.board()
    with prior.lock():print(json.dumps(collect(),indent=2))
