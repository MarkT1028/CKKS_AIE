from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,time,sys
R=Path(__file__).resolve().parent;W=R.parents[1];OLD=W/'experiments/ckks_perf2_20261017';B=Path('/home/mark/v32_coreopt_20261029/aie')
sys.path.insert(0,str(W/'integration/v32_aie_20261027'))
spec=importlib.util.spec_from_file_location('real_vectors',W/'integration/v32_aie_20261027/aie_checks.py');vectors=importlib.util.module_from_spec(spec);spec.loader.exec_module(vectors)
def run(args,cwd,log):
    with (cwd/log).open('w') as f:subprocess.run(list(map(str,args)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT,check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('variant',choices=['baseline','static']);p.add_argument('--case',choices=['real','edges','limbmax'],default='real');a=p.parse_args()
    out=B/(a.variant+'_'+a.case);out.mkdir(parents=True,exist_ok=False)
    src=R/'reference/aie' if a.variant=='baseline' else R/'aie'
    # Same actual endpoint positions, all 14 towers and all 16 pairs for BOTH targets.
    if a.case=='limbmax':
        data=out/'data';data.mkdir()
        for lane in range(2):
            patterns=[([32767]*256,[32767]*256),([0]*256,[32767]*256),([1]*256,[1]*256),([32767 if i%2 else 0 for i in range(256)],[32767]*256)]
            with (data/f'left{lane}.txt').open('w') as lf,(data/f'right{lane}.txt').open('w') as rf,(data/f'expected{lane}.txt').open('w') as ef:
                for left,right in patterns:
                    for f,values in ((lf,left),(rf,right)):
                        for j in range(0,256,8):f.write(' '.join(map(str,values[j:j+8]))+'\n')
                    for d in range(7):
                        pp=[sum(left[r*64+j]*right[(d-r)*64+j] for r in range(4) if 0<=d-r<4) for j in range(64)]
                        for j in range(0,64,4):ef.write(' '.join(map(str,pp[j:j+4]))+'\n')
        meta=dict(provenance=dict(type='AIE unit input limbs: all 32767, zero, one, alternating; max exact diagonal 4294705156 exceeds INT32_MAX; no claim this artificial full word is a canonical residue'),n=128,l=1,k=1,cores=2,compact=True,frames_per_core=4,expected_samples_per_core=1792)
        (data/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    else:
        meta=vectors.vectors(out/'data',W/'board_packages/v32_hs4_20261027/fixture' if a.case=='real' else None)
    results=[];started=time.monotonic()
    for target in ('x86sim','hw'):
        cwd=out/target;cwd.mkdir();shutil.copytree(out/'data',cwd/'data')
        run(['v++','-c','--mode','aie','--target',target,'--part','xcve2802-vsvh1760-2MP-e-S','--config',src/'aie.cfg','--work_dir','Work','-I',src,'--aie.Xpreproc',f'-DPERF_AIE_CORES=2 -DPERF_COMPACT=1 -DPERF_FRAMES={meta["frames_per_core"]}',src/'graph.cpp'],cwd,'compile.log')
        run(['x86simulator' if target=='x86sim' else 'aiesimulator','--pkg-dir=Work'],cwd,'simulate.log')
        actual=cwd/('x86simulator_output/data' if target=='x86sim' else 'aiesimulator_output/data')
        run(['python3',OLD/'vectors.py','compare','data','--cores','2','--actual',actual],cwd,'compare.log')
        verification=json.loads((actual.parent/'verification.json').read_text());verification.update(vector_metadata=meta,variant=a.variant,target=target,board_performance='NOT_MEASURED')
        (R/'evidence'/f'aie_{a.variant}_{a.case}_{target}.json').write_text(json.dumps(verification,indent=2)+'\n')
        results.append(verification);print('PASS_AIE',a.variant,a.case,target,flush=True)
    facts=dict(status='PASS_ACTUAL_AIE_X86_AND_CYCLE_SIM',variant=a.variant,case=a.case,source_sha256=hashlib.sha256((src/'limb_diag.cpp').read_bytes()).hexdigest(),libadf_sha256=hashlib.sha256((out/'hw/libadf.a').read_bytes()).hexdigest(),build=str(out),elapsed_seconds=time.monotonic()-started,results=results,board_performance='PENDING')
    (R/'evidence'/f'aie_{a.variant}_{a.case}.json').write_text(json.dumps(facts,indent=2)+'\n')
if __name__=='__main__':main()
