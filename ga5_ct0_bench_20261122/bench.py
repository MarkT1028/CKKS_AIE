"""Measure verified G5 replays with the existing tuned board server."""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import struct
import subprocess
import sys
from time import perf_counter_ns


ROOT = Path(__file__).resolve().parent
CT0_FIXTURE_SHA256 = '3bd791f123f1563c5874498abe32021f1197fc36a9b84c982c29ca5c7b2866fc'
TUNED_UUID = '6cc21e10b0805092bc88f9000f5a6d4f'
COMPARISON = ('stream', 'tiles', 'tiles', 'stream')


def board_environment():
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text('ascii').strip()
    uuid = Path('/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid').read_bytes().decode('ascii').strip('\x00\n')
    if uuid != TUNED_UUID or not boot_id:
        raise ValueError('G5 requires the sealed tuned board image')
    return dict(boot_id=boot_id, boot_uuid=uuid)


def fixture_identity(fixture, expected, protocol):
    content = (fixture / 'fixture.json').read_bytes()
    identity = hashlib.sha256(content).hexdigest()
    if identity != expected:
        raise ValueError('G5 fixture manifest SHA-256 differs from the sealed release')
    manifest = json.loads(content)
    request = fixture / 'request.bin'
    if (manifest['format'] != 'v32_ga5_tiles_v1' or manifest['layer'] != 'g_a.5'
            or manifest['scope'] not in ('pilot','ciphertext','full')
            or request.is_symlink() or request.stat().st_size != manifest['request_bytes']):
        raise ValueError('invalid G5 fixture file or scope')
    protocol.validate_coverage(manifest)
    return identity, manifest, request


def stop_child(child):
    if child.poll() is None:
        child.terminate()
        # The board wrapper owns recovery if an active PL launch was interrupted.
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    child.stdout.close()
    child.stdin.close()


def replay(request, meta, manifest_sha, policy, command, protocol, initial, export=None):
    strict = policy == 'stream'
    input_stream = hashlib.sha256() if strict else None
    output_stream = hashlib.sha256() if strict else None
    measured = dict(input_read=0, input_sha256=0, send=0, wait_and_receive=0, output_sha256=0, output_save=0)
    bytes_read = words = sync_ns = mac_ns = 0
    proof = []
    temporary = export.with_suffix('.partial') if export else None
    started = perf_counter_ns()
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=True)
    try:
        magic, backend = struct.unpack('<II', protocol.read_exact(child.stdout,8))
        if (magic, backend) != (protocol.HELLO, int(initial is not None)):
            raise ValueError('G5 server handshake or backend differs')
        setup_ns = perf_counter_ns() - started
        start = perf_counter_ns()
        with request.open('rb') as source, contextlib.ExitStack() as resources:
            target = resources.enter_context(temporary.open('xb')) if temporary else None
            for number, tile in enumerate(meta['tiles'],1):
                tick = perf_counter_ns()
                header = protocol.read_exact(source,28)
                n, l, k = (tile[key] for key in ('N','L','K'))
                if (tile['tile'] != number
                        or struct.unpack('<7I',header) != (protocol.REQUEST,number,n,l,k,0,0)):
                    raise ValueError(f'G5 request identity differs at tile {number}')
                packet = protocol.read_exact(source, l*8+4*n*l*k*8)
                measured['input_read'] += perf_counter_ns() - tick
                bytes_read += len(header)+len(packet)

                tick = perf_counter_ns()
                tile_digest = hashlib.sha256(header)
                tile_digest.update(packet)
                if tile_digest.hexdigest() != tile['input_sha256']:
                    raise ValueError(f'G5 input SHA-256 differs at tile {number}')
                if strict:
                    input_stream.update(header)
                    input_stream.update(packet)
                measured['input_sha256'] += perf_counter_ns() - tick

                tick = perf_counter_ns()
                child.stdin.write(header)
                child.stdin.write(packet)
                child.stdin.flush()
                measured['send'] += perf_counter_ns() - tick
                tick = perf_counter_ns()
                reply, ident, nn, ll, kk, sync, mac = struct.unpack('<5I2Q', protocol.read_exact(child.stdout,36))
                if (reply,ident,nn,ll,kk) != (protocol.REPLY,number,n,l,k):
                    raise ValueError(f'G5 reply identity differs at tile {number}')
                data = protocol.read_exact(child.stdout,3*n*l*8)
                measured['wait_and_receive'] += perf_counter_ns() - tick

                tick = perf_counter_ns()
                result_sha = hashlib.sha256(data).hexdigest()
                if result_sha != tile['sha256']:
                    raise ValueError(f'G5 output SHA-256 differs at tile {number}')
                if strict:
                    output_stream.update(data)
                measured['output_sha256'] += perf_counter_ns() - tick
                if target:
                    tick = perf_counter_ns()
                    target.write(data)
                    measured['output_save'] += perf_counter_ns() - tick
                words += 3*n*l
                sync_ns += sync
                mac_ns += mac
                proof.append(dict(tile=number, sha256=result_sha, receive_sync_ns=sync, run_ns=mac))
            tick = perf_counter_ns()
            trailer = protocol.read_exact(source,4)
            extra = source.read(1)
            measured['input_read'] += perf_counter_ns() - tick
            bytes_read += len(trailer)
            if trailer != struct.pack('<I',protocol.STOP) or extra or bytes_read != meta['request_bytes'] or words != meta['raw_words']:
                raise ValueError('G5 request or response length differs')
            input_sha = output_sha = None
            if strict:
                tick = perf_counter_ns()
                input_stream.update(trailer)
                input_sha = input_stream.hexdigest()
                measured['input_sha256'] += perf_counter_ns() - tick
                tick = perf_counter_ns()
                output_sha = output_stream.hexdigest()
                measured['output_sha256'] += perf_counter_ns() - tick
                if input_sha != meta['request_sha256'] or output_sha != meta['reference_sha256']:
                    raise ValueError('G5 complete stream SHA-256 differs')
            if target:
                tick = perf_counter_ns()
                target.flush()
                measured['output_save'] += perf_counter_ns() - tick
        child.stdin.write(trailer)
        child.stdin.close()
        if child.wait(timeout=30) != 0:
            raise RuntimeError('G5 server failed during shutdown')
        elapsed = perf_counter_ns() - start
        if initial is not None and board_environment() != initial:
            raise RuntimeError('board changed during replay')
        if temporary:
            temporary.replace(export)
    finally:
        stop_child(child)
        if temporary:
            temporary.unlink(missing_ok=True)
    return dict(scope=meta['scope'], ciphertexts=meta['ciphertexts'], fixture_sha256=manifest_sha,
                check_policy=policy, verified_input_tiles=len(proof), verified_output_tiles=len(proof),
                verified_words=words, request_bytes=bytes_read, output_bytes=words*8,
                measured_request_sha256=input_sha, measured_output_sha256=output_sha,
                sealed_request_sha256=meta['request_sha256'], sealed_output_sha256=meta['reference_sha256'],
                setup_seconds=setup_ns/1e9, request_seconds=elapsed/1e9,
                replay_excluding_file_read_seconds=(elapsed-measured['input_read'])/1e9,
                board_receive_range_and_sync_seconds=sync_ns/1e9, board_mac_and_readback_seconds=mac_ns/1e9,
                saved_output=export is not None,
                client_stage_seconds={key:value/1e9 for key,value in measured.items()},tiles=proof)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-package', type=Path,default=ROOT.parent/'v32_ga_activation_20261121')
    parser.add_argument('--fixture',type=Path)
    parser.add_argument('--fixture-sha256',default=CT0_FIXTURE_SHA256)
    parser.add_argument('--mode',choices=('compare','verify','export'),default='compare')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--model',type=Path,help='software contract model for local validation')
    args=parser.parse_args()
    installed=args.board_package.resolve(strict=True)
    sys.path.insert(0,str(installed/'ga5'))
    import replay as protocol
    manifest_sha, meta, request=fixture_identity(args.fixture or (installed/'ga5_full_ct0'),
                                                  args.fixture_sha256,protocol)
    initial=None if args.model else board_environment()
    command=([str(args.model.resolve(strict=True))] if args.model
             else [sys.executable,'-B',str(installed/'ga5/replay.py'),'serve'])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=args.output or ROOT/f'results_ga5_bench_{stamp}'
    output.mkdir()
    export=output/'actual.bin' if args.mode=='export' else None
    policy=COMPARISON if args.mode=='compare' else ('stream',)
    trials=[]
    for index, method in enumerate(policy,1):
        record=replay(request,meta,manifest_sha,method,command,protocol,initial,export=export)
        record['trial']=index
        trials.append(record)
        print(f'PASS_GA5_TRIAL {index}/{len(policy)} policy={method} tiles={record["verified_output_tiles"]} '
              f'request_s={record["request_seconds"]:.6f} '
              f'excluding_file_read_s={record["replay_excluding_file_read_seconds"]:.6f}',flush=True)
    medians={}
    for method in dict.fromkeys(policy):
        subset=[r for r in trials if r['check_policy']==method]
        medians[method]={key:statistics.median(r[key] for r in subset) for key in (
            'request_seconds','replay_excluding_file_read_seconds','board_mac_and_readback_seconds')}
        medians[method]['client_stage_seconds']={
            key:statistics.median(r['client_stage_seconds'][key] for r in subset)
            for key in subset[0]['client_stage_seconds']}
    evidence=dict(status='PASS_GA5_BENCH_MODEL' if args.model else 'PASS_GA5_BENCH_BOARD',
                  backend='software_model' if args.model else 'pure_pl', environment=initial,
                  scope=meta['scope'], ciphertexts=meta['ciphertexts'],fixture_sha256=manifest_sha,
                  mode=args.mode, schedule=policy, medians=medians,trials=trials,
                  verification='Both policies check every input tile and every output tile against the pinned fixture, in order. Stream also hashes both complete byte streams.',
                  timing_scope='Client replay minus file read still includes hashing and pipe transfers. Server work overlaps the client send/receive time. Rebuilding OpenFHE ciphertexts and the rest of the activation are outside this board replay.')
    summary=output/'summary.json'
    with summary.open('x',encoding='ascii') as file:
        json.dump(evidence,file,indent=2)
        file.write('\n')
    print(evidence['status'])
    print(f'GA5_BENCH_RESULT={summary.resolve()}')


if __name__=='__main__':
    def interrupt(number,_frame):
        raise SystemExit(128+number)

    for number in (signal.SIGTERM,signal.SIGHUP):
        signal.signal(number,interrupt)
    main()
