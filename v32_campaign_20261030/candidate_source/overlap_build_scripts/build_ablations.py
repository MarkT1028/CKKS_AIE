"""Local physical builds of the two missing 2x2 cells. No board access."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess,time
R=Path(__file__).resolve().parent;W=R.parents[1]
B=Path('/home/mark/v32_overlap_20261029/hardware')
CORE=Path('/home/mark/v32_coreopt_20261029/hardware/systems/v32_core_2_pipe')
BASE=Path('/home/mark/v32_aie_20261027/hardware/systems/v32_diag_2_pipe')
OLD=W/'experiments/ckks_perf2_20261017'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,cwd,log):
    print('START',cwd.name,log,flush=True)
    with (cwd/log).open('w') as f:subprocess.run([str(x) for x in args],cwd=cwd,stdout=f,stderr=subprocess.STDOUT,check=True)
    print('PASS',cwd.name,log,flush=True)
def build(name,aie,reducer):
    out=B/'systems'/name;out.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    files={'base.xsa':CORE/'base.xsa','ct_reader.xo':CORE/'ct_reader.xo','ct_reduce_accum.xo':reducer,'libadf.a':aie}
    inputs={}
    for key,p in files.items():
        q=out/key
        if q.exists():assert sha(q)==sha(p),'Existing build input mismatch'
        else:shutil.copy2(p,q)
        inputs[key]=dict(source=str(p),sha256=sha(p))
    cfg=(CORE/'system.cfg').read_text();assert '225000000' in cfg and 'synth.jobs=1' in cfg and 'impl.jobs=1' in cfg
    (out/'system.cfg').write_text(cfg)
    if not (out/'ckks_hw.xsa').exists():
        stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S');log='link_'+stamp+'.log'
        run(['v++','--link','--target','hw','--save-temps','--platform','base.xsa','--config','system.cfg','--remote_ip_cache',B/'ip_cache','--temp_dir','_x_'+stamp,'-o','ckks_hw.xsa','ct_reader.xo','ct_reduce_accum.xo','libadf.a'],out,log)
        (out/'successful_link.txt').write_text(log)
    if not (out/'postcheck_signoff.json').exists():
        dcps=list(out.glob('_x_*/link/vivado/vpl/prj/prj.runs/impl_1/*_routed.dcp'));assert dcps
        run(['/home/mark/AMDDesignTools/2025.2/Vivado/bin/vivado','-mode','batch','-source',OLD/'postcheck.tcl','-tclargs',max(dcps,key=lambda x:x.stat().st_mtime),out],out,'postcheck.log')
    assert 'All user specified timing constraints are met.' in (out/'postcheck_timing_summary.rpt').read_text()
    runtime=out/'runtime';runtime.mkdir(exist_ok=True)
    if not (runtime/'packaged.xclbin').exists():
        run(['v++','--package','--target','hw','--platform',out/'base.xsa','--advanced.param','software.os=standalone','--package.defer_aie_run','--package.out_dir','packaged',out/'libadf.a',out/'ckks_hw.xsa','-o','packaged.xclbin'],runtime,'package.log')
    boot=out/'boot_candidate'
    if not (boot/'manifest.json').exists():
        run(['python3',OLD/'baseline/scripts/build_boot_candidate.py','/mnt/e/vek280_AIe_ckks/board_snapshot/20261008',runtime,boot],out,'boot.log')
    m=json.loads((boot/'manifest.json').read_text());meta=boot/'ckks_hw_boot.xclbin';uuid=meta.read_bytes()[416:432].hex()
    assert sha(boot/'boot0001.bin')==m['candidate_sha256'] and sha(meta)==m['metadata_sha256']
    facts=dict(status='PASS_PHYSICAL_ABLATION_BUILD',variant=name,build=str(out),inputs=inputs,uuid=uuid,boot_sha256=sha(boot/'boot0001.bin'),metadata_sha256=sha(meta),elapsed_seconds=time.monotonic()-start,board_tested=False,board_performance='PENDING')
    (R/'evidence'/('hardware_'+name+'.json')).write_text(json.dumps(facts,indent=2)+'\n')
    print('ABLATION_IMAGE_READY',name,uuid,flush=True)
def main():
    build('v32_aie_only_2_pipe',CORE/'libadf.a',BASE/'ct_reduce_accum.xo')
    build('v32_reducer_only_2_pipe',BASE/'libadf.a',CORE/'ct_reduce_accum.xo')
if __name__=='__main__':main()
