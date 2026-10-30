"""Create an isolated next-round overlay; never change a frozen package."""
from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent;W=R.parents[1];OLD=W/'board_packages/v32_coreopt_20261029';P=R/'board_files'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not P.exists()
    ignore={'PACKAGE_STATUS.json','SHA256SUMS_PACKAGE','OFFLINE_VERIFICATION.json','SOURCE_PROVENANCE.json','START_HERE.md','__pycache__'}
    shutil.copytree(OLD,P,ignore=lambda d,n:[x for x in n if x in ignore])
    (R/'evidence').mkdir(exist_ok=True);(R/'build').mkdir(exist_ok=True)
    original={p.relative_to(OLD).as_posix():sha(p) for p in OLD.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for sub in ('host','common','tests'):
        shutil.copytree(OLD/sub,R/'reference'/sub)
    (R/'evidence/frozen_source_snapshot.json').write_text(json.dumps(dict(source=str(OLD),manifest_sha256=sha(OLD/'SHA256SUMS_PACKAGE'),files=original,board_tested=False),indent=2)+'\n',encoding='utf-8')
    print('ISOLATED_OVERLAY_READY')
if __name__=='__main__':main()
