from pathlib import Path
import hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parent;W=R.parents[1];P=W/'board_packages/v32_campaign_20261030';G=Path('E:/vek280_AIe_ckks/AIE_git');D=G/P.name;Z=G.parent/(P.name+'.zip')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def staged():return subprocess.check_output(['git','-c','safe.directory='+str(G),'diff','--cached','--name-status'],cwd=G,text=True)
def main():
    qa=json.loads((R/'evidence/final_release.json').read_text());assert qa['status']=='PASS_SEALED_CAMPAIGN_ZIP_GIT_AND_CLI_GUARDS';assert not D.exists() and not Z.exists()
    assert sha(P/'SHA256SUMS_PACKAGE')==qa['manifest_sha256'] and sha(P.with_suffix('.zip'))==qa['zip_sha256']
    before=staged();shutil.copytree(P,D);shutil.copy2(P.with_suffix('.zip'),Z)
    for p in P.rglob('*'):
        if p.is_file():assert sha(p)==sha(D/p.relative_to(P))
    assert staged()==before and sha(Z)==qa['zip_sha256']
    facts=dict(status='PUBLISHED_OFFLINE_VERIFIED_RESEARCH_CAMPAIGN',directory=str(D),zip=str(Z),files=qa['files'],package_bytes=qa['package_bytes'],zip_bytes=qa['zip_bytes'],manifest_sha256=qa['manifest_sha256'],zip_sha256=qa['zip_sha256'],user_Git_staging_unchanged=True,commit_or_push_performed=False,new_firmware_bytes=False,new_board_performance='PENDING',board_tested=False,hardware_programmed=False,instructions=str(D/'START_HERE.md'))
    (R/'evidence/PUBLICATION.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(facts,ensure_ascii=True,indent=2))
if __name__=='__main__':main()
