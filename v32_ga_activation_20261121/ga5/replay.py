"""Replay sealed G5 square and product tiles with the existing pure-PL MAC ABI."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import signal
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT.parent
HELLO, REQUEST, REPLY, STOP = (0x47413148, 0x47413151, 0x47413152, 0x47413153)


def read_exact(stream, count):
    block = stream.read(count)
    if len(block) != count:
        raise ValueError('truncated GA5 request or response')
    return block


def validate_coverage(meta):
    count=1 if meta['scope']=='ciphertext' else 16
    if meta['ciphertexts']!=count:
        raise ValueError('activation ciphertext count differs')
    expected=[]
    for ct in range(count):
        for phase,towers in enumerate((52,52,51),1):
            if meta['scope']=='pilot':
                expected.extend((ct,phase,t,j,128,1,1) for t,j in ((0,0),(towers-1,131072-128)))
            else:
                expected.extend((ct,phase,t,j,8192,min(16,towers-t),1)
                                for t in range(0,towers,16) for j in range(0,131072,8192))
    fields=('ct','phase','tower','coefficient','N','L','K')
    observed=[tuple(tile[name] for name in fields) for tile in meta['tiles']]
    if observed!=expected:
        raise ValueError('activation tile coordinates or coverage differ')


def run_fixture(fixture, result, command, *, hardware, on_exit):
    from time import perf_counter_ns as now
    meta_path = fixture/'fixture.json'
    manifest = meta_path.read_bytes()
    meta = json.loads(manifest)
    packed = fixture/'request.bin'
    if (meta['format']!='v32_ga5_tiles_v1' or meta['layer']!='g_a.5'
            or meta['scope'] not in ('pilot','ciphertext','full')
            or packed.is_symlink() or packed.stat().st_size!=meta['request_bytes']):
        raise ValueError('unexpected GA5 fixture')
    validate_coverage(meta)
    trial = result/'actual.partial'
    started = now()
    read = send = receive = check = sync = execute = words = 0
    request_sha, actual_sha = hashlib.sha256(), hashlib.sha256()
    rows = []
    child = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,start_new_session=True)
    try:
        hello, backend = struct.unpack('<II',read_exact(child.stdout,8))
        if (hello,backend)!=(HELLO,int(hardware)):
            raise ValueError('wrong activation server backend')
        setup = now()-started
        start = now()
        with packed.open('rb') as source, trial.open('xb') as output:
            for expected, tile in enumerate(meta['tiles'],1):
                tick = now()
                header = read_exact(source,28)
                if tile['tile']!=expected or struct.unpack('<7I',header)!=(REQUEST,expected,tile['N'],tile['L'],tile['K'],0,0):
                    raise ValueError(f'GA5 request header differs at tile {expected}')
                n,l,k=tile['N'],tile['L'],tile['K']
                if not (128<=n<=8192 and not n & (n-1) and 1<=l<=16 and k==1):
                    raise ValueError('unexpected GA5 tile shape')
                payload=read_exact(source,l*8+4*n*l*k*8)
                read+=now()-tick
                tick=now()
                request_sha.update(header)
                request_sha.update(payload)
                packet_digest=hashlib.sha256(header)
                packet_digest.update(payload)
                if packet_digest.hexdigest()!=tile['input_sha256']:
                    raise ValueError(f'GA5 input SHA256 differs at tile {expected}')
                check+=now()-tick
                tick=now()
                child.stdin.write(header)
                child.stdin.write(payload)
                child.stdin.flush()
                send+=now()-tick
                tick=now()
                reply, ident, nn, ll, kk, sent, ran = struct.unpack('<5I2Q',read_exact(child.stdout,36))
                if (reply,ident,nn,ll,kk)!=(REPLY,expected,n,l,k):
                    raise ValueError(f'GA5 reply identity differs at tile {expected}')
                block=read_exact(child.stdout,3*n*l*8)
                receive+=now()-tick
                tick=now()
                digest=hashlib.sha256(block).hexdigest()
                if digest!=tile['sha256']:
                    raise ValueError(f'GA5 PL output differs at tile {expected}')
                actual_sha.update(block)
                output.write(block)
                check+=now()-tick
                sync+=sent
                execute+=ran
                words+=3*n*l
                rows.append(dict(tile=expected,sha256=digest,receive_sync_ns=sent,run_ns=ran))
            stop=read_exact(source,4)
            request_sha.update(stop)
            if (stop!=struct.pack('<I',STOP) or source.read(1)
                    or request_sha.hexdigest()!=meta['request_sha256']
                    or words!=meta['raw_words'] or actual_sha.hexdigest()!=meta['reference_sha256']):
                raise ValueError('GA5 fixture or complete returned stream differs')
        child.stdin.write(stop)
        child.stdin.close()
        if child.wait(timeout=30)!=0:
            raise RuntimeError('GA5 server failed during shutdown')
        wall=now()-start
    finally:
        on_exit(child)
        child.stdout.close()
        child.stdin.close()
    trial.replace(result/'actual.bin')
    return dict(status='PASS_GA5_RAW_MAC_BOARD' if hardware else 'PASS_GA5_RAW_MAC_MODEL',
                backend='pure_pl' if hardware else 'software_model',
                layer='g_a.5', scope=meta['scope'], manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                actual_sha256=actual_sha.hexdigest(), tiles=rows, verified_words=words,
                complete_raw_mac_coverage=meta['scope']=='full',
                setup_seconds=setup/1e9, request_seconds=wall/1e9, sd_read_seconds=read/1e9,
                send_seconds=send/1e9, wait_and_receive_seconds=receive/1e9, verification_and_save_seconds=check/1e9,
                board_receive_range_and_sync_seconds=sync/1e9, board_mac_and_readback_seconds=execute/1e9,
                timing_scope='Raw activation tiles with host pipe transfers. Level alignment, relinearization and final addition are ground-side.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('replay','serve'))
    parser.add_argument('--fixture',type=Path,default=ROOT/'pilot')
    parser.add_argument('--model',type=Path,help='local software model executable')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.model:
        if args.action!='replay' or args.output is None:
            parser.error('model requires replay and a new --output')
        args.output.mkdir()

        def stop(child):
            if child.poll() is None:
                child.kill()
                child.wait()
        result=run_fixture(args.fixture,args.output,[str(args.model.resolve(strict=True))],
                           hardware=False,on_exit=stop)
        with (args.output/'summary.json').open('x',encoding='ascii') as file:
            json.dump(result,file,indent=2)
        print(result['status'])
        return 0
    sys.path.insert(0,str(PACKAGE))
    from run_board import boot_image, check, stamp
    owner=check()
    with contextlib.redirect_stdout(sys.stderr), owner.lock():
        before=owner.environment()
        label,image=boot_image(before)
        if label!='tuned':
            raise ValueError('G5 requires the sealed tuned image')
        owner.guard_recovery(before)
        image.check_xclbin()
        markers=[Path('/run/v32-'+stem+'-active-'+before['boot_id'])
                 for stem in ('ga-live','ga-resident','ga0-full')]
        if any(m.exists() for m in markers):
            raise RuntimeError('unfinished PL invocation found')
        binary=ROOT/'bin/tuned/ga5_server'
        subprocess.run(['sha256sum','-c','--quiet','BUILD_SHA256'],cwd=binary.parent,check=True)
        command=[str(binary),str(image.xclbin),str(markers[0])]

        def interrupt(number,_frame):
            raise SystemExit(128+number)

        def cleanup(child):
            if child.poll() is None:
                owner.stop_owned_child(child)
            if markers[0].exists():
                owner.write(owner.ROOT/'RECOVERY_REQUIRED.json',
                            dict(boot_id=before['boot_id'],reason='interrupted GA5 PL invocation'))

        for number in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
            signal.signal(number,interrupt)
        if args.action=='serve':
            child=subprocess.Popen(command,start_new_session=True,stdout=sys.__stdout__.buffer)
            try:
                return child.wait()
            finally:
                cleanup(child)
        dest=args.output or ROOT/f'results_ga5_{stamp()}'
        dest.mkdir()
        result=run_fixture(args.fixture,dest,command,hardware=True,on_exit=cleanup)
        after=owner.environment()
        if any(before[key]!=after[key] for key in ('boot_uuid','boot_id')):
            raise RuntimeError('board changed during GA5 trial')
        result.update(boot_uuid=before['boot_uuid'],boot_id=before['boot_id'])
        (dest/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(result['status'])
    print(f'RESULTS={dest.resolve()}')
    print(f'GA5_RETURN={dest.resolve()/"actual.bin"}')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
