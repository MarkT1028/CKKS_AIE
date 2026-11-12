"""Capture or replay the complete g_a layer wire stream in transferable parts."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

HELLO, REQUEST, REPLY, STOP = (0x47413148, 0x47413151, 0x47413152, 0x47413153)
LAYERS = {'g_a.6': (49, 8, 4), 'g_a.9': (45, 4, 6)}
PART_BYTES = 32 * 2**20
PROTOCOL = 'v32_ga_offline_full_v1'


def check(ok, message):
    if not ok:
        raise RuntimeError(message)


def exact(stream, size):
    data = stream.read(size)
    check(len(data) == size, 'truncated offline stream')
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def part_name(number):
    return f'parts/batch_{number//32 + 1:02}/part_{number:04}.part'


def save_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(value, file, indent=2)
        file.write('\n')


class PartsWriter:
    def __init__(self, root):
        self.root, self.parts = root, []
        self.file = None

    def write(self, data):
        remaining = memoryview(data)
        while remaining:
            if self.file is None:
                self.name = part_name(len(self.parts))
                path = self.root / self.name
                path.parent.mkdir(parents=True, exist_ok=True)
                self.file = path.open('xb')
                self.sha, self.size = hashlib.sha256(), 0
            span = remaining[:PART_BYTES-self.size]
            self.file.write(span)
            self.sha.update(span)
            self.size += len(span)
            remaining = remaining[len(span):]
            if self.size == PART_BYTES:
                self.finish_part()

    def finish_part(self):
        if self.file is not None:
            self.file.close()
            self.parts.append(dict(path=self.name, bytes=self.size, sha256=self.sha.hexdigest()))
            self.file = None


class PartsReader:
    def __init__(self, root, parts, total):
        check(len(parts) == (total + PART_BYTES-1)//PART_BYTES, 'incorrect number of input parts')
        self.root, self.parts, self.total = root, parts, total
        self.part, self.offset, self.position, self.data = 0, 0, 0, b''

    def read(self, size):
        out = bytearray()
        while len(out) < size and self.position < self.total:
            if self.offset == len(self.data):
                meta = self.parts[self.part]
                name = part_name(self.part)
                size_wanted = min(PART_BYTES, self.total-self.position)
                path = self.root / name
                check(meta['path'] == name and meta['bytes'] == size_wanted and path.is_file()
                      and path.stat().st_size == size_wanted, f'missing or invalid part {name}')
                self.data = path.read_bytes()
                check(len(self.data) == size_wanted and digest(self.data) == meta['sha256'], f'part SHA256 mismatch {name}')
                self.part += 1
                self.offset = 0
            span = memoryview(self.data)[self.offset:self.offset+size-len(out)]
            out.extend(span)
            self.offset += len(span)
            self.position += len(span)
        return out


def schedule(layer):
    towers, outputs, groups = LAYERS[layer]
    tile = 0
    for tower in range(0, towers, 16):
        l = min(16, towers-tower)
        for coefficient in range(0, 131072, 8192):
            for output in range(outputs):
                for group in range(groups):
                    tile += 1
                    flags = int(output != 0) | (2 if group else 0)
                    yield tile, l, group, flags, tower, coefficient


def request_size(layer):
    return 4 + sum(28 + 8*l + payload_size(l, flags) for _, l, _, flags, _, _ in schedule(layer))


def payload_size(l, flags):
    return 8192*l*16*16*(2-(flags & 1)-(flags >> 1))


def exchange(source, child, layer, expected, record=None, forward=None):
    count, output_words = 0, 0
    rows = []
    for tile, l, group, flags, _, _ in schedule(layer):
        header = exact(source, 28)
        check(struct.unpack('<7I', header) == (REQUEST, tile, 8192, l, 16, group, flags), f'tile schedule differs at {tile}')
        moduli = exact(source, 8*l)
        child.stdin.write(header)
        child.stdin.write(moduli)
        if record is not None:
            record.write(header)
            record.write(moduli)
        remaining = payload_size(l, flags)
        while remaining:
            data = exact(source, min(remaining, 4*2**20))
            child.stdin.write(data)
            if record is not None:
                record.write(data)
            remaining -= len(data)
        child.stdin.flush()
        reply = exact(child.stdout, 36)
        op, identity, n, actual_l, k, receive_sync, run = struct.unpack('<5I2Q', reply)
        check((op, identity, n, actual_l, k) == (REPLY, tile, 8192, l, 16), f'tile reply differs at {tile}')
        raw = exact(child.stdout, n*l*3*8)
        sha = digest(raw)
        if expected is not None:
            check(sha == expected[tile-1], f'OpenFHE output SHA256 mismatch at tile {tile}')
        if forward is not None:
            forward.write(reply)
            forward.write(raw)
            forward.flush()
        rows.append(dict(tile=tile, sha256=sha, receive_sync_ns=receive_sync, run_ns=run))
        count += 1
        output_words += n*l*3
        if count % 256 == 0:
            print(f'GA_OFFLINE_PROGRESS {layer} tiles={count}', file=sys.stderr, flush=True)
    stop = exact(source, 4)
    check(struct.unpack('<I', stop) == (STOP,), 'invalid end of offline stream')
    if record is not None:
        record.write(stop)
        record.finish_part()
    else:
        check(not source.read(1), 'extra offline input bytes')
    child.stdin.write(stop)
    child.stdin.close()
    check(child.wait(timeout=15) == 0, 'server exit failed')
    return rows, output_words


def transfer(source, command, layer, hardware, expected=None, record=None, forward=None):
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
        try:
            hello = exact(child.stdout, 8)
            check(struct.unpack('<II', hello) == (HELLO, int(hardware)), 'wrong server backend')
            if forward is not None:
                forward.write(hello)
                forward.flush()
            return exchange(source, child, layer, expected, record, forward)
        except BaseException:
            if child.poll() is None:
                child.terminate()
            raise
        finally:
            if record is not None and record.file is not None:
                record.file.close()


def capture(args):
    writer = PartsWriter(args.root)
    rows, words = transfer(sys.stdin.buffer, [str(args.model.resolve(strict=True))], args.layer, False,
                           record=writer, forward=sys.stdout.buffer)
    total = sum(p['bytes'] for p in writer.parts)
    check(total == request_size(args.layer), 'request size differs from complete schedule')
    save_json(args.root / 'capture.json', dict(protocol=PROTOCOL, layer=args.layer, request_bytes=total,
              verified_words=words, tiles=len(rows), parts=writer.parts, output_sha256=[r['sha256'] for r in rows]))


def replay(args):
    check(not args.output.exists(), 'choose a new receipt path')
    manifest = (args.root / 'manifest.json').read_bytes()
    meta = json.loads(manifest)
    check(meta['protocol'] == PROTOCOL and meta['status'] == 'PASS_SEALED_OPENFHE_REFERENCE', 'fixture not sealed')
    layer = meta['layer']
    expected = meta['output_sha256']
    count = sum(1 for _ in schedule(layer))
    check(meta['tiles'] == count and len(expected) == count and meta['request_bytes'] == request_size(layer), 'fixture coverage differs')
    source = PartsReader(args.root, meta['parts'], meta['request_bytes'])
    service = args.root.parent / 'v32_ga_live_20261111/serve_board.sh'
    command = [str(args.model.resolve(strict=True))] if args.model else ['sh', str(service)]
    start = time.perf_counter()
    rows, words = transfer(source, command, layer, not args.model, expected=expected)
    check(words == meta['verified_words'] and len(rows) == count, 'result coverage differs')
    save_json(args.output, dict(status='PASS_GA_OFFLINE_FULL', backend='model' if args.model else 'pure_pl',
              manifest_sha256=digest(manifest), layer=layer, tiles=count, verified_words=words,
              runner_wall_seconds=time.perf_counter()-start, results=rows))
    print(f'PASS_GA_OFFLINE_FULL layer={layer} backend={"model" if args.model else "pure_pl"} tiles={count} verified_words={words}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    c = sub.add_parser('capture')
    c.add_argument('layer', choices=LAYERS)
    c.add_argument('root', type=Path)
    c.add_argument('model', type=Path)
    r = sub.add_parser('replay')
    r.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    r.add_argument('--output', type=Path, required=True)
    r.add_argument('--model', type=Path)
    args = parser.parse_args()
    (capture if args.mode == 'capture' else replay)(args)


if __name__ == '__main__':
    main()
