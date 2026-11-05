"""Board-side bounded streaming extraction; no shell paths or overwrite."""
from pathlib import Path
import argparse, gzip, hashlib, json, os, shutil, tarfile
import ga3_board as b
def main(archive):
    archive=Path(archive).resolve(strict=True);meta=b.load(b.ROOT/'TRANSFER_MANIFEST.json')
    b.need(b.sha(archive)==meta['archive_sha256'],'archive SHA256 mismatch; do not extract')
    target=b.ROOT.parent/'v32_ga3_20261104_data';b.need(not target.exists(),'Data destination already exists; preserve it and run check_package or choose a new upload directory')
    expected=meta['data_files'];b.need(shutil.disk_usage(target.parent).free>sum(e['bytes'] for e in expected.values())+2**30,'not enough free ext4 storage for extraction; do not use SD FAT boot partition')
    target.mkdir();seen=set()
    with tarfile.open(archive,'r|gz') as tf:
        for m in tf:
            q=Path(m.name);b.need(m.isfile() and not q.is_absolute() and '..' not in q.parts and q.parts[0]=='v32_ga3_20261104_data','unsafe/non-regular archive member')
            name=Path(*q.parts[1:]).as_posix();b.need(name in expected and name not in seen and m.size==expected[name]['bytes'],'unexpected/duplicate/mis-sized data member')
            out=target/name;out.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256()
            with out.open('xb') as dst:
                source=tf.extractfile(m)
                for block in iter(lambda:source.read(2**20),b''):dst.write(block);h.update(block)
            b.need(h.hexdigest()==expected[name]['sha256'],'extracted data hash mismatch; retain failed extraction')
            seen.add(name)
            if len(seen)%128==0:print('RESTORED_DATA',len(seen),'/',len(expected),flush=True)
    b.need(seen==set(expected),'missing data archive members')
    print('PASS_RESTORED_GA3_DATA='+str(target));print('NEXT: sh check_package.sh')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');a=p.parse_args();main(a.archive)
