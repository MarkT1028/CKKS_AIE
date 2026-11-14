import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
SPLIT = ROOT.parent / 'v32_ga3_splitbo_20261109'
LIVE = ROOT.parent / 'v32_ga_live_20261111'
FINISH = ROOT.parent / 'v32_ga3_finishopt_20261110'
VARIANT = 'v32_native_splitbo_2_pipe'
UUID = '9bee253b8f345f39bd9c18d612897ce3'
PART_BYTES = 32 * 2**20
DEPENDENCIES = {
    SPLIT / 'SHA256SUMS_PACKAGE': '9046e08779347d8b766f5341264ca71fa24914b0a50fb2cd988f59661b0fa2a7',
    LIVE / 'wire.hpp': 'b1470ba01758b53577a69abfa57aa4bfdc71a9b3d2a1622f833e2cdd3a143a28',
    FINISH / 'common/sealed_sha256.hpp': '2947ca4c2879ee151ec1342481d2d7f3d02568116778b1a6ffe65a2ae8f402fe',
}
LAYERS = {
    'ga6': (49, 8, 4, '5709c423de20cdf36f9679b04955c75ad58c26495b12188930c4bea0943c8e28'),
    'ga9': (45, 4, 6, 'aaa859e2869fe6ca757b17f22ec7a59a93465fef4b489b794167f62f2a917868'),
}
BASELINE_SECONDS = 31.366680443


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as file:
        digest = hashlib.sha256()
        for block in iter(lambda: file.read(2**20), b''):
            digest.update(block)
        return digest.hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write('\n')


def package_check():
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS_PACKAGE'], cwd=ROOT, check=True)
    for path, digest in DEPENDENCIES.items():
        require(path.is_file() and sha(path) == digest, f'missing or changed dependency: {path}')
    sys.path.insert(0, str(SPLIT))
    import ga3_board
    ga3_board.board()
    return ga3_board, ga3_board.code_check()


def fixture(root, layer):
    towers, outputs, groups, digest = LAYERS[layer]
    blob = (root / 'manifest.json').read_bytes()
    require(hashlib.sha256(blob).hexdigest() == digest, f'{layer} manifest SHA256 differs')
    meta = json.loads(blob)
    blocks = ((towers + 15) // 16) * 16
    tiles = blocks * outputs * groups
    words = towers * 131072 * outputs * groups * 3
    payload_bytes = towers * 131072 * 16 * 16 * (outputs + groups)
    header_bytes = (28 * blocks + 8 * towers * 16) * outputs * groups
    size = payload_bytes + header_bytes + 4
    require(meta['protocol'] == 'v32_ga_offline_full_v1' and meta['layer'] == 'g_a.' + layer[-1]
            and meta['tiles'] == tiles and meta['verified_words'] == words
            and meta['request_bytes'] == size and len(meta['output_sha256']) == tiles,
            'fixture coverage differs')
    require(len(meta['parts']) == (size + PART_BYTES - 1) // PART_BYTES, 'fixture part count differs')
    for i, part in enumerate(meta['parts']):
        name = f'parts/batch_{i // 32 + 1:02}/part_{i:04}.part'
        path = root / name
        expected = min(PART_BYTES, size - i * PART_BYTES)
        require(part['path'] == name and part['bytes'] == expected and path.is_file()
                and not path.is_symlink() and path.stat().st_size == expected,
                f'missing or invalid input part: {path}')
    return meta


def check_result(result, meta, layer, scope):
    native = json.loads((result / 'native.json').read_text(encoding='utf-8'))
    towers, outputs, groups, _ = LAYERS[layer]
    blocks = ((towers + 15) // 16) * 16
    selected = range(blocks) if scope == 'full' else (0, blocks - 1)
    expected = [(block, output, group) for block in selected
                for output in range(outputs) for group in range(groups)]
    stage_totals = {}
    words = 0
    uploaded = 0
    with (result / 'tiles.csv').open(encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)
        for block, output, group in expected:
            row = next(reader, None)
            require(row is not None, 'missing result tile')
            ident = (block * outputs + output) * groups + group + 1
            l = min(16, towers - 16 * (block // 16))
            require(tuple(int(row[key]) for key in ('tile', 'block', 'output', 'group', 'L'))
                    == (ident, block, output, group, l)
                    and row['sha256'] == meta['output_sha256'][ident - 1], f'tile {ident} verification differs')
            words += 8192 * l * 3
            uploaded += 8192 * l * 16 * 16 * (int(output == 0) + int(group == 0))
            for stage, value in row.items():
                if stage.endswith('_ms'):
                    duration = float(value)
                    require(math.isfinite(duration) and duration >= 0, f'invalid {stage} duration')
                    stage_totals[stage] = stage_totals.get(stage, 0) + duration
        require(next(reader, None) is None, 'extra result tile')
    with (result / 'windows.csv').open(encoding='utf-8', newline='') as file:
        rows = list(csv.DictReader(file))
    require([(int(row['block']), int(row['output'])) for row in rows]
            == [(block, output) for block in selected for output in range(outputs)], 'window coverage differs')
    require(native['tiles'] == len(expected) and native['windows'] == len(rows)
            and native['verified_words'] == words and native['uploaded_bytes'] == uploaded,
            'native replay coverage differs')
    for field in ('resident_ms', 'admission_ms'):
        require(abs(sum(float(row[field]) for row in rows) - native[field]) < 0.01,
                f'{field} trace total differs')
    if scope == 'full':
        require(native['verified_parts'] == len(meta['parts'])
                and native['part_read_bytes'] == meta['request_bytes']
                and native['verified_words'] == meta['verified_words'], 'full replay byte count differs')
    return native, stage_totals


def run(args, board, package):
    root = args.data or ROOT.parent / f'v32_{args.layer}_offline_full_20261112'
    meta = fixture(root, args.layer)
    subprocess.run(['sha256sum', '-c', 'bin/BUILD_SHA256'], cwd=ROOT, check=True)
    binary_sha = sha(ROOT / 'bin/ga_resident')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    result = ROOT / f'results_{args.layer}_{args.scope}_{args.profile}_{stamp}'

    with board.lock():
        env = board.environment()
        board.guard_recovery(env)
        require(env['boot_uuid'] == UUID, f'boot {VARIANT} first; current UUID {env["boot_uuid"]}')
        marker = Path('/run/v32-ga-resident-active-' + env['boot_id'])
        live_marker = Path('/run/v32-ga-live-active-' + env['boot_id'])
        require(not marker.exists() and not live_marker.exists(), 'unfinished PL invocation; reboot the board')
        result.mkdir()
        index = result / 'sealed_index.txt'
        lines = [str(meta['request_bytes']), *(part['sha256'] for part in meta['parts']), *meta['output_sha256']]
        index.write_text('\n'.join(lines) + '\n', encoding='ascii')
        write_json(result / 'environment_before.json', env)
        command = [
            str(ROOT / 'bin/ga_resident'), str(SPLIT / 'variants' / VARIANT / 'ckks_hw_boot.xclbin'),
            str(marker), str(root.resolve()), str(index), str(result), args.layer, args.scope, args.profile,
        ]
        print(f'RESULTS={result}', flush=True)

        def stop(number, _frame):
            raise SystemExit(128 + number)

        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(number, stop)
        child = None
        start = time.perf_counter()
        try:
            child = subprocess.Popen(command, start_new_session=True,
                                     env=dict(os.environ, XRT_INI_PATH=str(SPLIT / 'configs/baseline.ini')))
            require(child.wait() == 0, 'native replay failed')
            wall_seconds = time.perf_counter() - start
            native, stage_totals = check_result(result, meta, args.layer, args.scope)
            require(native['backend'] == 'pure_pl', 'wrong execution backend')
            env_after = board.environment()
            require(env_after['boot_id'] == env['boot_id'] and env_after['boot_uuid'] == UUID,
                    'board identity changed during replay')
            write_json(result / 'environment_after.json', env_after)
            resident_seconds = native['resident_ms'] / 1000
            full = args.scope == 'full'
            summary = dict(
                status='PASS_GA_RESIDENT_FULL' if full else 'PASS_GA_RESIDENT_SMOKE',
                layer=meta['layer'], scope=args.scope, profile=args.profile, boot_uuid=UUID,
                firmware_changed=False, aie_compute_tiles=0, manifest_sha256=LAYERS[args.layer][3],
                package_sha256=sha(ROOT / 'SHA256SUMS_PACKAGE'),
                splitbo_manifest_sha256=package['manifest_sha256'],
                binary_sha256=binary_sha, **native, stage_work_ms=stage_totals,
                page_cache_policy='per_input_part_advisory_retirement_no_global_clear',
                process_wall_seconds=wall_seconds,
                ga3_reference_resident_seconds=BASELINE_SECONDS,
                resident_seconds=resident_seconds,
                measured_full_scope_meets_31_37s=(resident_seconds <= BASELINE_SECONDS) if full else None,
                timing_scope='Resident is the sum of measured per-window wall times after admission. '
                             'It includes first BO upload, synchronization, launch and wait, output readback '
                             'and exact full output SHA256. Request includes input part reads and hashes. '
                             'Setup is separate. Stage work can overlap. Scope is raw MAC replay.',
            )
            write_json(result / 'summary.json', summary)
            print(json.dumps(summary, indent=2))
        finally:
            if child is not None and child.poll() is None:
                board.stop_owned_child(child)
            if marker.exists():
                board.write(SPLIT / 'RECOVERY_REQUIRED.json',
                            dict(boot_id=env['boot_id'], reason='interrupted ga6/ga9 resident PL invocation'))


def main():
    parser = argparse.ArgumentParser(description='VEK280 pure PL g_a.6/g_a.9 resident replay')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('check')
    test = sub.add_parser('run')
    test.add_argument('layer', choices=LAYERS)
    test.add_argument('scope', choices=('smoke', 'full'))
    test.add_argument('profile', choices=('direct', 'merge'), nargs='?', default='direct')
    test.add_argument('--data', type=Path)
    args = parser.parse_args()
    board, package = package_check()
    if args.action == 'check':
        print('PASS_GA_RESIDENT_PACKAGE')
    else:
        run(args, board, package)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'GA_RESIDENT_BOARD_FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
