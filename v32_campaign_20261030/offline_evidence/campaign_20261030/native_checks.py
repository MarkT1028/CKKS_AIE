from pathlib import Path
import hashlib,json,subprocess,tempfile
R=Path(__file__).resolve().parent;W=R.parents[1];P=R/'board_files';OLD=W/'board_packages/v32_overlap_20261030';BASE=W/'board_packages/v32_hs4_20261027'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,log,good=True):
    p=subprocess.run(list(map(str,args)),capture_output=True,text=True);(R/'evidence'/log).write_text(p.stdout+p.stderr);assert (p.returncode==0)==good,(args,p.returncode,p.stderr[-1800:])
def main():
    counts={}
    for folder in ('host','common','reference','tests','variants'):
        files=[p for p in (OLD/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts];assert all(sha(p)==sha(P/p.relative_to(OLD)) for p in files);counts[folder]=len(files)
    with tempfile.TemporaryDirectory(prefix='campaign-native-') as tmp:
        root=Path(tmp);headers=W/'experiments/ckks_perf2_20261017/host_api_headers'
        for v in json.loads((P/'VARIANTS.json').read_text()):
            source=P/'variants'/v/'host/bo_host.cpp';exe=root/v
            run(['g++','-O3','-std=c++17','-pthread','-DCKKSMAC_PARSER_ONLY',source,'-o',exe],v+'_parser_compile.log')
            run([exe,'--check-data',BASE/'fixture'],v+'_full_real_split_merge.log')
            run(['g++','-std=c++17','-pthread','-DDISABLE_ABI_CHECK','-I'+str(headers),'-fsyntax-only',source],v+'_official_XRT_syntax.log')
        run(['g++','-O3','-std=c++17','-pthread',P/'reference/cpu/cached_cpu.cpp','-o',root/'cpu'],'CPU_compile.log');run([root/'cpu','--self-test'],'CPU_selftest.log')
        for source,name in [('fake_backend.cpp','baseline'),('finish_overlap_test.cpp','overlap')]:
            run(['g++','-O2','-std=c++17','-pthread',P/'tests'/source,'-o',root/name],name+'_compile.log');run([root/name,P/'test_fixture',root/(name+'_out')],name+'_model.log')
            if name=='overlap':run([root/name,P/'test_fixture_edge',root/'edge_out'],'edge_model.log')
        run(['g++','-O1','-g','-std=c++17','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',P/'tests/finish_overlap_test.cpp','-o',root/'sanitize'],'ASAN_UBSAN_compile.log')
        run([root/'sanitize',P/'test_fixture',root/'asan_out'],'ASAN_UBSAN_run.log')
        for f in P.glob('*.sh'):run(['sh','-n',f],'shell_'+f.name+'.log')
        run(['python3','-m','compileall','-q',P],'python_compileall.log')
    out=dict(status='PASS_UNCHANGED_ARITHMETIC_AND_NATIVE_HOST_CHECKS',unchanged_source_file_counts=counts,all_four_host_full_16_chunk_split_merge=True,all_four_official_XRT_header_syntax=True,reused_CPU_selftest=True,reused_baseline_overlap_and_edge_model=True,address_and_undefined_sanitizers=True,shell_and_Python_syntax=True,firmware_rebuilt=False,hardware_executed=False,new_performance='PENDING')
    (R/'evidence/native_checks.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
