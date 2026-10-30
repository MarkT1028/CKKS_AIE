"""Local-only physical implementation; never programs a board or modifies SD."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parent;W=R.parents[1]
B=Path('/home/mark/v32_coreopt_20261029/hardware')
OLD=W/'experiments/ckks_perf2_20261017'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,cwd,log):
    print('START',log,flush=True)
    with (cwd/log).open('w') as f:subprocess.run(list(map(str,args)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT,check=True)
    print('PASS',log,flush=True)
def main():
    system=B/'systems/v32_core_2_pipe';system.mkdir(parents=True,exist_ok=True)
    inherited=Path('/home/mark/v32_aie_20261027/hardware/systems/v32_diag_2_pipe')
    files=[inherited/'base.xsa',inherited/'ct_reader.xo',Path('/home/mark/v32_coreopt_20261029/hls/reducer_forward/ct_reduce_accum.xo'),Path('/home/mark/v32_coreopt_20261029/aie/static_real/hw/libadf.a')]
    provenance={}
    for p in files:
        dest=system/p.name
        if dest.exists():assert sha(dest)==sha(p),'build input changed; create fresh candidate'
        else:shutil.copy2(p,dest)
        provenance[p.name]=dict(source=str(p),sha256=sha(p))
    cfg=(inherited/'system.cfg').read_text();(system/'system.cfg').write_text(cfg)
    assert '225000000' in cfg and 'synth.jobs=1' in cfg and 'impl.jobs=1' in cfg
    if not (system/'ckks_hw.xsa').exists():
        stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S');log=f'link_hw_{stamp}.log'
        run(['v++','--link','--target','hw','--save-temps','--platform','base.xsa','--config','system.cfg','--remote_ip_cache',B/'ip_cache','--temp_dir',f'_x_hw_{stamp}','-o','ckks_hw.xsa','ct_reader.xo','ct_reduce_accum.xo','libadf.a'],system,log)
        (system/'successful_link.txt').write_text(log)
    if not (system/'postcheck_signoff.json').exists():
        checkpoints=list(system.glob('_x_hw*/link/vivado/vpl/prj/prj.runs/impl_1/*_routed.dcp'))
        assert checkpoints,'actual routed checkpoint required'
        run(['/home/mark/AMDDesignTools/2025.2/Vivado/bin/vivado','-mode','batch','-source',OLD/'postcheck.tcl','-tclargs',max(checkpoints,key=lambda p:p.stat().st_mtime),system],system,'postcheck.log')
    assert 'All user specified timing constraints are met.' in (system/'postcheck_timing_summary.rpt').read_text()
    runtime=system/'runtime';runtime.mkdir(exist_ok=True)
    if not (runtime/'packaged.xclbin').exists():
        run(['v++','--package','--target','hw','--platform',system/'base.xsa','--advanced.param','software.os=standalone','--package.defer_aie_run','--package.out_dir','packaged',system/'libadf.a',system/'ckks_hw.xsa','-o','packaged.xclbin'],runtime,'package.log')
    boot=system/'boot_candidate'
    if not (boot/'manifest.json').exists():run(['python3',OLD/'baseline/scripts/build_boot_candidate.py','/mnt/e/vek280_AIe_ckks/board_snapshot/20261008',runtime,boot],system,'boot.log')
    result=dict(status='PHYSICAL_CANDIDATE_READY_PENDING_ALL_OFFLINE_GATES',architecture='2 AIE compile-time exact diagonal kernels + forwarding reducer; inherited reader and 225MHz clocks',build=str(system),inputs=provenance,boot_manifest=json.loads((boot/'manifest.json').read_text()),board_performance='PENDING')
    (R/'evidence/hardware_build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],flush=True)
if __name__=='__main__':main()
