"""Read-only OpenSSL EVP capability check, before any hardware run."""
import argparse, json, subprocess
import ga3_board as b
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--available',action='store_true');args=parser.parse_args()
    b.board()
    exe=b.ROOT/'bin/ga3_host_native_legacy'
    run=subprocess.run([str(exe),'--crypto-check'],capture_output=True,text=True,timeout=15)
    answer=dict(status='SUPPORTED' if run.returncode==0 else 'UNSUPPORTED_SHA256_CANDIDATE',
                stdout=run.stdout.strip(),stderr=run.stderr.strip(),returncode=run.returncode,
                firmware_changed=False,hardware_executed=False)
    if args.available:
        if run.returncode:print('SKIP_SHA256: existing userspace EVP API unavailable; legacy/sequential remain available.')
        return 0 if run.returncode==0 else 1
    b.write(b.ROOT/'HASH_CAPABILITIES.json',answer);print(json.dumps(answer,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
