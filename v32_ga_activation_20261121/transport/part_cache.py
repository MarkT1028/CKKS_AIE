"""Build an optional bounded local SD cache for the sealed GA6/GA9 streams."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE/'resident'))
from run_board import fixture

BLOCK = 32768
MAGIC = b'GAPLAN01'


def encode(block):
    end = len(block)//8*8
    constants = bytearray(8)
    varied = []
    mask = 0
    for lane in range(8):
        column = block[lane:end:8]
        if column and column.count(column[0]) == len(column):
            constants[lane] = column[0]
        else:
            mask |= 1 << lane
            varied.append(column)
    header = bytes([mask]) + constants
    return header + (block if mask == 255 else b''.join(varied) + block[end:])


def read_exact(file, count):
    data = file.read(count)
    if len(data) != count:
        raise ValueError('truncated compact part')
    return data


def verify(path, size, digest):
    h = hashlib.sha256()
    with path.open('rb') as file:
        if read_exact(file,16) != MAGIC+struct.pack('<Q',size):
            raise ValueError('invalid compact part header')
        for offset in range(0,size,BLOCK):
            n = min(BLOCK,size-offset)
            mask,*constants = read_exact(file,9)
            if mask == 255:
                h.update(read_exact(file,n))
                continue
            rows,tail = divmod(n,8)
            out = bytearray(n)
            for lane,c in enumerate(constants):
                out[lane:rows*8:8] = read_exact(file,rows) if mask & (1<<lane) else bytes([c])*rows
            out[rows*8:] = read_exact(file,tail)
            h.update(out)
        if file.read(1) or h.hexdigest() != digest:
            raise ValueError(f'compact part differs from its sealed source: {path}')


def prepare_part(source, target, size, digest):
    h = hashlib.sha256()
    if target.is_symlink():
        raise ValueError('unexpected compact part symlink')
    if target.exists():
        verify(target,size,digest)
        return False
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as out:
            tmp = Path(out.name)
            out.write(MAGIC+struct.pack('<Q',size))
            with source.open('rb') as file:
                for offset in range(0,size,BLOCK):
                    chunk=read_exact(file,min(BLOCK,size-offset))
                    h.update(chunk)
                    out.write(encode(chunk))
                if file.read(1) or h.hexdigest()!=digest:
                    raise ValueError(f'source SHA256 differs: {source}')
            out.flush()
            os.fsync(out.fileno())
        verify(tmp,size,digest)
        # Same filesystem. Publish a complete file without replacing an existing entry.
        os.link(tmp,target)
        return True
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def main():
    import fcntl
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('layer',choices=('ga6','ga9'))
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--parts',type=int,default=32)
    p.add_argument('--budget-gib',type=float,default=1)
    p.add_argument('--keep-free-gib',type=float,default=10)
    a=p.parse_args()
    if (not math.isfinite(a.budget_gib) or a.budget_gib<=0 or
            not math.isfinite(a.keep_free_gib) or a.keep_free_gib<0):
        p.error('invalid disk budget or reserve')
    root=PACKAGE.parent/f'v32_{a.layer}_offline_full_20261112'
    meta=fixture(root,a.layer)
    if not 1<=a.parts<=len(meta['parts']):
        p.error('part count exceeds the sealed layer')
    cache=a.cache.resolve()
    if cache==root.resolve() or root.resolve() in cache.parents:
        p.error('choose a sibling cache directory outside the source fixture')
    cache.mkdir(parents=True,exist_ok=True)
    prepared=processed=logical=stored=0
    reason='requested_count'
    start=time.monotonic()
    with (cache/'.prepare.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        used=sum(f.stat().st_size for f in cache.glob('*.gpc'))
        for part in meta['parts'][:a.parts]:
            size,digest=part['bytes'],part['sha256']
            path=cache/(digest+'.gpc')
            maximum=size+16+9*((size+BLOCK-1)//BLOCK)
            if not path.exists() and (used+maximum>a.budget_gib*2**30 or
                    shutil.disk_usage(cache).free-maximum<a.keep_free_gib*2**30):
                reason='disk_budget_or_free_reserve'
                break
            new=prepare_part(root/part['path'],path,size,digest)
            packed=path.stat().st_size
            if new:
                prepared+=1
                used+=packed
            logical+=size
            stored+=packed
            processed+=1
            print(f'VERIFIED_PART {processed}/{a.parts} stored={packed}',flush=True)
    receipt=dict(layer=a.layer,verified_parts=processed,new_parts=prepared,stop_reason=reason,
                 logical_bytes=logical,cache_bytes=stored,preparation_seconds=time.monotonic()-start)
    print(json.dumps(receipt,indent=2))
    if not processed:
        raise SystemExit('no verified parts fit within the budget')
    with (cache/f'prepare_{a.layer}_{time.time_ns()}.json').open('x') as f:
        json.dump(receipt,f,indent=2)


if __name__=='__main__':
    main()
