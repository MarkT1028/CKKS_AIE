from pathlib import Path
import hashlib,json,shutil,subprocess,time
R=Path(__file__).resolve().parent;W=R.parents[1];B=Path('/home/mark/ga3_splitbo_20261109/hardware/splitbo_r1');E=R/'evidence'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,cwd,name):
 print('START',name,flush=True)
 with (cwd/name).open('w') as log:subprocess.run(list(map(str,args)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True)
 print('PASS',name,flush=True)
assert not B.exists();B.mkdir(parents=True)
base=Path('/home/mark/v32_coreopt_20261029/hardware/systems/v32_core_2_pipe/base.xsa');assert base.is_file();sources=[base]
reader=json.loads((E/'ct_reader.json').read_text());rp=Path(reader['build'])/'ct_reader.xo';assert sha(rp)==reader['xo_sha256'];sources.append(rp)
reduce=json.loads((W/'integration/ga3_pipeline_20261109/hls_evidence/ct_reduce_accum.json').read_text());qp=Path(reduce['build'])/'ct_reduce_accum.xo';assert sha(qp)==reduce['xo_sha256'];sources.append(qp)
assert sha(R/'design/native_reduce.cpp')==reduce['source']['native_reduce.cpp']
for p in sources:shutil.copyfile(p,B/p.name)
cfg='[connectivity]\nnk=ct_reader:2:ct_reader_1.ct_reader_2\nnk=ct_reduce_accum:2:ct_reduce_accum_1.ct_reduce_accum_2\n'
for i in (1,2):cfg+=f'stream_connect=ct_reader_{i}.products:ct_reduce_accum_{i}.products\nsp=ct_reader_{i}.weights:DDR0\nsp=ct_reader_{i}.baby:DDR0\nsp=ct_reduce_accum_{i}.outputs:DDR0\nsp=ct_reduce_accum_{i}.params:DDR0\n'
cfg+='[clock]\n'+''.join(f'freqHz=225000000:{name}_{i}.ap_clk\n' for i in (1,2) for name in ('ct_reader','ct_reduce_accum'))+'[vivado]\nsynth.jobs=1\nimpl.jobs=1\nparam=general.maxThreads=2\nprop=run.impl_1.strategy=Performance_Explore\n'
(B/'system.cfg').write_text(cfg)
run(['v++','--link','--target','hw','--save-temps','--platform','base.xsa','--config','system.cfg','--remote_ip_cache',B.parent/'ip_cache','--temp_dir','_x_split','-o','ckks_hw.xsa','ct_reader.xo','ct_reduce_accum.xo'],B,'link_hw.log')
dcps=list(B.glob('_x_split/link/vivado/vpl/prj/prj.runs/impl_1/*_routed.dcp'));assert len(dcps)==1
run(['/home/mark/AMDDesignTools/2025.2/Vivado/bin/vivado','-mode','batch','-source',W/'experiments/ckks_perf2_20261017/postcheck.tcl','-tclargs',dcps[0],B],B,'postcheck.log')
sign=json.loads((B/'postcheck_signoff.json').read_text());assert sign['setup_slack_ns']>=0 and sign['hold_slack_ns']>=0 and sign['drc_errors']==0
runtime=B/'runtime';runtime.mkdir();run(['v++','--package','--target','hw','--platform',B/'base.xsa','--advanced.param','software.os=standalone','--package.out_dir','packaged',B/'ckks_hw.xsa','-o','packaged.xclbin'],runtime,'package.log')
boot=B/'boot_candidate';run(['python3',W/'experiments/ckks_perf2_20261017/baseline/scripts/build_boot_candidate.py','/mnt/e/vek280_AIe_ckks/board_snapshot/20261008',runtime,boot],B,'boot.log')
run(['/home/mark/AMDDesignTools/2025.2/Vitis/bin/xclbinutil','--input',boot/'ckks_hw_boot.xclbin','--info'],B,'split_xclbin_info.txt')
result=dict(status='PASS_SPLIT_BO_ROUTED_TIMING_DRC_BOOT_PENDING_BOARD',build=str(B),inputs={p.name:sha(p) for p in sources},boot_manifest=json.loads((boot/'manifest.json').read_text()),PL_kernel_MHz=225,lanes=2,AIE_compute_tiles=0,source={p.name:sha(p) for p in (R/'design').iterdir()},scope='Canonical separate A/B BO inputs, shared read-only across two lanes; unchanged exact128 lazy8 reducer. Board speed pending.')
(E/'hardware.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],flush=True)
