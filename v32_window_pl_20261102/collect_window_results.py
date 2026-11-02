"""All attempts retained. Identical saved outputs stored once, no hardlinks.

Each logical actual file has a byte count and SHA256 in the index. Restoration
copies the verified blob back to every original path; board originals unchanged.
"""
from pathlib import Path,PurePosixPath
import gzip,hashlib,io as streams,json,re,tarfile
import compact_io as io,full_board as base,window_board as wb
def collect(root,release_names,marker,extra_paths=None):
 root=Path(root);logical={};stored={};blobs={};folders=[p for p in sorted(root.glob('results_window_*')) if p.is_dir()]
 io.need(folders,'no window results; retain smoke/formal failures too')
 paths=[]
 for folder in folders:
  io.need(not folder.is_symlink(),'result directory cannot be symlink')
  for p in sorted(folder.rglob('*')):
   io.need(not p.is_symlink(),'result path cannot be symlink')
   if not p.is_file():continue
   io.need(not p.is_symlink(),'result file cannot be symlink');io.need(p.resolve().is_relative_to(root.resolve()),'result path outside package');paths.append((p.relative_to(root).as_posix(),p))
 for name in release_names:
  p=root/name
  if p.is_file():paths.append(('release/'+name,p))
 paths.extend(extra_paths or [])
 print('INDEXING_WINDOW_RESULTS logical_files='+str(len(paths)),flush=True)
 total=0
 for i,(n,p) in enumerate(paths):
  io.need(n not in logical,'duplicate source path');size=p.stat().st_size;h=io.sha(p);total+=size
  if n.startswith('results_window_') and p.suffix=='.bin':
   io.need(bool(re.fullmatch(r'results_window_[^/]+/hardware/outputs/group_[0-5]/chunk_(?:[0-9]|1[0-5])_output\.bin',n)),'unknown binary result '+n)
   target='actual_output_blobs/'+h+'.bin';blobs.setdefault(h,p)
  else:target=n
  logical[n]=dict(bytes=size,sha256=h,stored_as=target)
  if target not in stored:stored[target]=dict(path=p,bytes=size,sha256=h)
  else:io.need(stored[target]['bytes']==size and stored[target]['sha256']==h,'conflicting dedup identity')
  if (i+1)%16==0:print(f'INDEX {i+1}/{len(paths)} source_MiB={total/1048576:.1f}',flush=True)
 index=dict(schema='window_results_dedup_v1',logical_sources=logical,stored_members={n:{k:v for k,v in x.items() if k!='path'} for n,x in stored.items()},scope='Actual source bytes indexed separately for every attempt. Identical ciphertext output blobs transported once. No board results deleted, no hardlinks, no new performance claim.')
 payload=(json.dumps(index,indent=2)+'\n').encode();archive=root/('collected_window_pl_'+marker+'.tar.gz');index_name='collection_index_'+marker+'.json';stored_bytes=sum(x['bytes'] for x in stored.values());print(f'COMPRESSING gzip1 logical_MiB={total/1048576:.1f} stored_MiB={stored_bytes/1048576:.1f} unique_output_blobs={len(blobs)}',flush=True)
 with archive.open('xb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=1,mtime=0) as z,tarfile.open(fileobj=z,mode='w|') as t:
  info=tarfile.TarInfo(index_name);info.size=len(payload);t.addfile(info,streams.BytesIO(payload))
  for i,(n,x) in enumerate(stored.items()):
   t.add(x['path'],arcname=n,recursive=False)
   if (i+1)%16==0:print(f'COMPRESS {i+1}/{len(stored)}',flush=True)
 seen=set()
 with tarfile.open(archive,'r:gz') as t:
  for m in t:
   io.need(m.isfile() and m.name not in seen,'archive duplicate or nonregular member');seen.add(m.name)
   if m.name==index_name:io.need(t.extractfile(m).read()==payload,'index changed');continue
   io.need(m.name in stored,'unexpected stored member');h=hashlib.sha256();size=0
   with t.extractfile(m) as f:
    for block in iter(lambda:f.read(1048576),b''):h.update(block);size+=len(block)
   x=stored[m.name];io.need(size==x['bytes'] and h.hexdigest()==x['sha256'],'stored archive byte mismatch '+m.name)
   if len(seen)%16==0:print(f'VERIFY {len(seen)-1}/{len(stored)}',flush=True)
 io.need(seen==set(stored)|{index_name},'missing stored member')
 for n,x in logical.items():v=stored[x['stored_as']];io.need(x['bytes']==v['bytes'] and x['sha256']==v['sha256'],'bad logical-to-stored identity '+n)
 receipt=dict(status='COLLECTED_ALL_LOGICAL_SOURCES_AND_STORED_BYTES_VERIFIED',schema=index['schema'],download_this_file=str(archive),logical_files=len(logical),stored_files=len(stored)+1,unique_output_blobs=len(blobs),logical_source_bytes=total,transport_payload_bytes=stored_bytes,bytes=archive.stat().st_size,sha256=io.sha(archive),original_board_results_unchanged=True,scope=index['scope']);io.write_json(root/('collection_receipt_'+marker+'.json'),receipt);print(json.dumps(receipt,indent=2),flush=True);return archive,index
def main():
 wb.check_code();names=['SHA256SUMS_PACKAGE','PACKAGE_STATUS.json','SOURCE_PROVENANCE.json','OFFLINE_VERIFICATION.json','WINDOW_VARIANTS.json','RESOURCE_COMPARISON.json','window_campaign.json','bin/window_build_identity.json',*(f'bin/{n}' for n in wb.BINARIES)]
 names.extend(n for line in (wb.ROOT/'SHA256SUMS_PACKAGE').read_text().splitlines() for h,n in [line.split('  ',1)] if n.startswith(('candidate_source/','offline_evidence/','evidence/')))
 for p in (wb.ROOT/'switch_logs').glob('*'):
  if p.is_file():names.append(p.relative_to(wb.ROOT).as_posix())
 extra=[('data_identity/'+n,base.data()/n) for n in ['LAYER_DATA.json','DATA_MANIFEST.json']]
 collect(wb.ROOT,list(dict.fromkeys(names)),base.stamp(),extra)
if __name__=='__main__':main()
