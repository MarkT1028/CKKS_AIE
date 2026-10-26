#!/usr/bin/env python3
"""Runtime profiling of the boot-programmed diag_2_pipe image; no native PLIO API."""
from pathlib import Path
import argparse
import csv
import json
import math
import shutil
import sys
import tempfile

import validation_common as base
from validation_common import ROOT, BoardLock, Telemetry, environment, fixtures, logged, write_json
from summarize_results import case_statistics

CORE_TILES = [(17, 0), (18, 0)]
MEMORY_TILES = [(16, 0), (17, 1), (18, 0), (18, 1)]
SETS = {
    'baseline': {'metric': None},
    'heat_map': {'metric': 'heat_map', 'core_events': [22, 28, 37], 'core_tiles': CORE_TILES},
    'stalls': {'metric': 'stalls', 'core_events': [23, 24, 26], 'core_tiles': CORE_TILES},
    'execution': {'metric': 'execution', 'core_events': [37], 'core_min_events': 3, 'core_tiles': CORE_TILES},
    'dma_in0': {'metric': 's2mm_throughputs', 'channel': 0, 'memory_events': [1031, 1039],
                'memory_tiles': [(16, 0), (18, 0), (18, 1)]},
    'dma_in1': {'metric': 's2mm_throughputs', 'channel': 1, 'memory_events': [1032, 1040],
                'memory_tiles': [(16, 0)]},
    'dma_out0': {'metric': 'mm2s_throughputs', 'channel': 0, 'memory_events': [1037, 1041],
                 'memory_tiles': [(17, 1), (18, 0)]},
    'dma_out1': {'metric': 'mm2s_throughputs', 'channel': 1, 'memory_events': [1038, 1042],
                 'memory_tiles': MEMORY_TILES, 'unused_channel_control': True},
}
ALL_SETS = ['baseline', 'heat_map', 'stalls', 'execution', 'dma_in0', 'dma_in1', 'dma_out0', 'baseline_after']


def config(name):
    spec = SETS['baseline' if name == 'baseline_after' else name]
    enabled = spec['metric'] is not None
    # Native XRT API trace is diagnostic only; no device trace or shim counters.
    lines = ['[Debug]', f'aie_profile={str(enabled).lower()}', 'aie_trace=false',
             'profile=false', 'native_xrt_trace=true', 'device_trace=off',
             '[AIE_profile_settings]', 'interval_us=1000']
    if enabled:
        metric = spec['metric']
        suffix = f':{spec["channel"]}' if 'channel' in spec else ''
        lines += [f'graph_based_aie_metrics=ckks_graph:all:{metric}{suffix}']
        memory_metric = metric if 'channel' in spec else ('conflicts' if name == 'heat_map' else 'off')
        lines += [f'graph_based_aie_memory_metrics=ckks_graph:all:{memory_metric}{suffix}']
    lines += ['graph_based_interface_tile_metrics=all:all:off',
              'tile_based_interface_tile_metrics=all:off']
    return '\n'.join(lines) + '\n'


def parse_profile(path):
    """Keep module/metric declarations and actual data separate."""
    declarations = {}
    groups = {}
    active_module = None
    in_data = False
    generation = None
    clock = None
    rows = 0
    for raw in Path(path).read_text(encoding='utf-8', errors='strict').splitlines():
        if raw.startswith('Hardware generation:'):
            generation = int(raw.split(':', 1)[1].strip())
        if raw.startswith('Clock frequency (MHz):'):
            clock = float(raw.split(':', 1)[1].strip())
        if raw.startswith('# AIE tile core module'):
            active_module = 'core'
        elif raw.startswith('# AIE tile memory module'):
            active_module = 'memory'
        elif raw.startswith('# Memory tile'):
            active_module = 'memory_tile'
        elif raw.startswith('# Interface tile'):
            active_module = 'shim'
        elif raw.startswith('# Microcontroller'):
            active_module = 'microcontroller'
        if raw.strip() == 'METRIC_DATA':
            in_data = True
            continue
        fields = next(csv.reader([raw]))
        if not fields or not fields[0] or fields[0].startswith('#'):
            continue
        if not in_data:
            if active_module and len(fields) == 3:
                declarations[(active_module, int(fields[0]), int(fields[1]))] = fields[2]
            continue
        if fields[0] == 'timestamp':
            continue
        base.require(len(fields) >= 9, f'Malformed profile data row: {path}')
        timestamp = float(fields[0])
        col, row, start, end, reset, value, timer, payload = map(int, fields[1:9])
        base.require(math.isfinite(timestamp) and timestamp >= 0 and min(col, row, start, end, value, timer) >= 0,
                     'Invalid profile row')
        module = 'shim' if start >= 2000 else 'memory' if start >= 1000 else 'core'
        key = (module, col, row, start, end, reset, payload)
        if key not in groups:
            groups[key] = {'samples': 0, 'nonzero_samples': 0, 'first_value': value, 'last_value': value,
                           'first_timestamp_ms': timestamp, 'last_timestamp_ms': timestamp, 'max_value': value}
        group = groups[key]
        group['samples'] += 1
        group['nonzero_samples'] += int(value != 0)
        group['last_value'] = value
        group['last_timestamp_ms'] = timestamp
        group['max_value'] = max(value, group['max_value'])
        rows += 1
    return declarations, groups, {'path': str(path), 'hardware_generation': generation,
                                  'clock_MHz': clock, 'metric_data_rows': rows}


def inspect_coverage(directory, name):
    spec = SETS['baseline' if name == 'baseline_after' else name]
    if spec['metric'] is None:
        return {'status': 'NO_AIE_COUNTERS_REQUESTED', 'missing': [], 'counter_groups': []}
    paths = sorted(p for p in Path(directory).rglob('*.csv') if 'aie' in p.name.lower() and 'profile' in p.name.lower())
    declarations = {}
    groups = {}
    files = []
    for p in paths:
        declared, counters, header = parse_profile(p)
        base.require(header['hardware_generation'] == 2, 'Event IDs require hardware generation 2; no automatic interpretation')
        declarations.update(declared)
        files.append(header)
        # Different files are retained as distinct series; never sum duplicate counters blindly.
        for key, values in counters.items():
            groups[(p.relative_to(directory).as_posix(), *key)] = values
    missing = []
    if not paths:
        missing.append('No AIE profile CSV generated')
    def seen(module, tile):
        return {key[4] for key in groups if key[1] == module and key[2:4] == tuple(tile)}
    def nonzero(module, tile, events):
        return any(values['nonzero_samples'] > 0 for key, values in groups.items()
                   if key[1] == module and key[2:4] == tuple(tile) and key[4] in events)
    if 'core_events' in spec:
        for tile in spec['core_tiles']:
            if declarations.get(('core', *tile)) != spec['metric']:
                missing.append(f'Core metric declaration missing/wrong at {tile}')
            events = seen('core', tile)
            for event in spec['core_events']:
                if event not in events:
                    missing.append(f'Core {tile} missing actual event {event}')
            if len(events) < spec.get('core_min_events', len(spec['core_events'])):
                missing.append(f'Core {tile} has too few actual event types')
            activity = [28] if name == 'heat_map' else [37] if name == 'execution' else []
            if activity and not nonzero('core', tile, activity):
                missing.append(f'Core {tile} activity not confirmed during captured samples')
    if 'memory_events' in spec:
        for tile in spec['memory_tiles']:
            if declarations.get(('memory', *tile)) != spec['metric']:
                missing.append(f'Memory metric declaration missing/wrong at {tile}')
            for event in spec['memory_events']:
                if event not in seen('memory', tile):
                    missing.append(f'Memory {tile} missing actual event {event}')
            # DMA port running/stalled counters live in core module, including a memory-only tile.
            events = seen('core', tile)
            if not any(75 <= e <= 103 and (e-75) % 4 == 0 for e in events):
                missing.append(f'DMA port-running counter absent at {tile}')
            if not any(76 <= e <= 104 and (e-76) % 4 == 0 for e in events):
                missing.append(f'DMA port-stalled counter absent at {tile}')
            if not spec.get('unused_channel_control') and not nonzero('core', tile, range(75, 104, 4)):
                missing.append(f'DMA {tile} channel activity not confirmed during captured samples')
    if any(key[1] == 'shim' for key in groups):
        missing.append('Unexpected shim counters; this package requests none')
    items = [{'file': key[0], 'module': key[1], 'column': key[2], 'row': key[3],
              'start': key[4], 'end': key[5], 'reset': key[6], 'payload': key[7], **values}
             for key, values in sorted(groups.items())]
    return {'status': 'COUNTER_ROWS_PRESENT' if not missing else 'COUNTER_COVERAGE_PARTIAL',
            'metric': spec['metric'], 'channel': spec.get('channel'), 'missing': missing, 'files': files,
            'counter_groups': items, 'unused_channel_control': spec.get('unused_channel_control', False),
            'interpretation': 'Coverage only. Zero stall counts can be valid. No utilization/throughput percentage or reducer-only duration is inferred. Host wait-return observations are completion upper bounds; API/CSV clocks are not assumed aligned.'}


def validate_mapping():
    mapping = json.loads((ROOT/'references/profiling_mapping.json').read_text(encoding='utf-8'))
    m = json.loads((base.COMPARISON/'variants/diag_2_pipe/manifest.json').read_text())
    base.require(mapping['xclbin_sha256'] == m['metadata_sha256'], 'Profile mapping/xclbin mismatch')
    base.require(mapping['core_tiles'] == [list(t) for t in CORE_TILES], 'Core mapping changed')
    base.require(mapping['memory_tiles'] == [list(t) for t in MEMORY_TILES], 'Memory mapping changed')
    base.require(base.sha(ROOT/'references/AIE_METADATA_diag_2_pipe.json') == mapping['AIE_METADATA_sha256'], 'Mapping source changed')
    base.require(base.sha(base.COMPARISON/'variants/diag_2_pipe/DMA_report.txt') == mapping['DMA_report_sha256'], 'DMA report changed')
    actual = json.loads((ROOT/'references/AIE_METADATA_diag_2_pipe.json').read_text())['aie_metadata']
    base.require(actual['driver_config']['hw_gen'] == '2', 'Expected AIE-ML hardware generation 2')
    graph = actual['graphs']['graph0']
    base.require(graph['name'] == 'ckks_graph', 'Graph changed')
    actual_cores = list(zip(map(int, graph['core_columns']), map(int, graph['core_rows'])))
    base.require(actual_cores == CORE_TILES, 'Actual metadata core coordinates differ')
    kernels = actual['TileMapping']['AIEKernelToTileMapping']
    base.require(len(kernels) == 2 and all(k['function'].startswith('limb_diag.') for k in kernels), 'Not the exact diagonal kernel')
    events = actual['EventGraphs']['graph0']
    memory = set(zip(map(int, events['dma_columns']), map(int, events['dma_rows'])))
    base.require(memory == set(MEMORY_TILES), 'Actual metadata DMA coordinates differ')
    # Verify port/channel mapping against the actual diagonal compiler report.
    routes=set();current=None;direction=None
    for line in (base.COMPARISON/'variants/diag_2_pipe/DMA_report.txt').read_text().splitlines():
        if line.startswith('DMA Report:'):direction=line.split(':',1)[1].strip().lower()
        port=base.re.search(r'mul\[(\d+)\]\.(in|out)\[(\d+)\]',line)
        if port:
            current=(int(port[1]),'partials' if port[2]=='out' else ('left' if port[3]=='0' else 'right'))
        dma=base.re.search(r'MG\((\d+),(\d+)\)\s*:\s*channel=(\d+)',line)
        if dma and current:routes.add((*current,direction,int(dma[1]),int(dma[2]),int(dma[3])))
    expected_routes={(r['lane'],r['port'],r['direction'],*r['tile'],r['channel']) for r in mapping['routes']}
    base.require(routes==expected_routes,'Actual diagonal port/channel mapping differs')


def run(selection, reps, label):
    package = base.check_package()
    base.board_check()
    validate_mapping()
    base.require(1 <= reps <= 1000, 'repetitions must be 1..1000')
    base.require(base.re.fullmatch(r'[A-Za-z0-9_-]{1,32}', label), 'Use short ASCII label')
    expected = (base.COMPARISON/'variants/diag_2_pipe/EXPECTED_BOOT_UUID').read_text().strip()
    base.require(base.boot_uuid() == expected, 'BOOT_MISMATCH: profiling requires diag_2_pipe; no test started')
    build = base.binary_record('profile_host_diag_2_pipe')
    result = Path(tempfile.mkdtemp(prefix=f'results_profile_diag_2_pipe_{label}_', dir=ROOT))
    print('PROFILE_RESULTS=' + str(result), flush=True)
    names = ALL_SETS if selection == 'all' else [selection]
    meta = {'schema': 'ckks_profile_board_v2', 'status': 'RUNNING', 'variant': 'diag_2_pipe',
            'package': package, 'build': build, 'board_run': True, 'new_firmware': False,
            'started_at_utc': base.stamp(), 'environment_before': base.snapshot(), 'sets': names,
            'repetitions': reps, 'warmups': 3, 'K': 16, 'mode': 'resident', 'cases': [],
            'timings_are_diagnostic_not_formal_comparison': True,
            'mapping': json.loads((ROOT/'references/profiling_mapping.json').read_text()),
            'scope_limit': 'Runtime core and local DMA counters + host API trace/wait-return observations. Existing image has no new PL AXI stream monitor/cycle counters. Reader-only/reducer-only hardware durations require additional instrumentation if these records do not resolve the bottleneck.'}
    def save():
        write_json(result/'experiment.json', meta)
    save()
    try:
        for name in names:
            base.require(base.boot_uuid() == expected, 'Boot UUID changed')
            case = result/name
            case.mkdir()
            ini = case/'xrt.ini'
            ini.write_text(config(name), encoding='ascii')
            env = environment()
            env['XRT_INI_PATH'] = str(ini)
            input_path, golden = fixtures(16)
            executable = case/'profile_host_diag_2_pipe'
            shutil.copy2(ROOT/'bin/profile_host_diag_2_pipe', executable)
            base.require(base.sha(executable) == build['binary_sha256'], 'Copied profile binary changed')
            command = [executable, base.COMPARISON/'variants/diag_2_pipe/ckks_hw_boot.xclbin',
                       input_path, golden, case/'host', reps, 3, 'resident', 'run']
            print('PROFILE_CASE=' + name, flush=True)
            before = base.snapshot()
            with Telemetry(case/'telemetry.jsonl'):
                log = logged(command, case, env, 300+120*(reps+3))
            base.require('PASS FULL_MAC' in log, 'Missing full hardware correctness marker')
            output = case/'host/output_last.bin'
            base.require(output.read_bytes() == golden.read_bytes(), 'Saved profile output differs from golden')
            case_statistics(case, False, reps, 3, 16, None, 'resident', 'diag_2_pipe')
            observations = list(csv.DictReader((case/'host/wait_observations.csv').read_text().splitlines()))
            base.require(len(observations) == 4*(reps+3), 'Incorrect profile wait-observation count')
            expected_observations = {(r, lane, kind) for r in range(reps+3) for lane in [0, 1] for kind in ['reader', 'reducer']}
            observed_keys = set()
            for observation in observations:
                rep, lane = int(observation['repetition']), int(observation['lane'])
                key = (rep, lane, observation['kind'])
                base.require(key not in observed_keys and key in expected_observations, 'Duplicate/invalid wait observation')
                observed_keys.add(key)
                start = float(observation['start_returned_session_ms'])
                end = float(observation['completion_observed_session_ms'])
                base.require(math.isfinite(start) and math.isfinite(end) and 0 <= start <= end and int(observation['warmup']) == int(rep < 3), 'Invalid wait observation')
            coverage = inspect_coverage(case, name)
            write_json(case/'counter_coverage.json', coverage)
            item = {'name': name, 'path': name, 'answers': 'PASS_FULL_GOLDEN',
                    'output_sha256': base.sha(output), 'coverage_status': coverage['status'],
                    'environment_before': before, 'environment_after': base.snapshot(),
                    'run_summary_files': [p.relative_to(case).as_posix() for p in sorted(case.rglob('*.run_summary'))]}
            write_json(case/'case.json', item)
            meta['cases'].append(item)
            save()
            print(f'PROFILE_COVERAGE {name} {coverage["status"]}', flush=True)
            for warning in coverage['missing']:
                print('COVERAGE_WARNING: ' + warning, flush=True)
            if coverage['status'] == 'COUNTER_COVERAGE_PARTIAL':
                print('STOPPED_PROFILE_AFTER_PARTIAL_COVERAGE: preserve this folder; remaining sets were not run', flush=True)
                break
        partial = any(c['coverage_status'] == 'COUNTER_COVERAGE_PARTIAL' for c in meta['cases'])
        meta.update(status='ANSWERS_PASS_COVERAGE_PARTIAL' if partial else 'ANSWERS_PASS_REQUESTED_COUNTER_ROWS_PRESENT',
                    completed_at_utc=base.stamp(), environment_after=base.snapshot())
        save()
        (result/'STATUS.txt').write_text(meta['status']+'\n', encoding='ascii')
        print('DOWNLOAD_ENTIRE_RESULTS=' + str(result), flush=True)
        return 2 if partial else 0
    except BaseException as error:
        meta.update(status='FAIL_STOPPED', error=str(error), environment_after=base.snapshot())
        save()
        (result/'STATUS.txt').write_text('FAIL_STOPPED\n', encoding='ascii')
        print('PRESERVE_PARTIAL_RESULTS=' + str(result), flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selection', choices=['all', *SETS])
    parser.add_argument('reps', type=int, nargs='?', default=200)
    parser.add_argument('label', nargs='?', default='profile1')
    args = parser.parse_args()
    base.board_check()
    with BoardLock():
        return run(args.selection, args.reps, args.label)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        sys.exit(1)
