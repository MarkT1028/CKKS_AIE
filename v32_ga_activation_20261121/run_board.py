"""Run and compare the sealed VEK280 GA convolution MAC replays."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import shutil
import statistics
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'common'))
from ga_all_board import ALL_LAYERS, available_images, input_source

BASE = ROOT.parent / 'v32_ga3_splitbo_20261109'
LAYERS = dict(ga0='ga0', ga3='ga3', ga6='resident', ga9='resident')
RESULT_FILES = ('summary.json', 'native.json', 'tiles.csv', 'windows.csv', 'environment_before.json',
                'environment_after.json', 'identity.json', 'runner_timing.json', 'status.json',
                'independently_recomputed_summary.json', 'execution.log')
RESULT_SUBDIRS = ('data_evidence', 'cache_evidence', 'replay')
RESULT_RECEIPTS = {'ga0': 'summary.json', 'ga3': 'independently_recomputed_summary.json',
                   'ga6': 'summary.json', 'ga9': 'summary.json'}
SENDER_KEYS = ('V32_GA_INPUT_IP', 'V32_GA_INPUT_PORT', 'V32_GA_INPUT_KEY')
RESIDENT_LIMITS = dict(ga0=37.817385824, ga3=31.366680443, ga6=15.346888682, ga9=10.570750137)
# Matched 11/20 tuned, fast, SD, read-ahead, original fixtures and GA3 pilot cache.
SD_REQUEST_REFERENCE = dict(ga0=443.117108782, ga3=1469.23015984, ga6=842.040963026, ga9=644.673667847)
GA0_PRELOADED_REFERENCE = 330.368595917
TUNED_RESIDENT_REFERENCE = dict(ga0=43.189359702,ga3=31.958800527,ga6=15.621644408,ga9=10.738672915)
OVERLAP_RESIDENT = dict(ga0=37.817385824,ga3=31.850047319,ga6=16.020062786,ga9=11.075741905)
OVERLAP_SD_REQUEST = dict(ga0=402.035039462,ga3=1469.19451519,ga6=815.096993597,ga9=624.427218642)


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


def boot_image(env):
    for label, image in available_images().items():
        if env['boot_uuid']==image.uuid:
            return label, image
    raise RuntimeError(f'unsupported active boot UUID {env["boot_uuid"]}')


def run_layer(layer, scope, profile, board_input, data, active, no_prefetch=False, part_cache=None,
              banks=None, ntt_block=None, ga3_cache=None):
    label, image = active
    if layer not in image.layers:
        raise ValueError(f'{image.variant} cannot run {layer}')
    if layer=='ga0':
        command = ['ga0/run_board.py', scope]
    elif layer=='ga3':
        command = ['ga3/finish_board.py', 'run', 'direct1', scope, 'descending']
    else:
        command = ['resident/run_board.py', 'run', layer, scope, 'direct']
    env = dict(os.environ, V32_GA_OPT_PROFILE=profile, V32_GA_IMAGE=label,
               V32_GA_DISABLE_READ_AHEAD=str(int(no_prefetch)))
    env.pop('V32_GA_PART_CACHE', None)
    env.pop('V32_GA_RESIDENT_BANKS', None)
    env.pop('V32_GA0_NTT_BLOCK', None)
    if banks is not None and layer in ('ga6','ga9'):
        env['V32_GA_RESIDENT_BANKS']=str(banks)
    if ntt_block is not None and layer=='ga0':
        env['V32_GA0_NTT_BLOCK']=str(ntt_block)
    if ga3_cache is not None and layer=='ga3':
        env['V32_GA3_CACHE']=str(ga3_cache.resolve(strict=True))
    if part_cache is not None and layer in ('ga6','ga9'):
        if board_input!='sd' or profile!='fast' or not part_cache.is_dir():
            raise ValueError('part cache requires fast SD and an existing directory')
        env['V32_GA_PART_CACHE']=str(part_cache.resolve(strict=True))
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


def layer_summary(layer, folder, result, scope):
    seconds = (result['resident_batch_wall_sum_ms']/1000 if layer=='ga3'
               else result['packing_and_resident_seconds'] if layer=='ga0' else result['resident_seconds'])
    request = result['request_wall_ms'] if layer=='ga3' else result['request_ms']
    io = (load(folder/'replay/admission_profile.json')['pread_ms'] if layer=='ga3'
          else result['read_ms'] if layer=='ga0' else result['part_read_ms'])
    wait = (result['admission_wait_ms'] if layer=='ga3' else result['weight_prefetch_wait_ms'] if layer=='ga0'
            else result['part_prefetch_wait_ms'])
    limit = RESIDENT_LIMITS[layer]
    matched_sd = scope=='full' and result['input_source']=='sd'
    duration = request/1000
    enabled = result.get('prefetch_enabled',result.get('weight_prefetch_enabled',False))
    summary = dict(result=str(folder), verified_words=result['verified_words'], resident_seconds=seconds,
                previous_resident_seconds=limit, resident_delta_seconds=(seconds-limit if scope=='full' else None),
                meets_previous_resident_limit=(seconds<=limit if scope=='full' else None),
                previous_tuned_suite_resident_seconds=TUNED_RESIDENT_REFERENCE[layer],
                resident_delta_vs_tuned_suite_seconds=(seconds-TUNED_RESIDENT_REFERENCE[layer] if scope=='full' else None),
                input_read_or_receive_work_seconds=io/1000, prefetch_wait_seconds=(wait/1000 if enabled else 0),
                synchronous_admission_seconds=(wait/1000 if layer=='ga3' and not enabled else None),
                request_seconds=duration, previous_sd_request_seconds=(SD_REQUEST_REFERENCE[layer] if matched_sd else None),
                request_delta_seconds=(duration-SD_REQUEST_REFERENCE[layer] if matched_sd else None),
                meets_sd_request_limit=(duration<=SD_REQUEST_REFERENCE[layer] if matched_sd else None),
                arm_ntt_seconds=result.get('ntt_ms',0)/1000,
                compact_parts=result.get('compact_parts'), input_stream_bytes=result.get('input_stream_bytes'))
    if scope=='full':
        summary['resident_delta_vs_1121_overlap_seconds']=seconds-OVERLAP_RESIDENT[layer]
        summary['request_delta_vs_1121_overlap_seconds']=duration-OVERLAP_SD_REQUEST[layer] if matched_sd else None
    if layer == 'ga0':
        preloaded = result['preloaded_including_ntt_and_slice_seconds']
        summary.update(preloaded_including_ntt_seconds=preloaded,
                       previous_preloaded_including_ntt_seconds=(GA0_PRELOADED_REFERENCE if scope=='full' else None),
                       preloaded_including_ntt_delta_seconds=(preloaded-GA0_PRELOADED_REFERENCE if scope=='full' else None))
        summary['ntt_block_coefficients']=result['ntt_block_coefficients']
    if layer in ('ga6','ga9'):
        summary['bo_banks']=result['bo_banks']
    return summary


def run_suite(args, board):
    env = board.environment()
    active = boot_image(env)
    label, image = active
    start = env['boot_id']
    campaign = ROOT/'campaigns'/f'{label}_{args.scope}_{args.profile}_{args.input}_{stamp()}.json'
    campaign.parent.mkdir(exist_ok=True)
    ledger = dict(status='RUNNING', boot_id=start, boot_uuid=env['boot_uuid'], hardware_variant=image.variant,
                  scope=args.scope, selected_layers=image.layers,
                  input_source=args.input, profile=args.profile, prefetch_disabled=args.no_prefetch,
                  part_cache=str(args.part_cache) if args.part_cache else None, completed_layers={})

    def save():
        temp = campaign.with_suffix('.tmp')
        temp.write_text(json.dumps(ledger, indent=2)+'\n', encoding='utf-8')
        temp.replace(campaign)

    save()
    try:
        for layer in image.layers:
            ledger['active_layer'] = layer
            save()
            folder, result = run_layer(layer,args.scope,args.profile,args.input,None,active,args.no_prefetch,args.part_cache,
                                       args.banks,args.ntt_block,args.ga3_cache)
            before, after = (load(folder/name) for name in ('environment_before.json','environment_after.json'))
            if any(x['boot_id']!=start or x['boot_uuid']!=image.uuid for x in (before,after)):
                raise RuntimeError('board changed boots during the campaign')
            ledger['completed_layers'][layer] = layer_summary(layer,folder,result,args.scope)
            save()
    except BaseException:
        ledger['status'] = 'FAILED_OR_INTERRUPTED'
        print(f'CAMPAIGN={campaign}', flush=True)
        raise
    else:
        ledger['status'] = 'PASS_GA_FOUR_LAYER_REPLAY' if image.layers==ALL_LAYERS else 'PASS_GA_BOOT_REPLAY'
        if args.scope=='full':
            misses = [layer for layer,result in ledger['completed_layers'].items()
                      if not result['meets_previous_resident_limit']]
            ledger['resident_limit_result'] = 'EXCEEDED' if misses else 'MET'
            ledger['layers_over_resident_limit'] = misses
            if args.input=='sd':
                request_misses=[k for k,v in ledger['completed_layers'].items() if not v['meets_sd_request_limit']]
                ledger['layers_over_sd_request_limit']=request_misses
                ledger['sd_request_limit_result']='EXCEEDED' if request_misses else 'MET'
            ledger['summed_resident_seconds']=sum(v['resident_seconds'] for v in ledger['completed_layers'].values())
            ledger['summed_request_seconds']=sum(v['request_seconds'] for v in ledger['completed_layers'].values())
        ledger.pop('active_layer')
    finally:
        save()
    print(json.dumps(ledger,indent=2))
    print(f'CAMPAIGN={campaign}')


def study(args, board):
    initial=board.environment()
    active=boot_image(initial)
    if active[0]!='tuned':
        raise ValueError('comparison requires the tuned image')
    bank_study=args.action=='compare-banks'
    layer=args.layer if bank_study else 'ga0'
    scope=args.segment if bank_study else 'smoke'
    settings=[2,3,3,2] if bank_study else [1024,512,2048,2048,512,1024]
    trials=[]
    for setting in settings:
        folder,result=run_layer(layer,scope,'fast','sd',None,active,
                                banks=setting if bank_study else None,
                                ntt_block=None if bank_study else setting)
        env=board.environment()
        if any(env[x]!=initial[x] for x in ('boot_id','boot_uuid')):
            raise RuntimeError('board changed boots during comparison')
        if bank_study and (result['bo_banks']!=setting or not result['prefetch_enabled']):
            raise RuntimeError('bank selection or read-ahead differs')
        trials.append(dict(setting=setting,**layer_summary(layer,folder,result,scope),
                           stage_work_ms=result['stage_work_ms']))
    if len({row['verified_words'] for row in trials})!=1:
        raise RuntimeError('comparison coverage differs')
    metric='resident_seconds' if bank_study else 'arm_ntt_seconds'
    scores={value:statistics.median(x[metric] for x in trials if x['setting']==value)
            for value in sorted(set(settings))}
    winner=min(scores,key=scores.get)
    # Prefer the measured leader only when both opposed-order runs beat the alternatives.
    stable=all(max(x[metric] for x in trials if x['setting']==winner)
               < min(x[metric] for x in trials if x['setting']==value)
               for value in scores if value!=winner)
    out=ROOT/'studies'
    out.mkdir(exist_ok=True)
    receipt=out/f'{args.action}_{layer}_{scope}_{stamp()}.json'
    evidence=dict(status='PASS_GA_COMPARISON',boot_id=initial['boot_id'],boot_uuid=initial['boot_uuid'],
                  layer=layer,scope=scope,schedule=settings,metric=metric,median_seconds=scores,
                  candidate=winner if stable else None,trials=trials,
                  timing_scope='Same checked subset and configuration per trial. No full-layer projection.')
    receipt.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in evidence.items() if k!='trials'},indent=2))
    print(f'STUDY={receipt}')


def prepare_ga3_cache(args):
    cache=args.cache.resolve()
    if not cache.parent.is_dir() or args.cache.is_symlink():
        raise ValueError('choose a cache folder with an existing parent')
    if (not math.isfinite(args.budget_gib) or not math.isfinite(args.keep_free_gib)
            or not 1<=args.budget_gib<=6 or args.keep_free_gib<0):
        raise ValueError('use a 1–6 GiB cache budget and a nonnegative free-space reserve')
    existing=0
    if cache.is_dir():
        existing=sum(p.stat().st_size for p in (cache/'inputs').glob('*.qpk') if not p.is_symlink())
    if shutil.disk_usage(cache.parent).free < max(0,args.budget_gib*2**30-existing)+args.keep_free_gib*2**30:
        raise ValueError('not enough free space for this GA3 cache budget and reserve')
    command='prepare' if args.prepare else 'plan'
    subprocess.run([sys.executable,'-B',str(BASE/'compact_cache.py'),command,'bounded',
                    '--budget-gib',str(args.budget_gib)],env=dict(os.environ,V32_GA3_CACHE=str(cache)),check=True)


def collect(args):
    folders = list(args.result or [])
    entries = []
    paths=list(args.campaign or [])
    if args.latest:
        matching=sorted((ROOT/'campaigns').glob('*.json'),key=lambda p:p.stem.rsplit('_',1)[-1],reverse=True)
        latest=next((p for p in matching if load(p).get('status')=='PASS_GA_FOUR_LAYER_REPLAY'
                     and load(p).get('scope')=='full'),None)
        if latest is None:
            raise ValueError('no completed four-layer full campaign found')
        paths.append(latest)
    campaigns = dict.fromkeys(path.resolve(strict=True) for path in paths)
    for campaign in campaigns:
        if campaign.parent != ROOT/'campaigns':
            raise ValueError('expected a campaign file from this package')
        ledger = load(campaign)
        entries.append((campaign,campaign.name))
        folders.extend(Path(item['result']) for item in ledger['completed_layers'].values())
    folders = list(dict.fromkeys(p.resolve(strict=True) for p in folders))
    for path in dict.fromkeys(args.study or []):
        path=path.resolve(strict=True)
        if path.parent!=ROOT/'studies' or load(path)['status']!='PASS_GA_COMPARISON':
            raise ValueError('expected a completed study from this package')
        entries.append((path,path.name))
    activation=list(args.ga5 or [])
    if args.ga5_latest:
        files=sorted((ROOT/'ga5').glob('results_ga5_*/summary.json'),reverse=True)
        latest=next((p.parent for p in files if load(p).get('status')=='PASS_GA5_RAW_MAC_BOARD'),None)
        if latest is None:
            raise ValueError('no completed GA5 board replay found')
        activation.append(latest)
    for folder in dict.fromkeys(p.resolve(strict=True) for p in activation):
        if folder.parent!=ROOT/'ga5' or not folder.name.startswith('results_ga5_'):
            raise ValueError('expected a G5 result from this package')
        receipt=load(folder/'summary.json')
        if receipt['status']!='PASS_GA5_RAW_MAC_BOARD':
            raise ValueError('G5 result did not complete on board')
        entries.extend((folder/name,f'{folder.name}/{name}') for name in ('summary.json','actual.bin'))
    if not folders and not entries:
        raise ValueError('provide at least one completed result')
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
    archive = ROOT / f'collected_ga_activation_{stamp()}.tar.gz'
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
    banks = actions.add_parser('compare-banks')
    banks.add_argument('layer',choices=('ga6','ga9'))
    banks.add_argument('--segment',choices=('pilot-head','pilot-tail'),default='pilot-head')
    actions.add_parser('study-ntt')
    cache = actions.add_parser('ga3-cache')
    cache.add_argument('--cache',type=Path,required=True)
    cache.add_argument('--budget-gib',type=float,default=4)
    cache.add_argument('--keep-free-gib',type=float,default=10)
    cache.add_argument('--prepare',action='store_true')
    for action in (run, suite):
        action.add_argument('scope', choices=('smoke','full','pilot-head','pilot-tail') if action==run else ('smoke','full'))
        action.add_argument('--input', choices=('sd','net'), default='sd')
        action.add_argument('--profile', choices=('baseline','fast'), default='fast')
        action.add_argument('--no-prefetch', action='store_true', help='disable input read-ahead with the same host profile')
        action.add_argument('--part-cache',type=Path,help='optional verified SD part cache for GA6/GA9')
        action.add_argument('--ga3-cache',type=Path)
        action.add_argument('--banks',type=int,choices=(2,3))
        action.add_argument('--ntt-block',type=int,choices=(512,1024,2048))
    archive = actions.add_parser('collect')
    archive.add_argument('--campaign', type=Path, action='append')
    archive.add_argument('--result', type=Path, nargs='+')
    archive.add_argument('--latest',action='store_true',help='collect the newest completed four-layer full campaign')
    archive.add_argument('--study',type=Path,action='append')
    archive.add_argument('--ga5',type=Path,action='append')
    archive.add_argument('--ga5-latest',action='store_true')
    args = parser.parse_args()
    if getattr(args,'part_cache',None) and (args.input!='sd' or args.profile!='fast'
            or getattr(args,'layer','ga6') not in ('ga6','ga9') or not args.part_cache.is_dir()):
        parser.error('--part-cache requires an existing directory and fast SD for GA6/GA9 or the suite')
    if args.action in ('run','suite'):
        layer=getattr(args,'layer',None)
        if ((args.banks is not None and (layer not in (None,'ga6','ga9') or (args.banks==3 and args.profile=='baseline')))
                or (args.ntt_block is not None and (layer not in (None,'ga0') or args.profile!='fast'))
                or (args.scope.startswith('pilot-') and layer not in ('ga6','ga9'))
                or (args.ga3_cache is not None and (layer not in (None,'ga3') or args.input!='sd'))):
            parser.error('sample and bank controls are for GA6/GA9, NTT block for fast GA0, compact cache for SD GA3')
    if args.action in ('run', 'suite','compare-banks','study-ntt'):
        def stop(number, _frame):
            raise SystemExit(128+number)
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(number, stop)
    board = check(verify_dependencies=args.action=='check')
    if args.action=='check':
        print('PASS_GA_OVERLAP_PACKAGE')
    elif args.action=='detect':
        env = board.environment()
        images = available_images()
        label = next((label for label,image in images.items() if image.uuid==env['boot_uuid']),None)
        print(json.dumps(dict(active_uuid=env['boot_uuid'],matching=label is not None, image=label,
                              layers=images[label].layers if label else (), boot_id=env['boot_id']),indent=2))
    elif args.action=='run':
        folder,result=run_layer(args.layer,args.scope,args.profile,args.input,args.data,
                                boot_image(board.environment()),args.no_prefetch,args.part_cache,
                                args.banks,args.ntt_block,args.ga3_cache)
        print(json.dumps(layer_summary(args.layer,folder,result,args.scope),indent=2))
    elif args.action=='suite':
        run_suite(args,board)
    elif args.action in ('compare-banks','study-ntt'):
        study(args,board)
    elif args.action=='ga3-cache':
        prepare_ga3_cache(args)
    else:
        collect(args)


if __name__=='__main__':
    main()
