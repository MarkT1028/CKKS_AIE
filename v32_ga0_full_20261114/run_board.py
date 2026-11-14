"""Run and verify the complete g_a.0 ciphertext-plaintext replay."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SPLIT = ROOT.parent / 'v32_ga3_splitbo_20261109'
RESIDENT = ROOT.parent / 'v32_ga_resident_20261114'
VARIANT = 'v32_native_splitbo_2_pipe'
UUID = '9bee253b8f345f39bd9c18d612897ce3'
N, RING, TOWERS, PER_BLOCK, OUTPUTS, GROUPS, K = 8192, 131072, 57, 4, 16, 4, 16
BLOCKS, COEFFS = (TOWERS + PER_BLOCK - 1)//PER_BLOCK, RING//N
DEPENDENCIES = {
    RESIDENT / 'run_board.py': 'ac7837ea8e297f8b9000092058bfecccbfe04da5789a69c50d54ba36012f5c15',
    RESIDENT / 'backend.hpp': 'e9632d9922e650dcdc28652a75c87bcaacdbca404552453e2fbdbbe1d2d499a1',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def board_check():
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS_PACKAGE'], cwd=ROOT, check=True)
    for path, digest in DEPENDENCIES.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'wrong dependency {path}')
    spec = importlib.util.spec_from_file_location('ga_resident_board', RESIDENT / 'run_board.py')
    resident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resident)
    board, _ = resident.package_check()
    print('PASS_GA0_FULL_PACKAGE', flush=True)
    return board, resident


def payload_name(kind, a, b, c=0):
    return f'data/{kind}_{a:02}_{b:02}_{c:02}.bin'


def fixture_check(root, resident):
    manifest = root / 'fixture.json'
    expected = (ROOT / 'FIXTURE_SHA256').read_text(encoding='ascii').strip()
    require(resident.sha(manifest) == expected, 'fixture manifest SHA256 differs')
    meta = json.loads(manifest.read_bytes())
    require(meta['layer'] == 'g_a.0' and meta['complete_raw_mac_coverage'] is True
            and meta['full_N'] == RING and meta['L'] == TOWERS
            and meta['tile_N'] == N and meta['K'] == K and meta['groups_per_output'] == GROUPS
            and meta['output_level'] == 0 and meta['output_scale_degree'] == 2
            and meta['tiles'] == BLOCKS * COEFFS * OUTPUTS * GROUPS
            and meta['outputs'] == list(range(OUTPUTS))
            and len(meta['files']) == GROUPS * BLOCKS * COEFFS + OUTPUTS * GROUPS + 2,
            'fixture coverage differs')
    sizes = {'basis.txt': None, 'expected.txt': meta['tiles'] * 65}
    sizes.update((payload_name('p', out, group), K*RING*8)
                 for out in range(OUTPUTS) for group in range(GROUPS))
    sizes.update((payload_name('a', group, block, c), K*min(PER_BLOCK,TOWERS-block*PER_BLOCK)*N*16)
                 for group in range(GROUPS) for block in range(BLOCKS) for c in range(COEFFS))
    require(set(sizes) == set(meta['files']), 'unexpected fixture paths')
    for name, size in sizes.items():
        entry = meta['files'][name]
        file = root / name
        require(file.is_file() and not file.is_symlink() and file.stat().st_size == entry['bytes'],
                f'missing or wrong size: {file}')
        if size is not None:
            require(entry['bytes'] == size, f'invalid fixture shape: {file}')
    expected_index = ''.join(f'{name}\t{entry["sha256"]}\n' for name, entry in meta['files'].items()).encode('ascii')
    require((root/'INDEX.tsv').read_bytes() == expected_index, 'fixture index differs from sealed manifest')
    return meta, expected


def audit(result, meta, scope, root):
    gold = (root / 'expected.txt').read_text(encoding='ascii').splitlines()
    require(len(gold) == meta['tiles'], 'expected tile count differs')
    native = json.loads((result / 'native.json').read_bytes())
    words, tiles, uploaded = 0, 0, 0
    stage_work_ms = {}
    with (result / 'tiles.csv').open(encoding='ascii', newline='') as file:
        rows = csv.DictReader(file)
        for group in range(GROUPS):
            for block in (range(BLOCKS) if scope == 'full' else (0, BLOCKS - 1)):
                tower = block * PER_BLOCK
                l = min(PER_BLOCK, TOWERS - tower)
                for c in (range(COEFFS) if scope == 'full' else (0, COEFFS - 1)):
                    for out in (range(OUTPUTS) if scope == 'full' else (0, OUTPUTS - 1)):
                        row = next(rows, None)
                        ident = ((group*BLOCKS+block)*COEFFS+c)*OUTPUTS+out+1
                        require(row and [int(row[k]) for k in ('tile','output','group','tower','L','coefficient')]
                                == [ident, out, group, tower, l, c*N] and row['sha256'] == gold[ident-1],
                                f'tile {ident} result mismatch')
                        tiles += 1
                        words += N*l*3
                        uploaded += N*l*K*16*(1+(out==0))
                        for field, value in row.items():
                            if field.endswith('_ms'):
                                duration = float(value)
                                require(math.isfinite(duration) and duration >= 0, 'invalid tile timing')
                                stage_work_ms[field] = stage_work_ms.get(field, 0) + duration
        require(next(rows, None) is None, 'extra result tiles')
    resident_ms = stage_work_ms.pop('resident_ms')
    require(native['tiles'] == tiles and native['verified_words'] == words
            and native['uploaded_bytes'] == uploaded and abs(native['resident_ms']-resident_ms) < 0.01,
            'coverage or elapsed time differs')
    if scope == 'full':
        expected_input = GROUPS*K*RING*8*(TOWERS*2+OUTPUTS)
        expected_upload = GROUPS*K*RING*TOWERS*16*(OUTPUTS+1)
        require(tiles == meta['tiles'] and words == meta['verified_words']
                and native['read_bytes'] == expected_input and uploaded == expected_upload,
                'full scope differs')
    return native, stage_work_ms


def collect(result):
    import tarfile
    files = ('summary.json', 'native.json', 'tiles.csv',
             'environment_before.json', 'environment_after.json')
    receipt = json.loads((result/'summary.json').read_bytes())
    require(receipt['status'] in ('PASS_GA0_CTPT_SMOKE', 'PASS_GA0_CTPT_FULL'),
            'completed board result required')
    archive = result.with_suffix('.tar.gz')
    with tarfile.open(archive, 'x:gz', compresslevel=1) as stream:
        for name in files:
            stream.add(result/name, arcname=f'{result.name}/{name}', recursive=False)
    print(f'DOWNLOAD={archive}')


def run(args, board, resident):
    root = args.data.resolve(strict=True)
    meta, fixture_hash = fixture_check(root, resident)
    subprocess.run(['sha256sum', '-c', 'bin/BUILD_SHA256'], cwd=ROOT, check=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    result = ROOT / f'results_ga0_{args.scope}_{stamp}'
    with board.lock():
        env = board.environment()
        board.guard_recovery(env)
        require(env['boot_uuid'] == UUID, f'expected {VARIANT}, current UUID {env["boot_uuid"]}')
        marker = Path('/run/v32-ga0-full-active-' + env['boot_id'])
        for prefix in ('v32-ga0-full-active-', 'v32-ga-live-active-', 'v32-ga-resident-active-'):
            require(not Path('/run', prefix+env['boot_id']).exists(), 'previous PL run interrupted')
        result.mkdir()
        resident.write_json(result/'environment_before.json', env)
        xclbin = SPLIT / 'variants' / VARIANT / 'ckks_hw_boot.xclbin'
        cmd = [str(ROOT/'bin/ga0_full'), str(xclbin), str(marker), str(root), str(result), args.scope]

        def stop(number, _frame):
            raise SystemExit(128 + number)

        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(number, stop)
        child = None
        start = time.perf_counter()
        print(f'RESULTS={result}', flush=True)
        try:
            child = subprocess.Popen(cmd, start_new_session=True,
                                     env=dict(os.environ, XRT_INI_PATH=str(SPLIT/'configs/baseline.ini')))
            require(child.wait() == 0, 'native replay failed')
            wall = time.perf_counter() - start
            native, stages = audit(result, meta, args.scope, root)
            require(native['backend'] == 'pure_pl', 'wrong backend')
            after = board.environment()
            require(after['boot_id'] == env['boot_id'] and after['boot_uuid'] == UUID,
                    'board identity changed')
            resident.write_json(result/'environment_after.json', after)
            summary = dict(status='PASS_GA0_CTPT_'+args.scope.upper(), layer='g_a.0',
                           complete_raw_mac_coverage=args.scope=='full', boot_uuid=UUID,
                           aie_compute_tiles=0, fixture_sha256=fixture_hash, **native,
                           stage_work_ms=stages, resident_seconds=native['resident_ms']/1000,
                           read_seconds=native['read_ms']/1000,
                           preloaded_including_ntt_and_slice_seconds=(
                               native['resident_ms']+native['ntt_ms']+native['slice_ms'])/1000,
                           request_seconds=native['request_ms']/1000,
                           process_wall_seconds=wall, timing_scope={
                               'read_ms': 'Timed file reads. Includes any OS cache hits.',
                               'ntt_ms': 'ARM reconstruction of all requested plaintext RNS towers.',
                               'resident_ms': 'Preloaded tile BO uploads, PL execute, output readback and SHA256.',
                               'request_ms': 'Full requested replay, including file reads, SHA256 and NTT.',
                               'scope': 'Raw MAC groups. Layer aggregation and bias occur in the ground verifier.'})
            resident.write_json(result/'summary.json', summary)
            print(json.dumps(summary, indent=2))
        finally:
            if child is not None and child.poll() is None:
                board.stop_owned_child(child)
            if marker.exists():
                board.write(SPLIT/'RECOVERY_REQUIRED.json',
                            dict(boot_id=env['boot_id'], reason='interrupted ga0 PL invocation'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope', choices=('check','smoke','full','collect'))
    parser.add_argument('--data', type=Path, default=ROOT/'fixture')
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    if args.scope == 'collect':
        require(args.result is not None, 'collect requires --result')
        collect(args.result.resolve(strict=True))
        return
    board, resident = board_check()
    if args.scope == 'check':
        if args.data.exists():
            meta, _ = fixture_check(args.data.resolve(strict=True), resident)
            print(f'PASS_GA0_FIXTURE_INDEX tiles={meta["tiles"]}')
    else:
        run(args, board, resident)


if __name__ == '__main__':
    main()
