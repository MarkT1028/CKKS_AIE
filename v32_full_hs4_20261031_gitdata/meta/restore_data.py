"""Portable equivalent of the PowerShell restorer. Never overwrites an output."""
from pathlib import Path
import argparse,hashlib,json
PIN='1942e4fab7b7d8737c45d7a9791ad0ca2a68e1aae44cf03472a62f8287a00a90'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args();meta=Path(__file__).resolve().parent;root=meta.parent;m=json.loads((meta/'TRANSFER_MANIFEST.json').read_text(encoding='utf-8'));assert m['schema']=='full_hs4_git_transport_v1' and m['archive_sha256']==PIN and len(m['parts'])==61
 count=0
 for i,r in enumerate(m['parts']):
  assert r['name']==f'batch_{i//16+1}/part_{i:03}.part';f=root/r['name'];assert not f.is_symlink() and f.stat().st_size==r['bytes'] and sha(f)==r['sha256'];count+=r['bytes'];print(f'CHECK_PART {i+1}/61',flush=True)
 assert count==m['archive_bytes']==3036730296
 if a.check_only:print('PASS_ALL_61_PARTS_NO_OUTPUT_WRITTEN');return
 out=a.output or root.parent.parent/m['archive_name'];out=out.resolve()
 if out.exists():assert sha(out)==PIN;print('PASS_EXISTING_ORIGINAL_ARCHIVE='+str(out));return
 partial=out.with_name(out.name+'.partial')
 with partial.open('xb') as dst:
  for r in m['parts']:
   with (root/r['name']).open('rb') as src:
    for b in iter(lambda:src.read(1048576),b''):dst.write(b)
   print('JOIN_PART '+r['name'],flush=True)
 assert sha(partial)==PIN,'Archive SHA mismatch; partial retained';assert not out.exists();partial.rename(out);print('PASS_RESTORED_ORIGINAL_ARCHIVE='+str(out)+'\nSHA256='+PIN,flush=True)
if __name__=='__main__':main()
