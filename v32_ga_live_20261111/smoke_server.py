"""Small exact test of both lanes, all six weight slots, and tile reuse."""
from array import array
from pathlib import Path
import argparse
import random
import struct
import subprocess
import sys

HELLO, REQUEST, REPLY, STOP = (0x47413148, 0x47413151, 0x47413152, 0x47413153)


def exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise RuntimeError('server closed its reply pipe')
    return data


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    check(sys.byteorder == 'little', 'little-endian host required')
    command = [str(args.model.resolve())] if args.model else ['sh', str(Path(__file__).with_name('serve_board.sh').resolve())]
    n, k = 128, 16
    rng = random.Random(911)
    completed = 0
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as p:
        try:
            check(struct.unpack('<II', exact(p.stdout, 8)) == (HELLO, int(not args.model)), 'server handshake differs')
            for qs in ((2**45-55, 2**45-61), (2**45-67,)):
                l = len(qs)

                def operand():
                    return array('Q', (rng.randrange(q) for _ in range(k) for q in qs for _ in range(2*n)))

                weights = [operand() for _ in range(6)]
                for output in range(2):
                    baby = operand()
                    for g, weight in enumerate(weights):
                        completed += 1
                        p.stdin.write(struct.pack('<7I', REQUEST, completed, n, l, k, g, int(bool(output)) | (2 if g else 0)))
                        p.stdin.write(struct.pack('<' + 'Q'*l, *qs))
                        if not output:
                            p.stdin.write(weight.tobytes())
                        if not g:
                            p.stdin.write(baby.tobytes())
                        p.stdin.flush()
                        header = struct.unpack('<5I2Q', exact(p.stdout, 36))
                        check(header[:5] == (REPLY, completed, n, l, k), 'reply identity differs')
                        result = array('Q')
                        result.frombytes(exact(p.stdout, n*l*3*8))
                        for t, q in enumerate(qs):
                            for j in range(n):
                                x, y, z = 0, 0, 0
                                for term in range(k):
                                    i = ((term*l+t)*n+j)*2
                                    a0,a1 = weight[i:i+2]
                                    b0,b1 = baby[i:i+2]
                                    x += a0*b0
                                    y += a0*b1+a1*b0
                                    z += a1*b1
                                i = (t*n+j)*3
                                check(tuple(result[i:i+3]) == (x%q,y%q,z%q), 'tile residue mismatch')
            p.stdin.write(struct.pack('<I', STOP))
            p.stdin.close()
            check(p.wait(timeout=15) == 0, 'server exit failure')
        except BaseException:
            if p.poll() is None:
                p.terminate()
            raise
    print(f'PASS_GA_SERVER_SMOKE backend={"model" if args.model else "pure_pl"} tiles={completed} slots=6')


if __name__ == '__main__':
    main()
