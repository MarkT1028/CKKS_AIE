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
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'common'))
from ga_all_board import boot_uuid as hardware_uuid, executable, input_source, read_ahead, selected_image

PACKAGES = ROOT.parent.parent
SPLIT = PACKAGES / 'v32_ga3_splitbo_20261109'
RESIDENT = PACKAGES / 'v32_ga_resident_20261114'
N, RING, TOWERS, PER_BLOCK, OUTPUTS, GROUPS, K = 8192, 131072, 57, 4, 16, 4, 16
BLOCKS, COEFFS = (TOWERS + PER_BLOCK - 1)//PER_BLOCK, RING//N
DEPENDENCIES = {
    RESIDENT / 'run_board.py': 'ac7837ea8e297f8b9000092058bfecccbfe04da5789a69c50d54ba36012f5c15',
    PACKAGES / 'v32_ga0_full_20261114/ga0.hpp': '7ce926a6fb06fff78b2a26dee9d9a9717e3861c747b5177240c3aef2767866a4',
    PACKAGES / 'v32_ga3_finishopt_20261110/common/sealed_sha256.hpp': '2947ca4c2879ee151ec1342481d2d7f3d02568116778b1a6ffe65a2ae8f402fe',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def board_check():
    subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS_PACKAGE'], cwd=ROOT.parent, check=True)
    for path, digest in DEPENDENCIES.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'wrong dependency {path}')
    spec = importlib.util.spec_from_file_location('ga_resident_board', RESIDENT / 'run_board.py')
    resident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resident)
    board, _ = resident.package_check()
    print('PASS_GA0_CTPT_COMPACT_PACKAGE', flush=True)
    return board, resident


def payload_name(kind, a, b, c=0):
    return f'data/{kind}_{a:02}_{b:02}_{c:02}.bin'


def fixture_check(root, resident, network=False):
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
        if not (network and name.startswith('data/')):
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
    words, tiles, uploaded, readback = 0, 0, 0, 0
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
                        uploaded += N*l*K*8*(1+2*(out==0))
                        readback += N*l*2*8
                        for field, value in row.items():
                            if field.endswith('_ms'):
                                duration = float(value)
                                require(math.isfinite(duration) and duration >= 0, 'invalid tile timing')
                                stage_work_ms[field] = stage_work_ms.get(field, 0) + duration
        require(next(rows, None) is None, 'extra result tiles')
    coordinates = [(g, block * PER_BLOCK, c * N)
                   for g in range(GROUPS)
                   for block in (range(BLOCKS) if scope == 'full' else (0, BLOCKS - 1))
                   for c in (range(COEFFS) if scope == 'full' else (0, COEFFS - 1))]
    resident_ms = 0.0
    with (result / 'windows.csv').open(encoding='ascii', newline='') as file:
        rows = csv.DictReader(file)
        for expected in coordinates:
            row = next(rows, None)
            require(row and tuple(int(row[k]) for k in ('group','tower','coefficient')) == expected
                    and int(row['tiles']) == (OUTPUTS if scope == 'full' else 2), 'window coverage differs')
            elapsed = float(row['wall_ms'])
            require(math.isfinite(elapsed) and elapsed > 0, 'invalid window wall time')
            resident_ms += elapsed
        require(next(rows, None) is None, 'extra result windows')
    require(native['tiles'] == tiles and native['verified_words'] == words
            and native['uploaded_bytes'] == uploaded and native['device_readback_bytes'] == readback and abs(native['resident_ms']-resident_ms) < 0.01,
            'coverage or elapsed time differs')
    if scope == 'full':
        expected_input = GROUPS*K*RING*8*(TOWERS*2+OUTPUTS)
        expected_upload = GROUPS*K*RING*TOWERS*8*(OUTPUTS+2)
        require(tiles == meta['tiles'] and words == meta['verified_words']
                and native['read_bytes'] == expected_input and uploaded == expected_upload,
                'full scope differs')
    return native, stage_work_ms


def collect(result):
    import tarfile
    files = ('summary.json', 'native.json', 'tiles.csv', 'windows.csv',
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
    source = input_source()
    profile = os.environ.get('V32_GA_OPT_PROFILE', 'baseline')
    require(profile in ('baseline', 'fast'), 'invalid GA0 host profile')
    meta, fixture_hash = fixture_check(root, resident, source=='net')
    label,image = selected_image()
    image.check_xclbin()
    binary = executable('ga0', 'ga0_ctpt')
    subprocess.run(['sha256sum', '-c', 'BUILD_SHA256'], cwd=binary.parent, check=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    uuid = hardware_uuid()
    result = ROOT / f'results_ga0_{label}_{args.scope}_{profile}_{source}_{stamp}'
    with board.lock():
        env = board.environment()
        board.guard_recovery(env)
        require(env['boot_uuid'] == uuid and 'ga0' in image.layers, f'incompatible boot for {image.variant}')
        marker = Path('/run/v32-ga0-full-active-' + env['boot_id'])
        for prefix in ('v32-ga0-full-active-', 'v32-ga-live-active-', 'v32-ga-resident-active-'):
            require(not Path('/run', prefix+env['boot_id']).exists(), 'previous PL run interrupted')
        result.mkdir()
        resident.write_json(result/'environment_before.json', env)
        cmd = [str(binary), str(image.xclbin), str(marker), str(root), str(result), args.scope]

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
            require(native['input_source'] == source and native['host_profile'] == profile
                    and native['ntt_fused_stages'] is (profile=='fast')
                    and native['plaintext_pipeline'] is (profile=='fast')
                    and native['packing_in_resident'] is True and native['ntt_workers'] == 2,
                    'host profile or NTT accounting differs')
            prefetch = profile=='fast' and read_ahead()
            expected_blocks = GROUPS*(BLOCKS if args.scope=='full' else 2) if prefetch else 0
            require(native['weight_prefetch_enabled'] is prefetch and native['prefetched_weight_blocks'] == expected_blocks and
                    all(math.isfinite(native[k]) and native[k]>=0 for k in
                        ('weight_prefetch_work_ms','weight_prefetch_wait_ms')), 'prefetch coverage differs')
            after = board.environment()
            require(after['boot_id'] == env['boot_id'] and after['boot_uuid'] == uuid,
                    'board identity changed')
            resident.write_json(result/'environment_after.json', after)
            summary = dict(status='PASS_GA0_CTPT_'+args.scope.upper(), layer='g_a.0',
                           complete_raw_mac_coverage=args.scope=='full', boot_uuid=uuid, hardware_variant=image.variant,
                           aie_compute_tiles=0, fixture_sha256=fixture_hash, **native,
                           stage_work_ms=stages, resident_seconds=native['resident_ms']/1000,
                           read_seconds=native['read_ms']/1000,
                           packing_and_resident_seconds=(native['slice_ms']+native['resident_ms'])/1000,
                           preloaded_including_ntt_and_slice_seconds=(
                               native['resident_ms']+native['ntt_ms']+native['slice_ms'])/1000,
                           request_seconds=native['request_ms']/1000,
                           process_wall_seconds=wall, timing_scope={
                               'read_ms': 'Summed input read or receive work. Overlaps NTT with the fast profile.',
                               'ntt_ms': 'ARM reconstruction of all requested plaintext RNS towers.',
                               'resident_ms': 'Packing, compact BO uploads/readback, PL execution, canonical zero reconstruction and complete SHA256.',
                               'packing_and_resident_seconds': 'BO preparation, launch/wait, readback and output SHA256.',
                               'device_readback_bytes': 'Logical two-component output synchronization size, both lanes.',
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
    parser.add_argument('scope', choices=('check','detect','smoke','full','collect'))
    parser.add_argument('--data', type=Path, default=PACKAGES/'v32_ga0_full_20261114'/'fixture')
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    if args.scope == 'collect':
        require(args.result is not None, 'collect requires --result')
        collect(args.result.resolve(strict=True))
        return
    board, resident = board_check()
    if args.scope == 'detect':
        env = board.environment()
        print(json.dumps(dict(
            active_uuid=env['boot_uuid'], expected_compact_uuid=hardware_uuid(),
            matching=env['boot_uuid'] == hardware_uuid(),
            boot_id=env['boot_id']), indent=2))
        return
    if args.scope == 'check':
        meta, _ = fixture_check(args.data.resolve(strict=True), resident, input_source()=='net')
        print(f'PASS_GA0_FIXTURE_INDEX tiles={meta["tiles"]} compact_uuid={hardware_uuid()}')
    else:
        run(args, board, resident)


if __name__ == '__main__':
    main()
