from pathlib import Path
import hashlib,json,os,shutil,struct,subprocess,time
R=Path(__file__).resolve().parents[1];W=R.parents[1];K=W/'board_packages/v32_ga3_20261104';DATA=Path('/mnt/d/CodexBuilds/v32_ga3_20261104/public_data_v2')
def main():
    out=R/'build'/('loader_'+str(time.time_ns()));out.mkdir();binary=out/'model';asan=out/'asan';reports=[]
    def call(cmd,good=True,timeout=900):
        p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=timeout);reports.append(dict(command=list(map(str,cmd)),returncode=p.returncode,stdout=p.stdout[-3000:],stderr=p.stderr[-3000:]));assert (p.returncode==0)==good,(cmd,p.stdout,p.stderr);return p
    flags=['-std=c++17','-pthread','-DWINDOW_SOFTWARE_MODEL']
    call(['g++','-O2',*flags,K/'host/ga3_host.cpp','-o',binary])
    for t in (0,16,32,48):
        for kind,sub,name in [(3,'weights',f'r{t}_c0_g3.bin'),(4,'baby',f'r{t}_c0_o00.bin'),(2,'gold',f'r{t}_c0_o00_g3.bin')]:call([binary,'--check-record',DATA/sub/name,kind])
    call([binary,'unused',DATA,out/'real_smoke','smoke',2,1,'descending',2])
    call(['g++','-O1','-g',*flags,'-fsanitize=address,undefined','-fno-omit-frame-pointer',K/'host/ga3_host.cpp','-o',asan])
    call([asan,'unused',DATA,out/'real_asan_smoke','smoke',1,0,'ascending',2])
    previous=(R/'build/latest_host_tests.txt').read_text().strip();synthetic=Path(previous)/'data_pilot';mutant=out/'invalid_canonical';shutil.copytree(synthetic,mutant,copy_function=os.link)
    p=mutant/'record_3_16.bin';data=bytearray(p.read_bytes());q=struct.unpack_from('<Q',data,64)[0];struct.pack_into('<Q',data,64+24*16,q);p.unlink();p.write_bytes(data)
    failure=call([binary,'unused',mutant,out/'invalid_output','smoke',1,0,'descending',2],False);assert 'noncanonical bulk source' in failure.stderr
    headers=W/'experiments/ckks_perf2_20261017/host_api_headers'
    for name,extra in [('aie',[]),('native',['-DWINDOW_PURE_PL','-DWINDOW_NATIVE_PL'])]:
        obj=out/(name+'.o');call(['g++','-O2','-std=c++17','-pthread','-DDISABLE_ABI_CHECK','-I'+str(headers),*extra,'-c',K/'host/ga3_host.cpp','-o',obj]);symbols=call(['nm','-u',obj]).stdout
        if name=='native':assert 'xrt5graph' not in symbols and 'xrt::graph' not in symbols,'pure PL references graph runtime'
    result=dict(status='PASS_REAL_BULK_LOADER_EQUIVALENCE_ASAN_UBSAN_ABI',test_path=str(out),real_records_checked=12,all_RNS_batches=True,board_executed=False,reports=reports,source_sha256={p.relative_to(K).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [K/'host/ga3_host.cpp',K/'host/ga3_xrt.hpp',K/'common/record.hpp',K/'common/ga3_source.hpp']})
    (R/'build/loader_validation.json').write_text(json.dumps(result,indent=2)+'\n');(R/'build/latest_loader_path.txt').write_text(str(out)+'\n');print(result['status'])
if __name__=='__main__':main()
