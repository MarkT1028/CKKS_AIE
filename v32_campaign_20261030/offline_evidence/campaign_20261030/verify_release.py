"""Validate the exact sealed bytes, Git/ZIP transfer and non-board CLI guards."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile,zipfile
R=Path(__file__).resolve().parent;W=R.parents[1];P=W/'board_packages/v32_campaign_20261030';BASE=W/'board_packages/v32_hs4_20261027'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,cwd,log,env=None,good=True):
    p=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,text=True);(R/'evidence'/log).write_text(p.stdout+p.stderr);assert (p.returncode==0)==good,(args,p.returncode,p.stdout[-800:],p.stderr[-1400:]);return p
def main():
    members={n:h for h,n in (line.split('  ',1) for line in (P/'SHA256SUMS_PACKAGE').read_text().splitlines())};members['SHA256SUMS_PACKAGE']=sha(P/'SHA256SUMS_PACKAGE');assert all(sha(P/n)==h for n,h in members.items())
    old=W/'board_packages/v32_overlap_20261030'
    for p in (old/'variants').rglob('*'):
        if p.is_file():assert sha(p)==sha(P/p.relative_to(old))
    env=dict(os.environ,V32_BASE_PACKAGE=str(BASE),PYTHONDONTWRITEBYTECODE='1')
    archive=P.with_suffix('.zip');assert not archive.exists()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n in sorted(members):z.write(P/n,P.name+'/'+n)
    with tempfile.TemporaryDirectory(prefix='campaign-transport-') as tmp:
        root=Path(tmp);extracted=root/'extracted';extracted.mkdir()
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.infolist())==len(members)
            for info in z.infolist():
                name=Path(info.filename);assert not name.is_absolute() and '..' not in name.parts and name.parts[0]==P.name
                dst=extracted/name;dst.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as inp,dst.open('wb') as out:shutil.copyfileobj(inp,out)
        assert all(sha(extracted/P.name/n)==h for n,h in members.items())
        run(['python3',extracted/P.name/'board_runner.py','check'],root,'zip_preflight.log',env)
        repo=root/'repo';repo.mkdir();parent=Path('/mnt/e/vek280_AIe_ckks/AIE_git')
        for n in ('.gitattributes','.gitignore'):shutil.copy2(parent/n,repo/n)
        shutil.copytree(P,repo/P.name);run(['git','init','-q','--initial-branch=codex/campaign-transport'],repo,'git_init.log')
        run(['git','-c','core.autocrlf=true','add','.'],repo,'git_add.log')
        run(['git','-c','user.name=Offline Transport Test','-c','user.email=codex@localhost','-c','commit.gpgsign=false','commit','-qm','Test campaign transport'],repo,'git_commit.log')
        checkout=root/'checkout';run(['git','-c','core.autocrlf=true','clone','-q',repo,checkout],root,'git_clone.log');q=checkout/P.name
        changed=[n for n,h in members.items() if not (q/n).is_file() or sha(q/n)!=h]
        assert not changed,('ignored or converted package member in checkout',changed)
        run(['python3',q/'board_runner.py','check'],root,'Git_checkout_preflight.log',env)
        initial=run(['sh',q/'run_study.sh'],root,'initial_next.log',env);assert 'STUDY_PROGRESS=0/11' in initial.stdout and 'NEXT_STEP=H01' in initial.stdout
        run(['sh',q/'run_study.sh','status'],root,'initial_status.log',env);run(['sh',q/'run_study.sh','summary'],root,'initial_summary.log',env)
        summary=json.loads((q/'study_summary.json').read_text());assert summary['completed_steps']==0 and summary['crypto_return']=='PENDING_ACTUAL_BOARD_OUTPUTS'
        for command,log in [(['python3',q/'board_runner.py','detect'],'PC_detect_rejected.log'),(['sh',q/'build_board.sh'],'PC_build_rejected.log'),(['sh',q/'run_study.sh','host'],'PC_host_rejected.log'),(['sh',q/'run_study.sh','ablation'],'PC_ablation_rejected.log'),(['sh',q/'switch_fair_board.sh','v32_core_2_pipe','check'],'PC_switch_rejected.log')]:run(command,root,log,env,False)
        assert not (q/'study_runs').exists() and not (q/'.study.lock').exists(),'PC guard must reject before enrollment or locking'
        bad=dict(env,V32_BASE_PACKAGE=str(root/'missing_dependency'));run(['python3',q/'board_runner.py','check'],root,'wrong_dependency_rejected.log',bad,False)
        source=q/'study_tools.py';original=source.read_bytes();source.write_bytes(original+b'\n# simulated corruption\n');run(['python3',q/'board_runner.py','check'],root,'tampered_script_rejected.log',env,False);source.write_bytes(original)
        for f in q.glob('*.sh'):run(['sh','-n',f],root,'release_shell_'+f.name+'.log')
        run(['python3','-m','compileall','-q',q],root,'release_python_compileall.log')
        assert all(sha(q/n)==h for n,h in members.items())
    frozen={}
    for name in ('v32_hs4_20261027','v32_hostopt_20261029','v32_bo_20261029','v32_coreopt_20261029','v32_overlap_20261030'):
        folder=W/'board_packages'/name
        for line in (folder/'SHA256SUMS_PACKAGE').read_text().splitlines():h,n=line.split('  ',1);assert sha(folder/n)==h,(name,n)
        frozen[name]=sha(folder/'SHA256SUMS_PACKAGE')
    result=dict(status='PASS_SEALED_CAMPAIGN_ZIP_GIT_AND_CLI_GUARDS',files=len(members),package_bytes=sum((P/n).stat().st_size for n in members),manifest_sha256=members['SHA256SUMS_PACKAGE'],zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),all_four_image_bytes_and_host_sources_preserved=True,ZIP_and_parent_Git_autocrlf_checkout_byte_exact=True,initial_progress_zero_no_mock_results_shipped=True,PC_build_detect_run_and_switch_rejected=True,wrong_dependency_and_tampered_source_rejected=True,old_five_packages_unchanged=frozen,new_board_performance='PENDING',hardware_programmed=False)
    (R/'evidence/final_release.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
