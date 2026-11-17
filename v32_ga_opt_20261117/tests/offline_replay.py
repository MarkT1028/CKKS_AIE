"""Exercise the same runners with the local XRT contract model and sealed fixtures."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_model(args, directory, binary, arguments, profile):
    env = dict(os.environ, V32_GA_OPT_PROFILE=profile)
    with (directory.parent / (directory.name + '.log')).open('x') as log:
        result = subprocess.run([args.output / binary, *arguments], env=env, stdout=log,
                                stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{binary} failed, see {log.name}')


def replay_ga0(args, directory, profile):
    controller = load_module('ga0', ROOT / 'ga0/run_board.py')
    legacy = load_module('resident_dependencies', PARENT / 'v32_ga_resident_20261114/run_board.py')
    fixture = PARENT / 'v32_ga0_full_20261114/fixture'
    meta, _ = controller.fixture_check(fixture, legacy)
    marker = directory.parent / (directory.name + '.active')
    directory.mkdir()
    run_model(args, directory, 'ga0_model',
              ['unused', marker, fixture, directory, args.scope], profile)
    native, stages = controller.audit(directory, meta, args.scope, fixture)
    assert native['backend'] == 'xrt_contract_model' and native['host_profile'] == profile
    assert native['packing_in_resident'] == (profile == 'fast')
    assert not marker.exists()
    return dict(tiles=native['tiles'], ntt_ms=native['ntt_ms'], request_ms=native['request_ms'],
                baby_pack_ms=stages['baby_pack_ms'])


def replay_resident(args, directory, profile):
    controller = load_module('resident', ROOT / 'resident/run_board.py')
    fixture = PARENT.parent / f'integration/v32_ga_live_20261111/build/v32_{args.layer}_offline_full_20261112'
    meta = controller.fixture(fixture, args.layer)
    marker = directory.parent / (directory.name + '.active')
    directory.mkdir()
    index = directory / 'sealed_index.txt'
    lines = [str(meta['request_bytes']), *(part['sha256'] for part in meta['parts']), *meta['output_sha256']]
    index.write_text('\n'.join(lines) + '\n', encoding='ascii')
    run_model(args, directory, 'resident_model',
              ['unused', marker, fixture, index, directory, args.layer, args.scope, 'direct'], profile)
    native, _ = controller.check_result(directory, meta, args.layer, args.scope)
    assert native['backend'] == 'xrt_contract_model' and native['host_profile'] == profile
    expected = len(meta['parts']) - 1 if profile == 'fast' and args.scope == 'full' else 0
    assert native['prefetched_parts'] == expected and not marker.exists()
    return dict(tiles=native['tiles'], prefetched_parts=expected, request_ms=native['request_ms'])


def reject_prefetch_corruption(args, directory):
    controller = load_module('resident', ROOT / 'resident/run_board.py')
    fixture = PARENT.parent / f'integration/v32_ga_live_20261111/build/v32_{args.layer}_offline_full_20261112'
    meta = controller.fixture(fixture, args.layer)
    directory.mkdir()
    index = directory / 'sealed_index.txt'
    hashes = [part['sha256'] for part in meta['parts']]
    hashes[1] = '0' * 64
    index.write_text('\n'.join([str(meta['request_bytes']), *hashes, *meta['output_sha256']]) + '\n',
                     encoding='ascii')
    marker = directory / 'active'
    process = subprocess.run(
        [args.output / 'resident_model', 'unused', marker, fixture, index, directory, args.layer, 'full', 'direct'],
        env=dict(os.environ, V32_GA_OPT_PROFILE='fast'), capture_output=True, text=True)
    if process.returncode == 0 or 'input part SHA256 mismatch' not in process.stderr:
        raise RuntimeError(f'prefetch failed to reject a corrupt digest: {process.stderr}')
    if (directory / 'native.json').exists():
        raise RuntimeError('invalid input produced a successful receipt')
    print('PASS_GA_PREFETCH_REJECTS_CORRUPTION', args.layer, flush=True)


def replay_ga3(args, directory, profile):
    controller = load_module('ga3', ROOT / 'ga3/finish_board.py')
    run_model(args, directory, 'finish_model',
              ['unused', args.ga3_data, directory, 'direct1', args.scope, 'descending'], profile)
    summary = json.loads((directory / 'summary.json').read_bytes())
    coords = controller.expected_coordinates(args.scope)
    expected = controller.expected_digests(args.ga3_data)
    with (directory / 'windows.csv').open(newline='') as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(coords) == summary['windows']
    assert summary['hashed_outputs'] == len(coords) * 4
    assert summary['host_profile'] == profile
    assert summary['prefetched_windows'] == (len(coords) - 1 if profile == 'fast' else 0)
    for row, (tower, coefficient, output, towers) in zip(rows, coords):
        keys = ('tower_start', 'coefficient_start', 'output_ct', 'L')
        assert tuple(int(row[key]) for key in keys) == (tower, coefficient, output, towers)
        assert all(row[f'digest{group}'] == expected[(tower, coefficient, output, group)]
                   for group in range(4))
    assert summary['request_wall_ms'] + .1 >= summary['resident_batch_wall_sum_ms'] + summary['admission_wait_ms']
    return dict(windows=summary['windows'], prefetched_windows=summary['prefetched_windows'],
                request_ms=summary['request_wall_ms'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('layer', choices=('ga0', 'ga3', 'ga6', 'ga9'))
    parser.add_argument('scope', choices=('smoke', 'pilot', 'full'))
    parser.add_argument('profile', choices=('baseline', 'fast'))
    parser.add_argument('--ga3-data', type=Path)
    parser.add_argument('--reject-prefetch-corruption', action='store_true')
    args = parser.parse_args()
    if args.layer == 'ga3' and args.ga3_data is None:
        parser.error('--ga3-data required for ga3')
    if args.layer != 'ga3' and args.scope == 'pilot':
        parser.error('pilot is only available for ga3')
    if args.reject_prefetch_corruption:
        if args.layer not in ('ga6', 'ga9') or (args.scope, args.profile) != ('full', 'fast'):
            parser.error('the corruption test requires ga6 or ga9 full fast')
        reject_prefetch_corruption(args, args.output / f'{args.layer}_prefetch_corruption')
        raise SystemExit(0)
    result = args.output / f'{args.layer}_{args.scope}_{args.profile}'
    runner = {'ga0': replay_ga0, 'ga3': replay_ga3, 'ga6': replay_resident, 'ga9': replay_resident}[args.layer]
    print('PASS_GA_OFFLINE_MODEL_NOT_BOARD', args.layer, args.scope, args.profile,
          runner(args, result, args.profile), flush=True)
