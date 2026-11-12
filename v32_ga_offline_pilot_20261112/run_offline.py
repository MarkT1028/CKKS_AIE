"""Replay one genuine g_a.6 window against the already built board service."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
HELLO, REQUEST, REPLY, STOP = (0x47413148, 0x47413151, 0x47413152, 0x47413153)


def check(ok, message):
    if not ok:
        raise RuntimeError(message)


def exact(stream, count):
    data = stream.read(count)
    check(len(data) == count, 'truncated request or reply')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check(not args.output.exists(), 'choose a new output file')
    fixture = json.loads((ROOT / 'fixture.json').read_text(encoding='utf-8'))
    check(fixture['layer'] == 'g_a.6' and fixture['N'] == 131072 and fixture['L'] == 49
          and fixture['output'] == 0 and fixture['tower'] == 48 and fixture['first_coefficient'] == 130944,
          'unexpected fixture scope')
    for name, size in (('request.bin', 163988), ('reference.bin', 12288)):
        path = ROOT / name
        check(path.stat().st_size == size, f'{name} size mismatch')
        check(hashlib.sha256(path.read_bytes()).hexdigest() == fixture['sha256'][name], f'{name} SHA256 mismatch')
    command = [str(args.model.resolve())] if args.model else ['sh', str(ROOT.parent / 'v32_ga_live_20261111/serve_board.sh')]
    results, modulus = [], None
    start = time.perf_counter()
    with (ROOT / 'request.bin').open('rb') as req, (ROOT / 'reference.bin').open('rb') as ref, \
            subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
        try:
            hardware = int(args.model is None)
            check(struct.unpack('<II', exact(child.stdout, 8)) == (HELLO, hardware), 'wrong server handshake')
            for group in range(4):
                header = exact(req, 36)
                op, tile, n, l, k, slot, flags, q = struct.unpack('<7IQ', header)
                check((op, tile, n, l, k, slot, flags) == (REQUEST, group+1, 128, 1, 16, group, 2 if group else 0),
                      'unexpected request schedule')
                check(2**44 <= q < 2**60 and q % 2 and (modulus is None or q == modulus), 'unexpected modulus')
                modulus = q
                child.stdin.write(header + exact(req, 32768 * (1 if group else 2)))
                child.stdin.flush()
                reply = struct.unpack('<5I2Q', exact(child.stdout, 36))
                check(reply[:5] == (REPLY, tile, n, l, k), 'reply identity mismatch')
                actual = exact(child.stdout, 3072)
                check(actual == exact(ref, 3072), f'OpenFHE residue mismatch in group {group}')
                results.append(dict(group=group, output_sha256=hashlib.sha256(actual).hexdigest(),
                                    receive_sync_ns=reply[5], run_ns=reply[6]))
            stop = exact(req, 4)
            check(struct.unpack('<I', stop) == (STOP,) and not req.read(1) and not ref.read(1), 'invalid fixture ending')
            child.stdin.write(stop)
            child.stdin.close()
            check(child.wait(timeout=15) == 0, 'server exit failed')
        except BaseException:
            if child.poll() is None:
                child.terminate()
            raise
    result = dict(status='PASS_GA6_OFFLINE_PILOT', backend='pure_pl' if hardware else 'model',
                  fixture_sha256=fixture['sha256'], layer='g_a.6', output=0, groups=4,
                  N_tile=128, L_tile=1, RNS_tower=48, first_coefficient=130944,
                  verified_words=4*128*3, complete_layer=False, results=results,
                  runner_wall_seconds=time.perf_counter()-start)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, indent=2)
        file.write('\n')
    print(f'PASS_GA6_OFFLINE_PILOT backend={result["backend"]} groups=4 verified_words=1536')
    print(f'RESULTS={args.output.resolve()}')


if __name__ == '__main__':
    main()
