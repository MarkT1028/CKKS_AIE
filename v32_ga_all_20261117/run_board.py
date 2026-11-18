"""Run the four sealed VEK280 GA convolution MAC replays on one boot image."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'common'))
from ga_all_board import VARIANT, boot_uuid, input_source

BASE = ROOT.parent / 'v32_ga3_splitbo_20261109'
LAYERS = dict(ga0='ga0', ga3='ga3', ga6='resident', ga9='resident')
RESULT_FILES = ('summary.json', 'native.json', 'tiles.csv', 'windows.csv', 'environment_before.json',
                'environment_after.json', 'identity.json', 'runner_timing.json', 'status.json',
                'independently_recomputed_summary.json', 'execution.log')
RESULT_SUBDIRS = ('data_evidence', 'cache_evidence', 'replay')
RESULT_RECEIPTS = {'ga0': 'summary.json', 'ga3': 'independently_recomputed_summary.json',
                   'ga6': 'summary.json', 'ga9': 'summary.json'}
SENDER_KEYS = ('V32_GA_INPUT_IP', 'V32_GA_INPUT_PORT', 'V32_GA_INPUT_KEY')


def check(verify_dependencies=False):
    for manifest in ('SHA256SUMS_PACKAGE', 'DEPENDENCY_MANIFESTS'):
        subprocess.run(['sha256sum', '-c', '--quiet', manifest], cwd=ROOT, check=True)
    if verify_dependencies:
        for line in (ROOT/'DEPENDENCY_MANIFESTS').read_text(encoding='ascii').splitlines():
            _, name = line.split('  ', 1)
            path = ROOT/name
            subprocess.run(['sha256sum','-c','--quiet',path.name], cwd=path.parent, check=True)
    sys.path.insert(0, str(BASE))
    import ga3_board
    ga3_board.board()
    return ga3_board


def load(path):
    return json.loads(path.read_bytes())


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def run_layer(layer, scope, profile, board_input, data):
    if layer=='ga0':
        command = ['ga0/run_board.py', scope]
    elif layer=='ga3':
        command = ['ga3/finish_board.py', 'run', 'direct1', scope, 'descending']
    else:
        command = ['resident/run_board.py', 'run', layer, scope, 'direct']
    env = dict(os.environ, V32_GA_OPT_PROFILE=profile)
    if board_input=='sd':
        for name in SENDER_KEYS:
            env.pop(name, None)
    elif input_source() != 'net':
        raise ValueError('set the GA sender environment before selecting net')
    if data is not None:
        if layer=='ga3':
            env['V32_GA3_DATA'] = str(data.resolve(strict=True))
        else:
            command += ['--data', str(data.resolve(strict=True))]
    folder = None
    proc = subprocess.Popen([sys.executable, '-B', *command], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                            start_new_session=True)
    try:
        with proc.stdout:
            for line in proc.stdout:
                print(line, end='', flush=True)
                if line.startswith('RESULTS='):
                    folder = Path(line.strip().split('=',1)[1]).resolve()
        if proc.wait() != 0 or folder is None or folder.parent != ROOT/LAYERS[layer]:
            raise RuntimeError(f'{layer} failed or produced no result receipt')
    except BaseException:
        # The Python driver owns its native child and recovery marker.
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            proc.wait()
        raise
    result = load(folder/RESULT_RECEIPTS[layer])
    expected = 'PASS_DECLARED_GA3_MAC' if layer=='ga3' else 'PASS_GA0_CTPT_' if layer=='ga0' else 'PASS_GA_RESIDENT_'
    if (not result['status'].startswith(expected) or result['input_source']!=board_input
            or result['host_profile']!=profile):
        raise RuntimeError(f'{layer} result identity differs')
    if layer in ('ga0','ga3'):
        key='complete_raw_mac_coverage' if layer=='ga0' else 'complete_raw_MAC_coverage'
        if result[key] is not (scope=='full'):
            raise RuntimeError(f'{layer} result coverage differs')
    elif result['scope']!=scope:
        raise RuntimeError(f'{layer} result scope differs')
    return folder, result


def layer_summary(layer, folder, result):
    seconds = (result['resident_batch_wall_sum_ms']/1000 if layer=='ga3'
               else result['packing_and_resident_seconds'] if layer=='ga0' else result['resident_seconds'])
    request = result['request_wall_ms'] if layer=='ga3' else result['request_ms']
    io = (load(folder/'replay/admission_profile.json')['pread_ms'] if layer=='ga3'
          else result['read_ms'] if layer=='ga0' else result['part_read_ms'])
    wait = (result['admission_wait_ms'] if layer=='ga3' else result['weight_prefetch_wait_ms'] if layer=='ga0'
            else result['part_prefetch_wait_ms'])
    return dict(result=str(folder), verified_words=result['verified_words'], resident_seconds=seconds,
                input_read_or_receive_work_seconds=io/1000, prefetch_wait_seconds=wait/1000,
                request_seconds=request/1000, arm_ntt_seconds=result.get('ntt_ms',0)/1000)


def run_suite(args, board):
    env = board.environment()
    if env['boot_uuid'] != boot_uuid():
        raise RuntimeError(f'boot {VARIANT} first')
    start = env['boot_id']
    campaign = ROOT/'campaigns'/f'{args.scope}_{args.profile}_{args.input}_{stamp()}.json'
    campaign.parent.mkdir(exist_ok=True)
    ledger = dict(status='RUNNING', boot_id=start, boot_uuid=env['boot_uuid'], scope=args.scope,
                  input_source=args.input, profile=args.profile, completed_layers={})

    def save():
        temp = campaign.with_suffix('.tmp')
        temp.write_text(json.dumps(ledger, indent=2)+'\n', encoding='utf-8')
        temp.replace(campaign)

    save()
    try:
        for layer in LAYERS:
            ledger['active_layer'] = layer
            save()
            folder, result = run_layer(layer,args.scope,args.profile,args.input,None)
            before, after = (load(folder/name) for name in ('environment_before.json','environment_after.json'))
            if before['boot_id'] != start or after['boot_id'] != start:
                raise RuntimeError('board changed boots during the campaign')
            ledger['completed_layers'][layer] = layer_summary(layer,folder,result)
            save()
    except BaseException:
        ledger['status'] = 'FAILED_OR_INTERRUPTED'
        print(f'CAMPAIGN={campaign}', flush=True)
        raise
    else:
        ledger['status'] = 'PASS_GA_FOUR_LAYER_REPLAY'
        ledger.pop('active_layer')
    finally:
        save()
    print(json.dumps(ledger,indent=2))
    print(f'CAMPAIGN={campaign}')


def collect(args):
    campaign = None
    folders = args.result or []
    if args.campaign:
        campaign = args.campaign.resolve(strict=True)
        if campaign.parent != ROOT/'campaigns':
            raise ValueError('expected a campaign file from this package')
        ledger = load(campaign)
        folders = folders + [Path(item['result']) for item in ledger['completed_layers'].values()]
    folders = list(dict.fromkeys(p.resolve(strict=True) for p in folders))
    if not folders:
        raise ValueError('provide at least one completed result')
    entries = [(campaign,campaign.name)] if campaign else []
    for folder in folders:
        if folder.parent not in {ROOT/name for name in LAYERS.values()} or not folder.name.startswith('results_'):
            raise ValueError('expected a result folder from this package')
        status_file = folder / ('status.json' if folder.parent==ROOT/'ga3' else 'summary.json')
        if not load(status_file)['status'].startswith(('PASS_GA0_CTPT_', 'PASS_GA_RESIDENT_', 'PASS_FINISH_BOARD_REPLAY')):
            raise ValueError(f'{folder.name} did not complete')
        files = [folder/name for name in RESULT_FILES if (folder/name).is_file()]
        for subdir in RESULT_SUBDIRS:
            path = folder/subdir
            if path.is_dir():
                files += [file for file in path.iterdir() if file.is_file() and file.name!='HARDWARE_ENTERED']
        for file in files:
            file.resolve(strict=True).relative_to(folder)
            if file.is_symlink():
                raise ValueError(f'symlink in result: {file.name}')
            entries.append((file,file.relative_to(folder.parent)))
    archive = ROOT / f'collected_ga_all_{stamp()}.tar.gz'
    staging = archive.with_suffix('.partial')
    with staging.open('xb') as output:
        try:
            with tarfile.open(fileobj=output, mode='w:gz', compresslevel=1) as stream:
                for file, name in entries:
                    stream.add(file,arcname=name,recursive=False)
        except BaseException:
            output.close()
            staging.unlink()
            raise
    staging.replace(archive)
    print(f'DOWNLOAD={archive}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('check')
    actions.add_parser('detect')
    run = actions.add_parser('run')
    run.add_argument('layer', choices=LAYERS)
    run.add_argument('--data', type=Path)
    suite = actions.add_parser('suite')
    for action in (run, suite):
        action.add_argument('scope', choices=('smoke','full'))
        action.add_argument('--input', choices=('sd','net'), default='sd')
        action.add_argument('--profile', choices=('baseline','fast'), default='fast')
    archive = actions.add_parser('collect')
    archive.add_argument('--campaign', type=Path)
    archive.add_argument('--result', type=Path, nargs='+')
    args = parser.parse_args()
    if args.action in ('run', 'suite'):
        def stop(number, _frame):
            raise SystemExit(128+number)
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(number, stop)
    board = check(verify_dependencies=args.action=='check')
    if args.action=='check':
        print('PASS_GA_ALL_PACKAGE')
    elif args.action=='detect':
        env = board.environment()
        expected = boot_uuid()
        print(json.dumps(dict(active_uuid=env['boot_uuid'],expected_uuid=expected,
                              matching=env['boot_uuid']==expected,boot_id=env['boot_id']),indent=2))
    elif args.action=='run':
        run_layer(args.layer,args.scope,args.profile,args.input,args.data)
    elif args.action=='suite':
        run_suite(args,board)
    else:
        collect(args)


if __name__=='__main__':
    main()
