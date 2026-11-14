"""Run the sealed g_a.0 ciphertext-plaintext pilot on the existing PL service."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SERVICE = ROOT.parent / 'v32_ga_live_20261111' / 'serve_board.sh'
HELLO, REQUEST, REPLY, STOP = (0x47413148, 0x47413151, 0x47413152, 0x47413153)
N, K, GROUPS, OUTPUTS, RING = 128, 16, 4, (0, 15), 131072


def require(value, message):
    if not value:
        raise RuntimeError(message)


def exact(stream, count):
    data = stream.read(count)
    require(len(data) == count, f'truncated stream, expected {count} bytes')
    return data


def load_fixture():
    meta = json.loads((ROOT / 'fixture.json').read_text(encoding='utf-8'))
    l = meta['L']
    require(meta['layer'] == 'g_a.0' and meta['full_N'] == RING and l == 57
            and meta['tile_N'] == N and meta['K'] == K and meta['groups_per_output'] == GROUPS
            and meta['outputs'] == list(OUTPUTS) and meta['complete_layer'] is False
            and meta['output_level'] == 0 and meta['output_scale_degree'] == 2
            and meta['tiles'] == len(OUTPUTS) * GROUPS * ((l + 15) // 16)
            and meta['verified_words'] == len(OUTPUTS) * GROUPS * l * N * 3,
            'pilot metadata coverage differs')
    header = len(OUTPUTS) * GROUPS * (((l + 15) // 16) * 28 + l * 8)
    inputs = len(OUTPUTS) * GROUPS * l * N * K * 32
    for name, size in [('request.bin', header + inputs + 4),
                       ('reference.bin', meta['verified_words'] * 8)]:
        path = ROOT / name
        require(not path.is_symlink() and path.stat().st_size == size == meta['files'][name]['bytes'],
                f'{name} size differs')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == meta['files'][name]['sha256'],
                f'{name} digest differs')
    return meta


def replay(meta, model):
    command = [str(model.resolve(strict=True))] if model else ['sh', str(SERVICE)]
    hardware = int(model is None)
    tiles = []
    moduli = {}
    with (ROOT/'request.bin').open('rb') as request, (ROOT/'reference.bin').open('rb') as reference, \
            subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
        try:
            require(struct.unpack('<II', exact(child.stdout, 8)) == (HELLO, hardware),
                    'wrong service backend')
            for output in OUTPUTS:
                for group in range(GROUPS):
                    for tower in range(0, meta['L'], 16):
                        ident = len(tiles) + 1
                        l = min(16, meta['L'] - tower)
                        header = exact(request, 28 + l * 8)
                        fields = struct.unpack_from('<7I', header)
                        require(fields == (REQUEST, ident, N, l, K, group, 0),
                                f'wrong pilot schedule at tile {ident}')
                        qs = struct.unpack_from(f'<{l}Q', header, 28)
                        require(all(2**44 <= q < 2**60 and q % 2 for q in qs)
                                and moduli.setdefault(tower, qs) == qs, 'invalid RNS basis')
                        payload = exact(request, N * l * K * 32)
                        expected = exact(reference, N * l * 24)
                        begin = time.perf_counter_ns()
                        child.stdin.write(header)
                        child.stdin.write(payload)
                        child.stdin.flush()
                        reply = struct.unpack('<5I2Q', exact(child.stdout, 36))
                        require(reply[:5] == (REPLY, ident, N, l, K), f'wrong reply for tile {ident}')
                        raw = exact(child.stdout, len(expected))
                        require(raw == expected, f'OpenFHE RNS mismatch at tile {ident}')
                        require(all(z == 0 for _, _, z in struct.iter_unpack('<QQQ', raw)),
                                f'nonzero third component at tile {ident}')
                        digest = hashlib.sha256(raw).hexdigest()
                        resident = time.perf_counter_ns() - begin
                        tiles.append(dict(tile=ident, output=output, group=group, tower=tower, L=l,
                                          first_coefficient=RING-N if output else 0, sha256=digest,
                                          resident_ns=resident, receive_sync_ns=reply[5], run_ns=reply[6]))
            stop = exact(request, 4)
            require(struct.unpack('<I', stop) == (STOP,) and not request.read(1) and not reference.read(1),
                    'invalid pilot ending')
            child.stdin.write(stop)
            child.stdin.close()
            require(child.wait(timeout=15) == 0, 'service exit failed')
        except BaseException:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            raise
    require(len(tiles) == meta['tiles'] and sum(N * row['L'] * 3 for row in tiles) == meta['verified_words'],
            'verified pilot coverage differs')
    return tiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, help='local software verification')
    parser.add_argument('--output', type=Path, default=ROOT/'ga0_pilot_result.json')
    args = parser.parse_args()
    require(not args.output.exists(), 'choose a new result file')
    start = time.perf_counter()
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=ROOT, check=True)
    meta = load_fixture()
    tiles = replay(meta, args.model)
    result = dict(status='PASS_GA0_CTPT_PILOT', layer=meta['layer'],
                  backend='model' if args.model else 'pure_pl', complete_layer=False,
                  outputs=meta['outputs'], full_N=meta['full_N'], L=meta['L'], tile_N=N, K=K,
                  tiles=len(tiles), verified_words=meta['verified_words'],
                  sample_resident_seconds=sum(tile['resident_ns'] for tile in tiles)/1e9,
                  runner_wall_seconds=time.perf_counter()-start, results=tiles,
                  fixture_sha256=hashlib.sha256((ROOT/'fixture.json').read_bytes()).hexdigest(),
                  timing_scope='Selected tiles only. Resident includes pipe transfer, BO synchronization, '
                               'PL wait, output readback and exact verification. Pre-timer input reads are excluded.')
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, indent=2)
        file.write('\n')
    print('PASS_GA0_CTPT_PILOT backend={} tiles={} verified_words={}'.format(
        result['backend'], result['tiles'], result['verified_words']))
    print(f'RESULTS={args.output.resolve()}')


if __name__ == '__main__':
    main()
