"""Expand this release's deduplicated archive into a NEW local folder only."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,shutil,tarfile
def need(ok,why):
 if not ok:raise ValueError(why)
def safe(root,name):
 need(isinstance(name,str),'archive path must be text');p=PurePosixPath(name);need(name and not p.is_absolute() and '\\' not in name and ':' not in name and all(v not in ('','.','..') for v in p.parts),'unsafe archive path');q=root.joinpath(*p.parts);need(q.resolve().is_relative_to(root.resolve()),'path escaped destination');return q
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def restore(archive,destination):
 root=Path(destination);need(not root.exists(),'new restore directory required');root.mkdir(parents=True)
 with tarfile.open(archive,'r:gz') as t:
  members=t.getmembers();need(len(members)<=20000 and sum(m.size for m in members)<=4*1024**3 and all(m.size<=100*1024**2 for m in members),'archive exceeds collection limits');need(all(m.isfile() for m in members) and len({m.name for m in members})==len(members),'archive contains link, directory or duplicate');indexes=[m for m in members if m.name.startswith('collection_index_') and m.name.endswith('.json')];need(len(indexes)==1,'one index required');index=json.loads(t.extractfile(indexes[0]).read());need(index['schema']=='window_results_dedup_v1','unsupported archive schema');expected=index['stored_members'];need({m.name for m in members}==set(expected)|{indexes[0].name},'missing or extra members');need(sum(v['bytes'] for v in index['logical_sources'].values())<=30*1024**3,'logical restoration exceeds30GiB')
  # Validate every path before writing any payload. Do not use extractall.
  for n in list(expected)+list(index['logical_sources']):safe(root,n)
  for m in members:
   if m.name==indexes[0].name:continue
   q=safe(root,m.name);q.parent.mkdir(parents=True,exist_ok=True)
   with t.extractfile(m) as inp,q.open('xb') as out:shutil.copyfileobj(inp,out,1048576)
   need(q.stat().st_size==expected[m.name]['bytes'] and sha(q)==expected[m.name]['sha256'],'stored hash mismatch '+m.name)
 for n,v in index['logical_sources'].items():
  need(v['stored_as'] in expected and v['bytes']==expected[v['stored_as']]['bytes'] and v['sha256']==expected[v['stored_as']]['sha256'],'logical output mapping mismatch')
  q=safe(root,n);source=safe(root,v['stored_as'])
  if q!=source:
   need(not q.exists(),'logical target already exists');q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,q)
  need(q.stat().st_size==v['bytes'] and sha(q)==v['sha256'],'restored logical source mismatch')
 (root/'RESTORED_INDEX.json').write_text(json.dumps(index,indent=2)+'\n');return dict(status='RESTORED_ALL_LOGICAL_SOURCES_BYTE_EXACT',files=len(index['logical_sources']),directory=str(root))
def main():
 p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('new_destination');a=p.parse_args();print(json.dumps(restore(a.archive,a.new_destination),indent=2))
if __name__=='__main__':main()
