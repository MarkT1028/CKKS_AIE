"""Run matched baseline/fast GA profiles on the installed Split BO image."""
import argparse
from pathlib import Path
import json
import os
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
RESULT_DIRS = {'ga0': 'ga0', 'ga3': 'ga3', 'ga6': 'resident', 'ga9': 'resident'}
FILES = ('summary.json', 'native.json', 'tiles.csv', 'windows.csv', 'environment_before.json',
         'environment_after.json', 'identity.json', 'runner_timing.json',
         'independently_recomputed_summary.json', 'status.json', 'execution.log')


def collect(folders):
    for candidate in folders:
        folder = candidate.resolve(strict=True)
        if folder.parent not in {ROOT / name for name in RESULT_DIRS.values()} or not folder.name.startswith('results_'):
            raise ValueError('expected a result folder from this package')
        receipt = folder / 'summary.json'
        if not receipt.is_file():
            receipt = folder / 'status.json'
        status = json.loads(receipt.read_bytes())['status']
        if not status.startswith(('PASS_GA0_CTPT_', 'PASS_GA_RESIDENT_', 'PASS_FINISH_BOARD_REPLAY')):
            raise ValueError('result did not complete: ' + status)
        archive = folder.with_suffix('.tar.gz')
        files = [folder / name for name in FILES if (folder / name).is_file()]
        for directory in ('data_evidence', 'cache_evidence', 'replay'):
            if (folder / directory).is_dir():
                files.extend(p for p in (folder / directory).iterdir()
                             if p.is_file() and not p.name.startswith('HARDWARE_ENTERED'))
        with tarfile.open(archive, 'x:gz', compresslevel=1) as stream:
            for path in files:
                path.resolve(strict=True).relative_to(folder)
                if path.is_symlink():
                    raise ValueError(f'symlink in result: {path}')
                stream.add(path, arcname=path.relative_to(folder.parent), recursive=False)
        print(f'DOWNLOAD={archive}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('check')
    run = actions.add_parser('run')
    run.add_argument('layer', choices=RESULT_DIRS)
    run.add_argument('scope', choices=('smoke', 'pilot', 'full'))
    run.add_argument('profile', choices=('baseline', 'fast'))
    run.add_argument('--data', type=Path, help='alternate path to the same sealed fixture')
    archive = actions.add_parser('collect')
    archive.add_argument('--result', type=Path, nargs='+', required=True)
    args = parser.parse_args()
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS_PACKAGE'], cwd=ROOT, check=True)
    if args.action == 'check':
        subprocess.run(['sha256sum', '-c', 'DEPENDENCY_MANIFESTS'], cwd=ROOT, check=True)
        print('PASS_GA_OPT_PACKAGE')
        return
    if args.action == 'collect':
        collect(args.result)
        return
    if args.scope == 'pilot' and args.layer != 'ga3':
        parser.error('pilot is available for ga3')
    if args.layer == 'ga0':
        command = ['ga0/run_board.py', args.scope]
    elif args.layer == 'ga3':
        command = ['ga3/finish_board.py', 'run', 'direct1', args.scope, 'descending']
    else:
        command = ['resident/run_board.py', 'run', args.layer, args.scope, 'direct']
    environment = dict(os.environ, V32_GA_OPT_PROFILE=args.profile)
    if args.data:
        data = str(args.data.resolve(strict=True))
        if args.layer == 'ga3':
            environment['V32_GA3_DATA'] = data
        else:
            command += ['--data', data]
    subprocess.run([sys.executable, '-B', *command], cwd=ROOT, env=environment, check=True)


if __name__ == '__main__':
    main()
