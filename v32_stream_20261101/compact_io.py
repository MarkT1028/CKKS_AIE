"""Strict public raw fixture IO. This module never imports OpenFHE or keys."""
from array import array
from pathlib import Path,PurePosixPath
import hashlib,json,struct,sys
SOURCE_SHA='078db343138b5f51b018bf963c5aa638c0445b6e9bb6ec0c79713f6e565e8916'
def need(x,msg):
 if not x:raise ValueError(msg)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write_json(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def safe(root,name):
 need(isinstance(name,str) and name and '\\' not in name and ':' not in name,'unsafe name');p=PurePosixPath(name);need(not p.is_absolute() and all(x not in ('.','..') for x in p.parts),'unsafe relative path');r=Path(root).resolve();q=r/Path(name);need(q.resolve().is_relative_to(r) and not any(x.is_symlink() for x in [q,*q.parents]),'unsafe symlink/path');return q
def record(path,want=None,payload=False):
 path=Path(path)
 with path.open('rb') as f:
  header=f.read(64);need(len(header)==64 and header[:8]==b'CKKSMAC1','record header');version,kind,n,l,k,c,layout,tile,r0,r1,words,r2=struct.unpack('<10I2Q',header[8:]);need(version==1 and kind in (2,3,4) and (want is None or kind==want),'record version/kind');need(128<=n<=8192 and not n&(n-1) and 1<=l<=16 and 1<=k<=16,'record bounds');need((c,layout,tile,r0,r1,r2)==(3 if kind==2 else 2,1,64,0,0,0),'record layout');need(words==n*l*(3 if kind==2 else 2*k) and path.stat().st_size==64+24*l+words*8,'record length/count');qs=[]
  for _ in range(l):
   q,lo,hi=struct.unpack('<3Q',f.read(24));need((1<<44)<=q<(1<<60) and q&1,'modulus bounds');need(lo+(hi<<64)==((1<<128)-1)//q,'reciprocal');qs.append(q)
  data=None
  if payload:
   data=array('Q');data.fromfile(f,words)
   if sys.byteorder!='little':data.byteswap()
   span=n*(3 if kind==2 else 2)
   need(all(x<qs[(i//span)%l] for i,x in enumerate(data)),'noncanonical payload')
 return dict(kind=kind,n=n,l=l,k=k,words=words,q=qs,data=data)
def write_record(path,kind,n,l,k,qs,data):
 data=array('Q',data);need(len(data)==n*l*(3 if kind==2 else k*2),'test record length')
 with Path(path).open('xb') as f:
  f.write(b'CKKSMAC1'+struct.pack('<10I2Q',1,kind,n,l,k,3 if kind==2 else 2,1,64,0,0,len(data),0))
  for q in qs:
   mu=((1<<128)-1)//q;f.write(struct.pack('<3Q',q,mu&((1<<64)-1),mu>>64))
  if sys.byteorder!='little':data.byteswap()
  data.tofile(f)
def verify_data(root,full=True,production=True,progress=True):
 root=Path(root);meta=load(root/'LAYER_DATA.json');manifest=load(root/'DATA_MANIFEST.json');need(meta['schema']=='full_hs4_mean_raw_v1' and meta['groups']==list(range(5,-1,-1)),'layer data schema/order');need(meta['source_sha256']==SOURCE_SHA,'wrong original source');need(meta['scope']=='h_s.4(mean),96 channels,4x4 positions,6 K16 MAC groups','wrong layer scope')
 shape=meta['shape'];n,l,k,cn=map(shape.__getitem__,('N','L','K','chunk_N'));need(128<=cn<=8192 and not cn&(cn-1) and cn<=n<=131072 and not n&(n-1) and n%cn==0 and 1<=l<=16 and k==16,'fixture grid')
 if production:need((n,l,k,cn)==(131072,14,16,8192) and meta['synthetic'] is False,'production requires real full-layer fixture')
 count=n//cn;expected={'LAYER_DATA.json'}
 for i in range(count):expected.add(f'shared/chunk_{i}_baby.bin')
 for g in range(6):
  base=f'group_{g}';expected|={base+'/shape.json',base+'/chunks.tsv'};gs=load(root/base/'shape.json');need(all(gs[q]==v for q,v in [('N',n),('L',l),('K',k),('chunk_N',cn),('chunks',count),('group',g)]),'group shape mismatch');rows=(root/base/'chunks.tsv').read_text().splitlines();need(rows==['id\ttower_start\tcoefficient_start\tN\tL\tK']+[f'chunk_{i}\t0\t{i*cn}\t{cn}\t{l}\t{k}' for i in range(count)],'group chunk coverage/order')
  for i in range(count):
   for suffix,kind in [('weight',3),('expected',2)]:
    name=f'{base}/chunks/chunk_{i}_{suffix}.bin';expected.add(name);h=record(root/name,kind);need((h['n'],h['l'],h['k'],h['q'])==(cn,l,k,shape['moduli']),'operand shape/moduli')
 for i in range(count):
  h=record(root/f'shared/chunk_{i}_baby.bin',4);need((h['n'],h['l'],h['k'],h['q'])==(cn,l,k,shape['moduli']),'shared baby metadata')
 need(set(manifest)==expected,'missing or extra data-manifest members');actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()};need(actual==expected|{'DATA_MANIFEST.json'},'unlisted file in data tree')
 total=0
 for i,(name,row) in enumerate(manifest.items()):
  p=safe(root,name);need(p.is_file() and p.stat().st_size==row['bytes'],'missing/resized data member '+name);need(p.stat().st_size<50*1024*1024,'oversized individual data member');total+=row['bytes']
  if full:need(sha(p)==row['sha256'],'data checksum '+name)
  if progress and (i+1)%32==0:print(f'CHECK_DATA {i+1}/{len(manifest)} bytes={total}',flush=True)
 return dict(status='PASS_FULL_HS4_COMPACT_DATA' if full else 'PASS_FULL_HS4_DATA_HEADERS',files=len(manifest),bytes=total,manifest_sha256=sha(root/'DATA_MANIFEST.json'),capture_id=meta['capture_id'],full_checksums=full,production=production,groups=6,output_words=6*n*l*3)
def seal_data(root):
 root=Path(root);need(not (root/'DATA_MANIFEST.json').exists(),'data already sealed');files={p.relative_to(root).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(root.rglob('*')) if p.is_file()};write_json(root/'DATA_MANIFEST.json',files)
