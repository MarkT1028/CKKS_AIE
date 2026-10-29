#!/usr/bin/env python3
"""Progressful, indexed collection. gzip-1 defaults to fast board-side compression."""
from pathlib import Path, PurePosixPath
import argparse, fcntl, hashlib, json, tarfile
import board_runner as runner
ROOT=Path(__file__).resolve().parent

def safe_name(name):
    p=PurePosixPath(name)
    runner.require(bool(name) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name,'unsafe archive member: '+name)

def regular(path):
    runner.require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'missing/unsafe collection file: '+str(path))

def _collect(compression):
    runner.require(compression in ('gz','xz'),'compression must be gz or xz')
    entries={};results=sorted(ROOT.glob('results_bo_*'))
    runner.require(results,'no result directories found')
    for folder in results:
        runner.require(folder.is_dir() and not folder.is_symlink(),'unsafe result directory')
        for p in sorted(folder.rglob('*')):
            runner.require(not p.is_symlink(),'unsafe symlink: '+str(p))
            runner.require(p.is_file() or p.is_dir(),'non-regular result member: '+str(p))
            if p.is_file():entries[p.relative_to(ROOT).as_posix()]=p
    runner.require(any(n.endswith('/status.json') for n in entries),'no result status files')
    for name in ('PACKAGE_STATUS.json','SHA256SUMS_PACKAGE','OFFLINE_VERIFICATION.json','SOURCE_PROVENANCE.json','START_HERE.md',
                 'bin/build_identity.json','bin/schedule_selftest.log',*(f'bin/{n}' for n in runner.BINARIES)):
        p=ROOT/name
        if p.exists():entries[name]=p
    for p in sorted((ROOT/'offline_evidence').glob('*')):
        if p.is_file():entries[p.relative_to(ROOT).as_posix()]=p
    for name in ('SHA256SUMS_PACKAGE','fixture/shape.json','fixture/chunks.tsv','fixture/capture_provenance.json'):
        entries['dependency/'+name]=runner.base()/name
    for name,p in entries.items():safe_name(name);regular(p)
    stamp=runner.stamp();index=ROOT/f'collection_index_{stamp}.json'
    runner.require(not index.exists(),'index exists')
    total=sum(p.stat().st_size for p in entries.values())
    print(f'INDEXING files={len(entries)} source_MiB={total/1024**2:.1f}',flush=True)
    inventory={}
    for i,(name,p) in enumerate(sorted(entries.items()),1):
        inventory[name]=dict(bytes=p.stat().st_size,sha256=runner.records.sha(p))
        if i%50==0 or i==len(entries):print(f'INDEX {i}/{len(entries)}',flush=True)
    runner.write(index,inventory);entries[index.name]=index
    inventory[index.name]=dict(bytes=index.stat().st_size,sha256=runner.records.sha(index))
    archive=ROOT/f'collected_bo_{stamp}.tar.{compression}'
    runner.require(not archive.exists(),'archive exists')
    print(f'PACKING compression={compression}'+(' level=1' if compression=='gz' else ' preset=1'),flush=True)
    options={'compresslevel':1} if compression=='gz' else {'preset':1}
    with tarfile.open(archive,'w:'+compression,**options) as tar:
        for i,(name,p) in enumerate(sorted(entries.items()),1):
            regular(p);tar.add(p,arcname=name,recursive=False)
            if i%20==0 or i==len(entries):print(f'PACK {i}/{len(entries)}',flush=True)
    seen=set();print('VERIFYING compressed archive against the saved SHA-256 inventory',flush=True)
    with tarfile.open(archive,'r|'+compression) as tar:
        for member in tar:
            safe_name(member.name)
            runner.require(member.isfile() and member.name in inventory and member.name not in seen,'archive member/inventory mismatch')
            seen.add(member.name);want=inventory[member.name]
            runner.require(member.size==want['bytes'],'archive size mismatch')
            h=hashlib.sha256()
            with tar.extractfile(member) as f:
                for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
            runner.require(h.hexdigest()==want['sha256'],'archive SHA mismatch: '+member.name)
            if len(seen)%20==0 or len(seen)==len(inventory):print(f'VERIFY {len(seen)}/{len(inventory)}',flush=True)
    runner.require(seen==set(inventory),'archive incomplete')
    result=dict(status='COLLECTED_AND_VERIFIED',download_this_file=str(archive),files=len(entries),source_bytes=total,
                bytes=archive.stat().st_size,sha256=runner.records.sha(archive),compression=compression)
    print(json.dumps(result,indent=2),flush=True);return archive

def collect(compression='gz'):
    # Do not index outputs while any base/overlay replay owns the same device.
    with (runner.base()/'.board.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _collect(compression)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--compression',choices=['gz','xz'],default='gz');a=p.parse_args();collect(a.compression)
