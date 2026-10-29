#!/usr/bin/env python3
"""Collect result evidence and raw outputs, excluding large input fixtures."""
from pathlib import Path
import hashlib,json,tarfile
import board_runner as runner
ROOT=Path(__file__).resolve().parent
def collect():
    files=[]
    for folder in sorted(ROOT.glob('results_hostopt_*')):
        if folder.is_dir() and not folder.is_symlink():
            files.extend(p for p in sorted(folder.rglob('*')) if p.is_file())
    if not any(p.name=='status.json' for p in files):raise RuntimeError('No result directories found')
    for name in ('PACKAGE_STATUS.json','SHA256SUMS_PACKAGE','OFFLINE_VERIFICATION.json','SOURCE_PROVENANCE.json','bin/build_identity.json',*(f'bin/{n}' for n in runner.BINARIES)):
        p=ROOT/name
        if p.is_file():files.append(p)
    entries={str(p.relative_to(ROOT)).replace('\\','/'):p for p in files}
    for name in ('SHA256SUMS_PACKAGE','fixture/shape.json','fixture/chunks.tsv','fixture/capture_provenance.json'):
        entries['dependency/'+name]=runner.base()/name
    for name,p in entries.items():
        if p.is_symlink() or any(x.is_symlink() for x in p.parents):raise RuntimeError('Unsafe symlink: '+str(p))
        if Path(name).is_absolute() or any(x=='..' for x in Path(name).parts):raise RuntimeError('Unsafe archive member')
    stamp=runner.stamp();index=ROOT/f'collection_index_{stamp}.json'
    runner.write(index,{n:dict(bytes=p.stat().st_size,sha256=runner.records.sha(p)) for n,p in sorted(entries.items())})
    entries[index.name]=index;archive=ROOT/f'collected_hostopt_{stamp}.tar.xz'
    with tarfile.open(archive,'w:xz') as tar:
        for name,p in sorted(entries.items()):tar.add(p,arcname=name,recursive=False)
    with tarfile.open(archive,'r:xz') as tar:
        if sorted(tar.getnames())!=sorted(entries):raise RuntimeError('Archive inventory mismatch')
        for member in tar:
            if not member.isfile():raise RuntimeError('Non-regular archive member')
            with tar.extractfile(member) as f:
                h=hashlib.sha256()
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            if h.hexdigest()!=runner.records.sha(entries[member.name]):raise RuntimeError('Archive SHA mismatch')
    print(json.dumps(dict(status='COLLECTED_AND_VERIFIED',download_this_file=str(archive),files=len(entries),bytes=archive.stat().st_size,sha256=runner.records.sha(archive)),indent=2));return archive
if __name__=='__main__':collect()
