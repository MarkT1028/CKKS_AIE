"""All stream/service/baseline attempts; gzip1, progress, byte-exact index."""
from pathlib import Path
import gzip,hashlib,io as streams,json,re,tarfile
import compact_io as io,full_board as base,stream_board as s
def main():
 base.check_code();folders=sorted({p for pattern in ('results_stream_*','results_service_*','results_full_hs4_*') for p in s.ROOT.glob(pattern) if p.is_dir()});io.need(folders,'no results');io.need(all(not p.is_symlink() for p in folders),'linked result folder');paths=[]
 for folder in folders:
  for p in sorted(folder.rglob('*')):
   if not p.is_file():continue
   n=p.relative_to(s.ROOT).as_posix();io.safe(s.ROOT,n);io.need(not any(word in n.lower() for word in ('secret_key','context.bin','eval_mult','rotation_keys')),'private file in result')
   if p.suffix=='.bin':
    allowed=re.fullmatch(r'results_(?:stream_[^/]+/hardware|full_hs4_[^/]+/hardware|service_[^/]+/session/request_[12])/outputs/group_[0-5]/chunk_(?:[0-9]|1[0-5])_output\.bin',n);io.need(allowed,'unknown result binary '+n);io.record(p,2)
   paths.append((n,p))
 for n in ('SHA256SUMS_PACKAGE','PACKAGE_STATUS.json','SOURCE_PROVENANCE.json','OFFLINE_VERIFICATION.json','bin/build_identity.json','bin/stream_build_identity.json',*(f'bin/{x}' for x in s.BINARIES)):
  p=s.ROOT/n
  if p.is_file():paths.append(('release/'+n,p))
 for n in ('LAYER_DATA.json','DATA_MANIFEST.json'):paths.append(('data_identity/'+n,base.data()/n))
 print('INDEXING_STREAM_RESULTS files='+str(len(paths)),flush=True);index={}
 for i,(n,p) in enumerate(paths):
  io.need(n not in index,'duplicate archive source');index[n]=dict(bytes=p.stat().st_size,sha256=io.sha(p))
  if (i+1)%24==0:print(f'INDEX {i+1}/{len(paths)}',flush=True)
 marker=base.stamp();index_name='collection_index_'+marker+'.json';payload=(json.dumps(index,indent=2)+'\n').encode();archive=s.ROOT/('collected_stream_'+marker+'.tar.gz');print('COMPRESSING gzip_level=1 '+str(archive),flush=True)
 with archive.open('xb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=1,mtime=0) as z,tarfile.open(fileobj=z,mode='w|') as t:
  info=tarfile.TarInfo(index_name);info.size=len(payload);t.addfile(info,streams.BytesIO(payload))
  for i,(n,p) in enumerate(paths):
   t.add(p,arcname=n,recursive=False)
   if (i+1)%24==0:print(f'COMPRESS {i+1}/{len(paths)}',flush=True)
 seen=set()
 with tarfile.open(archive,'r:gz') as t:
  for m in t:
   io.need(m.isfile() and m.name not in seen,'archive type/duplicate');seen.add(m.name)
   if m.name==index_name:continue
   io.need(m.name in index,'unlisted archive member');h=hashlib.sha256();size=0
   with t.extractfile(m) as f:
    for b in iter(lambda:f.read(1048576),b''):h.update(b);size+=len(b)
   io.need(index[m.name]==dict(bytes=size,sha256=h.hexdigest()),'archive byte verification '+m.name)
 io.need(seen==set(index)|{index_name},'archive missing member');receipt=dict(status='COLLECTED_AND_ALL_STREAM_MEMBERS_VERIFIED',download_this_file=str(archive),files=len(seen),bytes=archive.stat().st_size,sha256=io.sha(archive),scope='All retained streamed/persistent-fixture/legacy baseline attempts, including failures. No fixtures or private keys. Original-context ground return required before full-layer claims.');io.write_json(s.ROOT/('collection_receipt_'+marker+'.json'),receipt);print(json.dumps(receipt,indent=2),flush=True)
if __name__=='__main__':main()
