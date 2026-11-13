#!/usr/bin/env python3
"""Compare serial reads with one-part prefetch using the first full g_a.9 block."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import time


def discard_cached_parts(paths):
    if not hasattr(os, 'posix_fadvise'):
        return 'unavailable'
    try:
        for path in paths:
            with path.open('rb') as stream:
                os.posix_fadvise(stream.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    except OSError as error:
        return f'advice_failed_errno_{error.errno}'
    return 'advisory_dontneed'


def process_read_bytes():
    try:
        fields = dict(line.split(':', 1) for line in Path('/proc/self/io').read_text().splitlines())
        return int(fields['read_bytes'])
    except (OSError, KeyError, ValueError):
        return None


class Reader:
    def __init__(self, entries, executor, wire):
        self.entries, self.executor, self.wire = entries, executor, wire
        self.next = 0
        self.buffer = memoryview(b'')
        self.pending = None
        self.read_ns = self.hash_ns = self.wait_ns = 0

    def load(self, index):
        path, size, expected = self.entries[index]
        start = time.perf_counter_ns()
        data = path.read_bytes()
        read_ns = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        self.wire.check(len(data) == size and self.wire.digest(data) == expected, f'bad input part {path.name}')
        return data, read_ns, time.perf_counter_ns() - start

    def next_part(self):
        start = time.perf_counter_ns()
        if self.pending is None:
            data, read_ns, hash_ns = self.load(self.next)
        else:
            data, read_ns, hash_ns = self.pending.result()
        self.wait_ns += time.perf_counter_ns() - start
        self.read_ns += read_ns
        self.hash_ns += hash_ns
        self.next += 1
        self.buffer = memoryview(data)
        if self.executor is not None and self.next < len(self.entries):
            self.pending = self.executor.submit(self.load, self.next)
        else:
            self.pending = None

    def read(self, count):
        output = bytearray()
        while len(output) < count:
            if not self.buffer:
                self.next_part()
            length = min(count-len(output), len(self.buffer))
            output.extend(self.buffer[:length])
            self.buffer = self.buffer[length:]
        return output


def trial(wire, command, entries, schedule, hashes, hardware, prefetch):
    cache = discard_cached_parts(path for path, _, _ in entries)
    workers = ThreadPoolExecutor(max_workers=1) if prefetch else nullcontext()
    with workers as executor, subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
        try:
            wire.check(struct.unpack('<II', wire.exact(child.stdout, 8)) == (wire.HELLO, int(hardware)), 'wrong server backend')
            start = time.perf_counter_ns()
            read_before = process_read_bytes()
            source = Reader(entries, executor, wire)
            pipe_ns = receive_ns = pl_ns = result_hash_ns = 0
            verified_words = 0
            for tile, l, group, flags, _, _ in schedule:
                header = source.read(28)
                wire.check(struct.unpack('<7I', header) == (wire.REQUEST, tile, 8192, l, 16, group, flags), 'request header mismatch')
                moduli = source.read(8*l)
                tick = time.perf_counter_ns()
                child.stdin.write(header)
                child.stdin.write(moduli)
                pipe_ns += time.perf_counter_ns() - tick
                remaining = wire.payload_size(l, flags)
                while remaining:
                    data = source.read(min(remaining, 4*2**20))
                    tick = time.perf_counter_ns()
                    child.stdin.write(data)
                    pipe_ns += time.perf_counter_ns() - tick
                    remaining -= len(data)
                tick = time.perf_counter_ns()
                child.stdin.flush()
                pipe_ns += time.perf_counter_ns() - tick
                op, identity, n, actual_l, k, receive, run = struct.unpack('<5I2Q', wire.exact(child.stdout, 36))
                wire.check((op, identity, n, actual_l, k) == (wire.REPLY, tile, 8192, l, 16), 'reply header mismatch')
                raw = wire.exact(child.stdout, n*l*3*8)
                tick = time.perf_counter_ns()
                wire.check(wire.digest(raw) == hashes[tile-1], f'output SHA256 mismatch at tile {tile}')
                result_hash_ns += time.perf_counter_ns() - tick
                receive_ns += receive
                pl_ns += run
                verified_words += n*l*3
            read_after = process_read_bytes()
            wall_ns = time.perf_counter_ns() - start
            wire.check(source.next == len(entries), 'unexpected short-test input part coverage')
            child.stdin.write(struct.pack('<I', wire.STOP))
            child.stdin.close()
            wire.check(child.wait(timeout=15) == 0, 'server exit failed')
        except BaseException:
            if child.poll() is None:
                child.terminate()
            raise
    return dict(mode='prefetch' if prefetch else 'serial', cache_advice=cache,
                process_storage_read_bytes=None if read_before is None or read_after is None else read_after-read_before,
                parts=len(entries), tiles=len(schedule), verified_words=verified_words, wall_ns=wall_ns,
                file_read_ns=source.read_ns, input_sha256_ns=source.hash_ns, reader_wait_ns=source.wait_ns,
                parent_pipe_write_flush_ns=pipe_ns, server_receive_sync_ns=receive_ns, server_run_ns=pl_ns,
                output_sha256_ns=result_hash_ns)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, help='local software-model validation only')
    args = parser.parse_args()
    root = Path.cwd()
    manifest_bytes = (root / 'manifest.json').read_bytes()
    meta = json.loads(manifest_bytes)
    # Use the board package's existing wire constants and schedule.
    sys.path.insert(0, str(root))
    import offline_files as wire

    wire.check(not args.output.exists(), 'choose a new output path')
    wire.check(meta['layer'] == 'g_a.9' and meta['protocol'] == wire.PROTOCOL and
               meta['status'] == 'PASS_SEALED_OPENFHE_REFERENCE' and
               wire.digest((root / 'offline_files.py').read_bytes()) == meta['runner_sha256'], 'wrong g_a.9 bundle')
    schedule = [row for row in wire.schedule('g_a.9') if row[4:] == (0, 0)]
    wire.check(len(schedule) == 24, 'unexpected short-test tile count')
    request_bytes = sum(28 + 8*l + wire.payload_size(l, flags) for _, l, _, flags, _, _ in schedule)
    count = (request_bytes + wire.PART_BYTES-1)//wire.PART_BYTES
    entries = []
    for i in range(count):
        part = meta['parts'][i]
        name = wire.part_name(i)
        path = root / name
        wire.check(part['path'] == name and part['bytes'] == wire.PART_BYTES and path.is_file() and
                   path.stat().st_size == part['bytes'], f'missing or incomplete part {name}')
        entries.append((path, part['bytes'], part['sha256']))
    service = root.parent / 'v32_ga_live_20261111/serve_board.sh'
    command = [str(args.model.resolve(strict=True))] if args.model else ['sh', str(service)]
    print(f'GA9_IO_SHORT tiles={len(schedule)} parts={count} schedule=serial,prefetch,prefetch,serial', flush=True)
    trials = []
    for prefetch in (False, True, True, False):
        result = trial(wire, command, entries, schedule, meta['output_sha256'], args.model is None, prefetch)
        trials.append(result)
        print(f'PASS_TRIAL {len(trials)}/4 {result["mode"]} wall_s={result["wall_ns"]/1e9:.3f}', flush=True)
    median = {mode: statistics.median(row['wall_ns'] for row in trials if row['mode'] == mode)
              for mode in ('serial', 'prefetch')}
    wire.save_json(args.output, dict(status='PASS_GA9_IO_SHORT', backend='model' if args.model else 'pure_pl',
                   manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(), request_bytes=request_bytes,
                   part_bytes_read=sum(size for _, size, _ in entries), trials=trials, median_wall_ns=median,
                   prefetch_reduction_percent=100*(1-median['prefetch']/median['serial']),
                   timing_scope='Each trial times 24 tiles with exact SHA256 verification, after server handshake. '
                                'File work and pipe/server timings can overlap. File reads can hit page cache. '
                                'The existing server measures input receive, range check and BO sync together.'))
    print(f'PASS_GA9_IO_SHORT backend={"model" if args.model else "pure_pl"} results={args.output}', flush=True)


if __name__ == '__main__':
    main()
