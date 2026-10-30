"""Check exact frozen release, Git/ZIP transport, native guards and XRT syntax."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile,zipfile
R=Path(__file__).resolve().parent;W=R.parents[1];P=W/'board_packages/v32_overlap_20261030';BASE=W/'board_packages/v32_hs4_20261027'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,cwd,log,env=None,good=True):
    result=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,env=env)
    (R/'evidence'/log).write_text(result.stdout+result.stderr)
    assert (result.returncode==0)==good,(args,result.returncode,result.stdout[-1800:],result.stderr[-1800:])
def main():
    inventory={n:h for h,n in (line.split('  ',1) for line in (P/'SHA256SUMS_PACKAGE').read_text().splitlines())};inventory['SHA256SUMS_PACKAGE']=sha(P/'SHA256SUMS_PACKAGE')
    assert all(sha(P/n)==h for n,h in inventory.items())
    env=dict(os.environ,V32_BASE_PACKAGE=str(BASE),PYTHONDONTWRITEBYTECODE='1')
    archive=P.with_suffix('.zip');assert not archive.exists()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n in sorted(inventory):z.write(P/n,P.name+'/'+n)
    with tempfile.TemporaryDirectory(prefix='overlap-transport-') as t:
        root=Path(t);extracted=root/'zip';extracted.mkdir()
        with zipfile.ZipFile(archive) as z:
            assert len(z.infolist())==len(inventory)
            for info in z.infolist():
                path=Path(info.filename);assert not path.is_absolute() and '..' not in path.parts and path.parts[0]==P.name
                target=extracted/path;target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
        assert all(sha(extracted/P.name/n)==h for n,h in inventory.items())
        run(['python3',extracted/P.name/'board_runner.py','check'],extracted,'zip_check.log',env)
        repo=root/'repo';repo.mkdir();parent=Path('/mnt/e/vek280_AIe_ckks/AIE_git')
        for n in ('.gitattributes','.gitignore'):shutil.copy2(parent/n,repo/n)
        shutil.copytree(P,repo/P.name)
        run(['git','init','-q','--initial-branch=codex/overlap-transport'],repo,'transport_git_init.log')
        run(['git','-c','core.autocrlf=true','add','.'],repo,'transport_git_add.log')
        run(['git','-c','user.name=Offline Transport Test','-c','user.email=codex@localhost','-c','commit.gpgsign=false','commit','-qm','Test core candidate transport'],repo,'transport_git_commit.log')
        checkout=root/'checkout';run(['git','-c','core.autocrlf=true','clone','-q',repo,checkout],root,'transport_git_clone.log')
        assert all((checkout/P.name/n).is_file() and sha(checkout/P.name/n)==h for n,h in inventory.items()),'ignored or changed release file after checkout'
        q=checkout/P.name;run(['python3',q/'board_runner.py','check'],checkout,'checkout_check.log',env)
        headers=W/'experiments/ckks_perf2_20261017/host_api_headers'
        for variant in ('v32_diag_2_pipe','v32_aie_only_2_pipe','v32_reducer_only_2_pipe','v32_core_2_pipe'):
            source=q/('variants/'+variant+'/host/bo_host.cpp')
            exe=root/('host_'+variant)
            run(['g++','-O3','-std=c++17','-pthread','-DCKKSMAC_PARSER_ONLY',source,'-o',exe],root,variant+'_parser_compile.log')
            run([exe,'--check-data',BASE/'fixture'],root,variant+'_full_real_split.log')
            run(['g++','-std=c++17','-pthread','-DDISABLE_ABI_CHECK','-I'+str(headers),'-fsyntax-only',source],root,variant+'_official_XRT_syntax.log')
            # Exercise the exact matching-header and DT marker guard independently.
            wrapper=root/(variant+'_metadata.cpp');perf=q/('variants/'+variant+'/host/perf_host.cpp')
            wrapper.write_text('#define CKKSMAC_PARSER_ONLY\n#define PERF_HOST_NO_MAIN\n#include "'+str(perf)+'"\nint main(int argc,char**argv){try{require(argc==3,"args");validate_boot_xclbin(argv[1]);validate_boot_marker(argv[2]);return 0;}catch(const std::exception&e){std::cerr<<e.what();return 1;}}\n')
            exe=root/(variant+'_metadata');run(['g++','-O2','-std=c++17','-pthread',wrapper,'-o',exe],root,variant+'_metadata_compile.log')
            uuid=(q/'variants'/variant/'EXPECTED_BOOT_UUID').read_text().strip();marker=root/'marker';marker.write_bytes(uuid.encode()+b'\0')
            metadata=q/'variants'/variant/'ckks_hw_boot.xclbin';run([exe,metadata,marker],root,variant+'_metadata_guard_PASS.log')
            other='v32_core_2_pipe' if variant=='v32_diag_2_pipe' else 'v32_diag_2_pipe';run([exe,q/'variants'/other/'ckks_hw_boot.xclbin',marker],root,variant+'_wrong_metadata_rejected.log',good=False)
            marker.write_bytes(b'0'*32+b'\0');run([exe,metadata,marker],root,variant+'_wrong_marker_rejected.log',good=False)
        run(['g++','-O3','-std=c++17','-pthread',q/'reference/cpu/cached_cpu.cpp','-o',root/'cpu'],root,'release_cpu_compile.log')
        run([root/'cpu','--self-test'],root,'release_cpu_selftest.log')
        run(['g++','-O3','-std=c++17','-pthread',q/'tests/fake_backend.cpp','-o',root/'schedule'],root,'release_schedule_compile.log')
        run([root/'schedule',q/'test_fixture',root/'schedule_results'],root,'release_schedule_selftest.log')
        run(['g++','-O3','-std=c++17','-pthread',q/'tests/finish_overlap_test.cpp','-o',root/'finish_schedule'],root,'release_finish_compile.log')
        run([root/'finish_schedule',q/'test_fixture',root/'finish_results'],root,'release_finish_schedule.log')
        run([root/'finish_schedule',q/'test_fixture_edge',root/'finish_edge_results'],root,'release_finish_edge.log')
        run(['python3',q/'board_runner.py','detect'],root,'PC_detect_rejected.log',env,False)
        run(['sh',q/'build_board.sh'],root,'PC_build_rejected.log',env,False)
        run(['sh',q/'switch_fair_board.sh','v32_core_2_pipe','check'],root,'PC_switch_rejected.log',env,False)
        for f in q.glob('*.sh'):run(['sh','-n',f],root,'shell_'+f.name+'.log')
    facts=dict(status='PASS_FINAL_OVERLAP_TRANSPORT_AND_RELEASE',files=len(inventory),package_bytes=sum((P/n).stat().st_size for n in inventory),manifest_sha256=inventory['SHA256SUMS_PACKAGE'],zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),ZIP_and_parent_Git_autocrlf_inventory_byte_exact=True,all_four_release_hosts_full_fixture_split_merge=True,all_four_release_hosts_official_XRT_syntax=True,all_four_matching_metadata_and_boot_guards=True,wrong_metadata_and_boot_markers_rejected=True,release_CPU_and_scheduler_selftests=True,PC_build_detect_and_switch_rejected=True,user_git_staging_unchanged=True,hardware_programmed=False,board_tested=False)
    (R/'evidence/final_transport.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps(facts,indent=2))
if __name__=='__main__':main()
