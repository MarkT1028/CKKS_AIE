#!/usr/bin/env python3
from pathlib import Path
import datetime as dt
import hashlib
import json
import tarfile
ROOT=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
    return h.hexdigest()
def main():
    files=[]
    for directory in sorted(ROOT.glob('results_real_v32_*')):
        if directory.is_dir() and not directory.is_symlink():
            files += [p for p in sorted(directory.rglob('*')) if p.is_file() and not p.is_symlink()]
    for name in ['PACKAGE_STATUS.json','SHA256SUMS_PACKAGE','OFFLINE_VERIFICATION.json','fixture/shape.json','fixture/chunks.tsv','fixture/capture_provenance.json']:
        files.append(ROOT/name)
    for name in ['bin/build_identity.json','bin/tiled_host','bin/tiled_cpu']:
        if (ROOT/name).is_file() and not (ROOT/name).is_symlink():files.append(ROOT/name)
    for directory in [ROOT/'switch_logs']:
        if directory.is_dir():files += [p for p in sorted(directory.rglob('*')) if p.is_file() and not p.is_symlink()]
    if not any(p.name=='status.json' for p in files):raise RuntimeError('No result directories found')
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    index=ROOT/f'collection_index_{stamp}.json'
    index.write_text(json.dumps({str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in files},indent=2)+'\n')
    archive=ROOT/f'collected_real_v32_{stamp}.tar.xz'
    with tarfile.open(archive,'w:xz') as tar:
        for p in files+[index]:tar.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
    with tarfile.open(archive,'r:xz') as tar:
        for p in files+[index]:
            with tar.extractfile(str(p.relative_to(ROOT))) as f:
                h=hashlib.sha256()
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
            assert h.hexdigest()==sha(p)
    print(json.dumps(dict(status='COLLECTED_AND_VERIFIED',download_this_file=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),indent=2))
if __name__=='__main__':main()
