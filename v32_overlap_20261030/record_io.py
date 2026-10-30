"""Strict CKKSMAC1 reader used by preparation, tests and board preflight."""
from array import array
from pathlib import Path
import csv
import hashlib
import json
import struct
import sys

MIN_Q=1<<44
MAX_Q=1<<60

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def require(test, message):
    if not test:raise ValueError(message)

def read(path, kind=None, canonical=True):
    path=Path(path)
    with path.open('rb') as f:
        h=f.read(64)
        require(len(h)==64 and h[:8]==b'CKKSMAC1','invalid record header')
        version,kd,n,l,k,components,layout,tile,r0,r1,count,r2=struct.unpack('<10I2Q',h[8:])
        require(version==1 and kd in (1,2) and (kind is None or kd==kind),'record version/kind')
        require(128<=n<=8192 and n&(n-1)==0 and 1<=l<=16 and 1<=k<=16,'record dimensions')
        require((components,layout,tile,r0,r1,r2)==(4 if kd==1 else 3,1,64,0,0,0),'record layout')
        require(count==n*l*(4*k if kd==1 else 3),'record word count')
        require(path.stat().st_size==64+24*l+8*count,'record file length')
        q=[]
        for _ in range(l):
            m,lo,hi=struct.unpack('<3Q',f.read(24));mu=(1<<128)//m if m else 0
            require(MIN_Q<=m<MAX_Q and m&1,'record modulus')
            require(lo+(hi<<64)==mu and mu.bit_length()<=84,'record reciprocal')
            q.append(m)
        data=array('Q');data.fromfile(f,count)
        if sys.byteorder!='little':data.byteswap()
    if canonical:
        span=n*(4 if kd==1 else 3)
        for i,x in enumerate(data):require(x<q[(i//span)%l],'noncanonical residue')
    return dict(kind=kd,n=n,l=l,k=k,q=q,data=data)

def write(path,kind,n,l,k,q,data):
    require(len(q)==l and len(data)==n*l*(4*k if kind==1 else 3),'write shape')
    with Path(path).open('wb') as f:
        f.write(b'CKKSMAC1'+struct.pack('<10I2Q',1,kind,n,l,k,4 if kind==1 else 3,1,64,0,0,len(data),0))
        for m in q:
            mu=(1<<128)//m;f.write(struct.pack('<3Q',m,mu&((1<<64)-1),mu>>64))
        a=array('Q',data)
        if sys.byteorder!='little':a.byteswap()
        a.tofile(f)

def grid(n,l,k):
    require(128<=n<=131072 and n&(n-1)==0 and 1<=l<=64 and 1<=k<=16,'full shape')
    rows=[]
    for t in range(0,l,16):
        for j in range(0,n,8192):
            rows.append(dict(id=f'chunk_{len(rows)}',tower_start=t,coefficient_start=j,
                             N=min(8192,n-j),L=min(16,l-t),K=k))
    return rows

def inspect_fixture(root, canonical=True):
    root=Path(root)
    shape=json.loads((root/'shape.json').read_text())
    wanted=grid(shape['N'],shape['L'],shape['K'])
    with (root/'chunks.tsv').open(newline='') as f:
        rows=[{key:value if key=='id' else int(value) for key,value in r.items()} for r in csv.DictReader(f,delimiter='\t')]
    require(rows==wanted and shape['chunks']==len(rows),'incomplete or overlapping chunk coverage')
    require(len(shape['moduli'])==shape['L'],'full modulus count')
    words=0
    for r in rows:
        a=read(root/'chunks'/(r['id']+'_input.bin'),1,canonical)
        b=read(root/'chunks'/(r['id']+'_expected.bin'),2,canonical)
        for record in [a,b]:
            require((record['n'],record['l'],record['k'])==(r['N'],r['L'],r['K']),'chunk shape mismatch')
            require(record['q']==shape['moduli'][r['tower_start']:r['tower_start']+r['L']],'chunk modulus order')
        words+=len(b['data'])
    require(words==3*shape['N']*shape['L'],'full output coverage')
    return dict(status='PASS_COMPLETE_FULL_RING_CHUNK_COVERAGE',shape=shape,
                chunks=len(rows),raw_words=words,canonical_checked=canonical)
