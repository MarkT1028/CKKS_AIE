"""Time the same sealed 32 MiB parts over SD and the Windows sender."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time


PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE/'resident'))
from run_board import fixture, input_source


def read_part(stream, size):
    digest = hashlib.sha256()
    buffer = bytearray(2**20)
    data = memoryview(buffer)
    read_seconds = hash_seconds = 0.0
    remaining = size
    while remaining:
        start = time.perf_counter()
        got = stream.readinto(data[:min(remaining,len(buffer))])
        read_seconds += time.perf_counter() - start
        if not got:
            raise EOFError('input part truncated')
        remaining -= got
        start = time.perf_counter()
        digest.update(data[:got])
        hash_seconds += time.perf_counter() - start
    return digest.hexdigest(), read_seconds, hash_seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layer', choices=('ga6','ga9'))
    parser.add_argument('--input', choices=('sd','net'), required=True)
    parser.add_argument('--parts', type=int, default=32)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.data or (PACKAGE.parent/f'v32_{args.layer}_offline_full_20261112')
    network = args.input=='net'
    meta = fixture(root,args.layer,network)
    if not 1 <= args.parts <= len(meta['parts']):
        parser.error('part count must be within the sealed dataset')
    if network and input_source()!='net':
        parser.error('configure the GA sender first')

    total = 0
    read_work = hash_work = 0.0
    start = time.perf_counter()
    with contextlib.ExitStack() as context:
        if network:
            sender = context.enter_context(socket.create_connection((os.environ['V32_GA_INPUT_IP'],
                int(os.environ.get('V32_GA_INPUT_PORT','8407'))), timeout=30))
            pipe = context.enter_context(sender.makefile('rb'))
            sender.sendall(('V32GA1 '+os.environ['V32_GA_INPUT_KEY']+'\n').encode('ascii'))
            if pipe.read(1) != b'Y':
                raise ConnectionError('sender rejected handshake')
        for part in meta['parts'][:args.parts]:
            name, size = part['path'], part['bytes']
            if network:
                tick = time.perf_counter()
                sender.sendall(f'{args.layer} {name} {size}\n'.encode('ascii'))
                if pipe.read(1) != b'Y':
                    raise ConnectionError(f'sender rejected {name}')
                read_work += time.perf_counter()-tick
                digest, elapsed, checked = read_part(pipe,size)
            else:
                with (root/name).open('rb') as handle:
                    digest, elapsed, checked = read_part(handle,size)
                    if hasattr(os,'posix_fadvise'):
                        os.posix_fadvise(handle.fileno(),0,0,os.POSIX_FADV_DONTNEED)
            if digest!=part['sha256']:
                raise ValueError(f'input SHA256 differs for {name}')
            total += size
            read_work += elapsed
            hash_work += checked
    wall = time.perf_counter()-start
    result = dict(status='PASS_GA_INPUT_PROBE',layer=args.layer,input_source=args.input,parts=args.parts,
                  verified_bytes=total,read_or_receive_seconds=read_work,input_sha256_seconds=hash_work,
                  elapsed_seconds=wall,verified_MiB_per_second=total/(2**20*wall),
                  scope='Input parts only. Both sources can benefit from their OS file caches.')
    payload = json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='ascii') as file:
            file.write(payload)
    print(payload,end='')


if __name__=='__main__':
    main()
