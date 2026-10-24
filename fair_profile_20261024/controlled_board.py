#!/usr/bin/env python3
"""Controlled VEK280 comparison. Never changes boot images, clocks or governors."""
from pathlib import Path
import argparse
import csv
import datetime as dt
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

import board_experiment as base

ROOT = base.ROOT
VARIANTS = base.VARIANTS
WARMUPS = 3


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class BoardLock:
    def __enter__(self):
        self.file = open('/run/lock/ckks-board-experiment.lock', 'a+')
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise RuntimeError('Another controlled/profile experiment is running; no test started')
        return self

    def __exit__(self, *unused):
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


class Telemetry:
    """100 ms snapshots; not a guarantee about frequency between samples."""
    def __init__(self, path):
        self.path = Path(path)
        self.stop = threading.Event()
        self.thread = None
        self.error = None

    def sample(self):
        data = {'utc': base.stamp(), 'monotonic_ns': time.monotonic_ns(), 'cpu_policies': {}, 'thermal': {}}
        for p in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')):
            data['cpu_policies'][p.name] = {n: base.read(p/n) for n in ['scaling_cur_freq', 'scaling_governor']}
        for p in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
            data['thermal'][p.name] = base.read(p/'temp')
        data['proc_stat'] = (base.read('/proc/stat') or '').splitlines()[:3]
        return data

    def collect(self):
        try:
            with self.path.open('w', encoding='utf-8') as f:
                while True:
                    f.write(json.dumps(self.sample()) + '\n')
                    f.flush()
                    if self.stop.wait(.1):
                        break
                f.write(json.dumps(self.sample()) + '\n')
        except Exception as error:
            self.error = str(error)

    def __enter__(self):
        self.thread = threading.Thread(target=self.collect, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *unused):
        self.stop.set()
        self.thread.join()
        if self.error and unused[0] is None:
            raise RuntimeError('Telemetry capture failed: ' + self.error)


def logged(command, case, env, timeout):
    """Save partial output even on failure, timeout or interruption."""
    case = Path(case)
    write_json(case/'command.json', {'argv': [str(x) for x in command], 'cwd': str(case),
                                    'XRT_INI_PATH': env.get('XRT_INI_PATH'), 'timeout_seconds': timeout})
    with (case/'host.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([str(x) for x in command], cwd=case, env=env,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout)
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            raise
    output = (case/'host.log').read_text(encoding='utf-8', errors='replace')
    print(output, end='', flush=True)
    base.require(rc == 0, f'{case.name}: host exit {rc}; partial log retained; no automatic retry/reset')
    return output


def environment():
    env = os.environ.copy()
    for name in ['XCL_EMULATION_MODE', 'XRT_INI_PATH']:
        env.pop(name, None)
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', PERF_PROFILE='none')
    return env


def fixtures(k):
    return (ROOT/'fixtures'/('inputs.bin' if k == 1 else 'inputs_k16.bin'),
            ROOT/'fixtures'/('expected_raw.bin' if k == 1 else 'expected_k16_raw.bin'))


def plan(order, cpus):
    configs = [('unbound_t1', 1, 'unbound', []), ('unbound_t2', 2, 'unbound', []),
               ('pinned_t1_c0', 1, 'pinned', [cpus[0]]), ('pinned_t1_c1', 1, 'pinned', [cpus[1]]),
               ('pinned_t2_c01', 2, 'pinned', cpus)]
    cases = []
    for phase in ['cpu_before', 'hardware', 'cpu_after']:
        entries = ([{'kind': phase, 'K': k, 'mode': mode, 'threads': None,
                     'path': f'hardware/k{k}_{mode}'} for k in [1, 16] for mode in ['resident', 'transfer']]
                   if phase == 'hardware' else
                   [{'kind': phase, 'K': k, 'mode': None, 'threads': threads, 'affinity_mode': affinity,
                     'target_cpus': targets, 'config': name, 'path': f'{phase}/k{k}_{name}'}
                    for k in [1, 16] for name, threads, affinity, targets in configs])
        # Reverse after-block as well as round2, to expose order effects.
        reverse = (order == 'reverse') != (phase == 'cpu_after')
        if reverse:
            entries.reverse()
        cases.extend(entries)
    return cases


def build(choice):
    base.build(choice)
    if choice not in ['all', 'raw_2_pipe']:
        return
    src = ROOT/'profile_host/perf_host.cpp'
    name = 'profile_host_raw_2_pipe'
    destination = ROOT/'bin'/name
    with tempfile.TemporaryDirectory(prefix='build_profile_', dir=ROOT/'bin') as td:
        tmp = Path(td)/name
        command = ['g++', *base.FLAGS, str(src), '-lxrt_coreutil', '-o', str(tmp)]
        base.logged(command, ROOT/'bin'/(name+'.compile.log'))
        linked = base.logged(['ldd', tmp], ROOT/'bin'/(name+'.ldd.log'))
        os.replace(tmp, destination)
    sources = [src, *sorted(src.parent.glob('*.hpp'))]
    write_json(ROOT/'bin'/(name+'.build.json'), {
        'target': 'profile_raw_2_pipe', 'built_at_utc': base.stamp(), 'architecture': base.platform.machine(),
        'compiler_version': subprocess.check_output(['g++', '--version'], text=True),
        'flags': base.FLAGS, 'libraries': ['-lxrt_coreutil'], 'binary_sha256': base.sha(destination),
        'package_manifest_sha256': base.sha(ROOT/'SHA256SUMS_PACKAGE'),
        'source_files': {p.relative_to(ROOT).as_posix(): base.sha(p) for p in sources},
        'linked_libraries': linked,
        'instrumentation': 'Host wait-return observation timestamps; not PL hardware cycle counters',
    })
    print('BUILD_READY=' + str(destination), flush=True)


def run(variant, reps, label, order):
    check = base.check_package()
    base.board_check()
    base.require(1 <= reps <= 1000, 'repetitions must be 1..1000')
    base.require(base.re.fullmatch(r'[A-Za-z0-9_-]{1,32}', label), 'Use a short ASCII session label')
    expected = (ROOT/'variants'/variant/'EXPECTED_BOOT_UUID').read_text().strip()
    base.require(base.boot_uuid() == expected, 'BOOT_MISMATCH; no experiment started')
    base.require(os.environ.get('PERF_PROFILE', 'none') == 'none', 'Unset PERF_PROFILE for formal tests')
    cpu_build = base.binary_record('cpu_bench')
    hw_build = base.binary_record('perf_host_'+variant)
    base.require(cpu_build['compiler_version'] == hw_build['compiler_version'], 'Compiler versions differ')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    cases = plan(order, cpus)
    result = Path(tempfile.mkdtemp(prefix=f'results_controlled_{variant}_{label}_', dir=ROOT))
    print('CONTROLLED_RESULTS=' + str(result), flush=True)
    metadata = {
        'schema': 'ckks_controlled_board_v2', 'status': 'RUNNING', 'variant': variant,
        'session_label': label, 'order': order, 'repetitions': reps, 'warmups': WARMUPS,
        'board_run': True, 'new_firmware': False, 'started_at_utc': base.stamp(),
        'package': check, 'cpu_build': cpu_build, 'hardware_host_build': hw_build,
        'fixture_sha256': {p.name: base.sha(p) for p in sorted((ROOT/'fixtures').glob('*.bin'))},
        'selected_cpus': cpus, 'environment_before': base.snapshot(), 'plan': cases, 'cases': [],
        'telemetry_interval_seconds': .1,
        'timing_notes': 'Historical U128 algorithm retained. CPU endpoint sampling included in compute; setup/pinning excluded. Formal HW host unchanged. Telemetry parent active for all cases. No file I/O, OpenFHE or full application timing.',
    }
    def save():
        write_json(result/'experiment.json', metadata)
    save()
    try:
        for index, request in enumerate(cases):
            base.require(base.boot_uuid() == expected, 'Boot UUID changed')
            case = result/request['path']
            case.mkdir(parents=True)
            input_path, golden = fixtures(request['K'])
            ini = case/'xrt.ini'
            ini.write_text('[Debug]\naie_profile=false\naie_trace=false\nprofile=false\nnative_xrt_trace=false\n', encoding='ascii')
            env = environment()
            env['XRT_INI_PATH'] = str(ini)
            before = base.snapshot()
            if request['threads']:
                cpu_list = ','.join(map(str, request['target_cpus'] or cpus))
                command = [ROOT/'bin/cpu_bench', input_path, golden, case/'host', reps, WARMUPS,
                           request['threads'], request['affinity_mode'], cpu_list]
            else:
                command = [ROOT/'bin'/('perf_host_'+variant), ROOT/'variants'/variant/'ckks_hw_boot.xclbin',
                           input_path, golden, case/'host', reps, WARMUPS, request['mode'], 'run']
            print(f'CASE {index+1}/24 {request["path"]}', flush=True)
            with Telemetry(case/'telemetry.jsonl'):
                log = logged(command, case, env, 300 + 120*(reps+WARMUPS))
            base.require(('PASS CPU_FULL_MAC' if request['threads'] else 'PASS FULL_MAC') in log, 'Missing correctness marker')
            output = case/'host/output_last.bin'
            base.require(output.read_bytes() == golden.read_bytes(), 'Saved output differs from complete golden')
            item = {**request, 'index': index, 'status': 'PASS', 'output_sha256': base.sha(output),
                    'environment_before': before, 'environment_after': base.snapshot()}
            write_json(case/'case.json', item)
            metadata['cases'].append(item)
            save()
        metadata.update(status='PASS_ALL_24_CASES', completed_at_utc=base.stamp(), environment_after=base.snapshot())
        save()
        (result/'STATUS.txt').write_text('PASS_ALL_24_CASES\n', encoding='ascii')
        print('DOWNLOAD_ENTIRE_RESULTS=' + str(result), flush=True)
    except BaseException as error:
        metadata.update(status='FAIL_STOPPED', error=str(error), environment_after=base.snapshot())
        save()
        (result/'STATUS.txt').write_text('FAIL_STOPPED\n', encoding='ascii')
        print('PRESERVE_PARTIAL_RESULTS=' + str(result), flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('detect')
    p = sub.add_parser('build')
    p.add_argument('variant', nargs='?', default='all', choices=['all', *VARIANTS])
    p = sub.add_parser('run')
    p.add_argument('variant', choices=VARIANTS)
    p.add_argument('reps', type=int, nargs='?', default=30)
    p.add_argument('label', nargs='?', default='round1')
    p.add_argument('order', choices=['forward', 'reverse'], nargs='?', default='forward')
    args = parser.parse_args()
    if args.command == 'check':
        print(json.dumps(base.check_package(), indent=2))
    elif args.command == 'detect':
        base.check_package()
        base.board_check()
        actual = base.boot_uuid()
        matching = [v for v in VARIANTS if (ROOT/'variants'/v/'EXPECTED_BOOT_UUID').read_text().strip() == actual]
        print(json.dumps({'boot_uuid': actual, 'matching_variants': matching, 'environment': base.snapshot()}, indent=2))
    else:
        base.board_check()
        with BoardLock():
            if args.command == 'build':
                build(args.variant)
            else:
                run(args.variant, args.reps, args.label, args.order)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        sys.exit(1)
