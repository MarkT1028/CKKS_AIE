#!/usr/bin/env python3
"""Recompute timing and affinity checks; never silently pool a drifting CPU baseline."""
from pathlib import Path, PurePosixPath
import argparse
import csv
import json
import math
import statistics
import sys
import tempfile

import board_experiment as base
from controlled_board import ROOT, plan, write_json
from summarize_results import case_statistics, stats, taiwan_day


def csv_rows(path):
    with Path(path).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def safe_case(directory, relative):
    rel = PurePosixPath(relative)
    base.require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in relative, 'Unsafe case path')
    result = directory.joinpath(*rel.parts).resolve()
    base.require(result.is_relative_to(directory.resolve()), 'Case escapes results directory')
    return result


def inspect(directory):
    directory = Path(directory).resolve()
    m = json.loads((directory/'experiment.json').read_text(encoding='utf-8'))
    base.require(m['schema'] == 'ckks_controlled_board_v2' and m['status'] == 'PASS_ALL_24_CASES', 'Not a completed controlled experiment')
    base.require(m.get('board_run') is True and not m.get('synthetic_fixture_for_tests'), 'Only real board runs can enter research comparison')
    base.require((directory/'STATUS.txt').read_text().strip() == m['status'], 'Status file mismatch')
    variant = m['variant']
    base.require(variant in base.VARIANTS, 'Unknown variant')
    expected_uuid = (ROOT/'variants'/variant/'EXPECTED_BOOT_UUID').read_text().strip()
    boot_id = m['environment_before']['boot_id']
    base.require(bool(boot_id) and m['environment_after']['boot_id'] == boot_id, 'Boot changed')
    base.require(m['environment_before']['boot_uuid'] == m['environment_after']['boot_uuid'] == expected_uuid, 'Boot image mismatch')
    base.require(m['package']['manifest_sha256'] == base.sha(ROOT/'SHA256SUMS_PACKAGE'), 'Package differs from measurement')
    for key in ['cpu_build', 'hardware_host_build']:
        b = m[key]
        base.require(b['architecture'] == 'aarch64' and b['flags'] == base.FLAGS, 'Not ARM build / compiler flags differ')
        base.require(b['package_manifest_sha256'] == m['package']['manifest_sha256'], 'Build package mismatch')
        for relative, digest in b['source_files'].items():
            path = safe_case(ROOT, relative)
            base.require(base.sha(path) == digest, 'Build source mismatch: ' + relative)
    base.require(m['cpu_build']['compiler_version'] == m['hardware_host_build']['compiler_version'], 'Compiler versions differ')
    fixture_names = ['inputs.bin', 'inputs_k16.bin', 'expected_raw.bin', 'expected_k16_raw.bin']
    base.require(set(m['fixture_sha256']) == set(fixture_names), 'Fixture coverage mismatch')
    for name in fixture_names:
        base.require(base.sha(ROOT/'fixtures'/name) == m['fixture_sha256'][name], 'Fixture changed')
    cpus = m['selected_cpus']
    base.require(len(cpus) == 2 and cpus[0] != cpus[1] and all(isinstance(c, int) and c >= 0 for c in cpus), 'Invalid CPU selection')
    expected_plan = plan(m['order'], cpus)
    base.require(m['plan'] == expected_plan and len(m['cases']) == len(expected_plan) == 24, 'Incorrect case/order coverage')
    repetitions, warmups = int(m['repetitions']), int(m['warmups'])
    base.require(1 <= repetitions <= 1000 and warmups == 3, 'Invalid count')
    details = []
    all_environment = [m['environment_before'], m['environment_after']]
    lookup = {}
    telemetry_signatures = set()
    for index, (request, item) in enumerate(zip(expected_plan, m['cases'])):
        base.require(all(item.get(k) == v for k, v in request.items()) and item['index'] == index, 'Case/request mismatch')
        case = safe_case(directory, request['path'])
        base.require(json.loads((case/'case.json').read_text()) == item and item['status'] == 'PASS', 'Case record mismatch')
        k, threads = request['K'], request['threads']
        cpu = threads is not None
        golden = ROOT/'fixtures'/('expected_raw.bin' if k == 1 else 'expected_k16_raw.bin')
        output = case/'host/output_last.bin'
        base.require(output.read_bytes() == golden.read_bytes() and base.sha(output) == item['output_sha256'], 'Full output mismatch')
        log = (case/'host.log').read_text()
        base.require(('PASS CPU_FULL_MAC' if cpu else 'PASS FULL_MAC') in log, 'Missing correctness marker')
        ini = (case/'xrt.ini').read_text().replace(' ', '')
        base.require('aie_profile=false' in ini and 'aie_trace=false' in ini and 'native_xrt_trace=false' in ini, 'Formal profiling not disabled')
        st, measured = case_statistics(case, cpu, repetitions, warmups, k, threads, request['mode'], variant)
        rows = csv_rows(case/'host/iterations.csv')
        if cpu:
            affinity = json.loads((case/'host/affinity.json').read_text())
            base.require(affinity['mode'] == request['affinity_mode'] and affinity['compute_threads'] == threads and len(affinity['workers']) == threads, 'Affinity configuration mismatch')
            base.require(len({worker['tid'] for worker in affinity['workers']}) == threads, 'Worker TIDs are not distinct')
            for lane, worker in enumerate(affinity['workers']):
                base.require(worker['lane'] == lane and worker['tid'] > 0, 'Worker identity invalid')
                allowed = worker['allowed_cpus']
                if request['affinity_mode'] == 'pinned':
                    target = request['target_cpus'][lane]
                    base.require(worker['target_cpu'] == target and allowed == [target], 'Worker not individually pinned')
                else:
                    base.require(worker['target_cpu'] == -1 and set(cpus).issubset(allowed), 'Unbound worker unexpectedly restricted')
                for row in rows:
                    base.require(row['affinity_mode'] == request['affinity_mode'], 'Per-row affinity mode mismatch')
                    endpoints = [int(row[f'cpu{lane}_start']), int(row[f'cpu{lane}_end'])]
                    base.require(all(c in allowed for c in endpoints), 'CPU endpoint outside actual worker affinity')
                    if request['affinity_mode'] == 'pinned':
                        base.require(endpoints == [target, target], 'Pinned worker migrated')
            lookup[(request['kind'], k, request['config'])] = (st, measured)
        else:
            lookup[('hardware', k, request['mode'])] = (st, measured)
        telemetry = [json.loads(line) for line in (case/'telemetry.jsonl').read_text().splitlines()]
        base.require(len(telemetry) >= 2 and all(telemetry[i]['monotonic_ns'] <= telemetry[i+1]['monotonic_ns'] for i in range(len(telemetry)-1)), 'Missing/unordered telemetry')
        for sample in telemetry:
            telemetry_signatures.add(json.dumps(sample['cpu_policies'], sort_keys=True))
        for env in [item['environment_before'], item['environment_after']]:
            base.require(env['boot_id'] == boot_id and env['boot_uuid'] == expected_uuid, 'Case boot mismatch')
            base.require(env['kernel']['machine'] == 'aarch64' and 'vek280' in env['model'].lower(), 'Case not VEK280')
            base.require(set(cpus).issubset(env['affinity']), 'Driver lost two-core affinity')
            all_environment.append(env)
        details.append({'path': request['path'], 'statistics': st, 'telemetry_samples': len(telemetry)})
    comparisons = []
    drift_rows = []
    for k in [1, 16]:
        for config_name in ['unbound_t1', 'unbound_t2', 'pinned_t1_c0', 'pinned_t1_c1', 'pinned_t2_c01']:
            before, before_samples = lookup[('cpu_before', k, config_name)]
            after, after_samples = lookup[('cpu_after', k, config_name)]
            change = 100*(after['compute_ms']['median']/before['compute_ms']['median']-1)
            # This is an explicit reporting flag, not a significance test or sample rejection rule.
            qualified = abs(change) > 5
            drift_rows.append({'variant': variant, 'session': m['session_label'], 'boot_id': boot_id, 'K': k,
                               'config': config_name, 'before_compute_ms': before['compute_ms']['median'],
                               'after_compute_ms': after['compute_ms']['median'], 'change_percent': change,
                               'before_call_ms': before['verified_call_ms']['median'],
                               'after_call_ms': after['verified_call_ms']['median'], 'drift_over_5_percent': qualified})
            pooled_call = stats([float(r['verified_call_ms']) for r in before_samples+after_samples])
            for mode in ['resident', 'transfer']:
                hw = lookup[('hardware', k, mode)][0]
                # Primary values keep before/after separate; pooled is explicitly descriptive.
                comparisons.append({**drift_rows[-1], 'mode': mode,
                    'hardware_execution_ms': hw['execution_ms']['median'],
                    'hardware_execution_p95_ms': hw['execution_ms']['p95'],
                    'hardware_transaction_ms': hw['transaction_ms']['median'],
                    'before_mainflow_speedup_cpu_over_hardware': before['compute_ms']['median']/hw['execution_ms']['median'],
                    'after_mainflow_speedup_cpu_over_hardware': after['compute_ms']['median']/hw['execution_ms']['median'],
                    'before_call_speedup_cpu_over_hardware': before['verified_call_ms']['median']/hw['transaction_ms']['median'],
                    'after_call_speedup_cpu_over_hardware': after['verified_call_ms']['median']/hw['transaction_ms']['median'],
                    'pooled_call_ms_descriptive_only': pooled_call['median']})
    return {'directory': str(directory), 'variant': variant, 'boot_id': boot_id, 'order': m['order'],
            'repetitions': repetitions, 'Taiwan_day': taiwan_day(m['started_at_utc']), 'case_count': 24,
            'package_sha256': m['package']['manifest_sha256'], 'drift': drift_rows, 'comparisons': comparisons,
            'details': details, 'telemetry_frequency_governor_signatures': len(telemetry_signatures),
            'environment_snapshots': len(all_environment)}


def summarize(paths, out=None):
    base.check_package()
    directories = [Path(p).resolve() for p in paths]
    base.require(len(set(directories)) == len(directories), 'Duplicate result directory')
    results = [inspect(p) for p in directories]
    formal = [r for r in results if r['repetitions'] >= 30]
    coverage = {}
    for v in base.VARIANTS:
        matched = [r for r in formal if r['variant'] == v]
        boots = sorted({r['boot_id'] for r in matched})
        forward = {r['boot_id'] for r in matched if r['order'] == 'forward'}
        reverse = {r['boot_id'] for r in matched if r['order'] == 'reverse'}
        independent_orders = any(a != b for a in forward for b in reverse)
        coverage[v] = {'formal_runs': len(matched), 'distinct_boot_ids': boots,
                       'forward_and_reverse_on_distinct_boots': independent_orders,
                       'complete': len(boots) >= 2 and independent_orders}
    complete = all(c['complete'] for c in coverage.values())
    drift = any(row['drift_over_5_percent'] for run in formal for row in run['drift'])
    result = {'schema': 'ckks_controlled_summary_v2',
              'status': 'VALIDATED_COMPLETE_COVERAGE' if complete and not drift else 'VALIDATED_PARTIAL_OR_DRIFT_QUALIFIED',
              'four_architectures_two_boots_both_orders_complete': complete,
              'formal_CPU_drift_over_5_percent': drift, 'coverage': coverage,
              'formal_Taiwan_days': sorted({r['Taiwan_day'] for r in formal}),
              'runs': results,
              'notes': ['5% is a predeclared reporting flag, not a statistical significance cutoff.',
                        'A single boot with multiple session labels does not satisfy cross-boot coverage.',
                        'Compare matching arithmetic and timing boundaries. No OpenFHE/application timings.',
                        '100 ms frequency samples and CPU start/end samples do not observe every instant.']}
    if out is None:
        out = Path(tempfile.mkdtemp(prefix='comparison_controlled_', dir=ROOT))
    else:
        out = Path(out)
        base.require(not out.exists(), 'Summary output directory already exists')
        out.mkdir(parents=True)
    write_json(out/'comparison.json', result)
    for name, key in [('CPU_DRIFT.csv', 'drift'), ('CPU_HW_COMPARISON.csv', 'comparisons')]:
        records = [row for r in results for row in r[key]]
        with (out/name).open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    (out/'README.txt').write_text('Results are independently recomputed; all samples retained.\nRead CPU_DRIFT.csv before any pooled CPU values.\n'+result['status']+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'summary': str(out), 'coverage': coverage}, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('results', nargs='+')
    p.add_argument('--out')
    args = p.parse_args()
    try:
        summarize(args.results, args.out)
    except Exception as error:
        print('FAIL: '+str(error), file=sys.stderr)
        sys.exit(1)
