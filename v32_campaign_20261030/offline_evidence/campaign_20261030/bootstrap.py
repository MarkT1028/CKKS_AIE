"""Prepare a new research campaign without editing any frozen firmware/source."""
from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent;W=R.parents[1];OLD=W/'board_packages/v32_overlap_20261030';P=R/'board_files'
PIN='1bcb9582a15d6555abe83c4984397ea1aece53419aa42c8148a49b31e4eba3f6'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert sha(OLD/'SHA256SUMS_PACKAGE')==PIN
 for line in (OLD/'SHA256SUMS_PACKAGE').read_text().splitlines():
  h,n=line.split('  ',1);assert sha(OLD/n)==h,n
 assert not P.exists()
 shutil.copytree(OLD,P,ignore=shutil.ignore_patterns('__pycache__','SHA256SUMS_PACKAGE','PACKAGE_STATUS.json'))
 (R/'evidence').mkdir(exist_ok=True);(R/'build').mkdir(exist_ok=True)
 (R/'evidence/source_identity.json').write_text(json.dumps(dict(source_package=str(OLD),source_manifest_sha256=PIN,all_images_and_host_CPU_sources_reused_byte_exact=True,hardware_programmed=False,new_board_performance='PENDING'),indent=2)+'\n')
 print('CAMPAIGN_WORKTREE_PREPARED',P)
if __name__=='__main__':main()
