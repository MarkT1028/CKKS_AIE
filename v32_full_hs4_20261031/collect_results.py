"""Stream gzip level1, progress before compression, verify every archive member."""
from pathlib import Path
import gzip,hashlib,json,re,tarfile
import compact_io as io
from full_board import ROOT,data,stamp,check_code
def main():
 check_code();folders=sorted(p for p in ROOT.glob('results_full_hs4_*') if p.is_dir());io.need(folders,'no results to collect');paths=[]
 for folder in folders:
  for p in sorted(folder.rglob('*')):
   if p.is_file():
    n=p.relative_to(ROOT).as_posix();io.need(not any(x in n.lower() for x in ('secret_key','eval_mult','rotation_keys','context.bin')),'private file in results')
    if p.suffix=='.bin':io.need(re.fullmatch(r'results_full_hs4_[^/]+/hardware/outputs/group_[0-5]/chunk_(?:[0-9]|1[0-5])_output\.bin',n),'unknown binary in results');io.record(p,2)
    paths.append((n,p))
 for n in ('SHA256SUMS_PACKAGE','PACKAGE_STATUS.json','OFFLINE_VERIFICATION.json','SOURCE_PROVENANCE.json','bin/build_identity.json','bin/full_cpu','bin/full_host','bin/full_parser'):
  p=ROOT/n
  if p.is_file():paths.append(('release/'+n,p))
 for n in ('LAYER_DATA.json','DATA_MANIFEST.json'):paths.append(('data_identity/'+n,data()/n))
 print('INDEXING_FULL_HS4_RESULTS files='+str(len(paths)),flush=True);index={}
 for i,(n,p) in enumerate(paths):
  index[n]=dict(bytes=p.stat().st_size,sha256=io.sha(p))
  if (i+1)%24==0:print(f'INDEX {i+1}/{len(paths)}',flush=True)
 marker=stamp();name='collection_index_'+marker+'.json';payload=(json.dumps(index,indent=2)+'\n').encode();archive=ROOT/('collected_full_hs4_'+marker+'.tar.gz');io.need(not archive.exists(),'archive exists');print('COMPRESSING gzip_level=1 output='+str(archive),flush=True)
 with archive.open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,compresslevel=1,mtime=0) as z,tarfile.open(fileobj=z,mode='w|') as t:
  import io as streams
  info=tarfile.TarInfo(name);info.size=len(payload);t.addfile(info,streams.BytesIO(payload))
  for i,(n,p) in enumerate(paths):
   t.add(p,arcname=n,recursive=False)
   if (i+1)%24==0:print(f'COMPRESS {i+1}/{len(paths)}',flush=True)
  print('ARCHIVE_STREAM_WRITTEN members='+str(len(paths)+1),flush=True)
 with tarfile.open(archive,'r:gz') as t:
  seen=set()
  for member in t:
   io.need(member.isfile() and member.name not in seen,'unsafe archive');seen.add(member.name)
   if member.name==name:continue
   io.need(member.name in index,'extra member');h=hashlib.sha256();size=0
   with t.extractfile(member) as f:
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b);size+=len(b)
   io.need(index[member.name]==dict(bytes=size,sha256=h.hexdigest()),'archive verification failed')
  io.need(seen==set(index)|{name},'missing archive member')
 result=dict(status='COLLECTED_AND_ALL_MEMBERS_VERIFIED',download_this_file=str(archive),files=len(paths)+1,bytes=archive.stat().st_size,sha256=io.sha(archive),scope='All preserved full-six-MAC result folders, including failures; no raw fixtures or private keys. Ground full-layer reconstruction and decrypt still required.')
 io.write_json(ROOT/('collection_receipt_'+marker+'.json'),result);print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
