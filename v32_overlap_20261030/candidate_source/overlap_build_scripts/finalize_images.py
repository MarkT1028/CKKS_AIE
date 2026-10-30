"""Bind actual physical inputs, boot UUIDs, test evidence and new source."""
from pathlib import Path
import hashlib,json,re,shutil
R=Path(__file__).resolve().parent;W=R.parents[1];P=R/'board_files';PREVIOUS=R.parent/'v32_coreopt_20261029'
BASE=Path('/home/mark/v32_aie_20261027/hardware/systems/v32_diag_2_pipe');CORE=Path('/home/mark/v32_coreopt_20261029/hardware/systems/v32_core_2_pipe')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
def main():
    names=('v32_aie_only_2_pipe','v32_reducer_only_2_pipe');hardware={n:json.loads((R/'evidence'/('hardware_'+n+'.json')).read_text()) for n in names}
    for name,h in hardware.items():
        assert h['status']=='PASS_PHYSICAL_ABLATION_BUILD';system=Path(h['build']);sign=json.loads((system/'postcheck_signoff.json').read_text())
        assert sign['setup_slack_ns']>=0 and sign['hold_slack_ns']>=0 and sign['drc_errors']==0
        assert re.search(r'# of nets with routing errors[.\s]*:\s*0\b',(system/'postcheck_route_status.rpt').read_text(),re.I)
        assert 'VIOLATED' not in (system/'postcheck_bus_skew.rpt').read_text()
        assert (system/'system.cfg').read_bytes()==(CORE/'system.cfg').read_bytes()==(BASE/'system.cfg').read_bytes()
        for n,x in h['inputs'].items():assert sha(system/n)==x['sha256']
        boot=system/'boot_candidate';manifest=json.loads((boot/'manifest.json').read_text());assert len(manifest['checks'])==5
        assert sha(boot/'boot0001.bin')==h['boot_sha256'] and sha(boot/'ckks_hw_boot.xclbin')==h['metadata_sha256']
        dst=P/'variants'/name;dst.mkdir(exist_ok=False)
        for n in ('boot0001.bin','ckks_hw_boot.xclbin','manifest.json'):shutil.copy2(boot/n,dst/n)
        (dst/'EXPECTED_BOOT_UUID').write_text(h['uuid']+'\n');(dst/'EXPECTED_BOOT_SHA256').write_text(h['boot_sha256']+'\n')
        ev=P/'offline_evidence'/name;ev.mkdir()
        for f in system.glob('postcheck*'):
            if f.suffix in ('.json','.rpt'):shutil.copy2(f,ev/f.name)
        shutil.copy2(system/'system.cfg',ev/'system.cfg');shutil.copy2(R/'evidence'/('hardware_'+name+'.json'),ev/'hardware_build.json')
    variants={}
    matrix={
        'v32_diag_2_pipe':(BASE/'libadf.a',BASE/'ct_reduce_accum.xo'),
        'v32_aie_only_2_pipe':(CORE/'libadf.a',BASE/'ct_reduce_accum.xo'),
        'v32_reducer_only_2_pipe':(BASE/'libadf.a',CORE/'ct_reduce_accum.xo'),
        'v32_core_2_pipe':(CORE/'libadf.a',CORE/'ct_reduce_accum.xo')}
    inputs={}
    for name,(aie,reducer) in matrix.items():
        dst=P/'variants'/name;metadata=dst/'ckks_hw_boot.xclbin';uuid=metadata.read_bytes()[416:432].hex();assert uuid==(dst/'EXPECTED_BOOT_UUID').read_text().strip()
        variants[name]=dict(uuid=uuid,boot_sha256=sha(dst/'boot0001.bin'),metadata_sha256=sha(metadata))
        inputs[name]=dict(aie_sha256=sha(aie),reducer_sha256=sha(reducer),reader_sha256=sha(CORE/'ct_reader.xo'),clock_config_sha256=sha(CORE/'system.cfg'),cores=2,PL_Hz=225000000,host_ablation_mode='map_pingpong')
    for name,h in hardware.items():
        assert h['inputs']['libadf.a']['sha256']==inputs[name]['aie_sha256'] and h['inputs']['ct_reduce_accum.xo']['sha256']==inputs[name]['reducer_sha256']
    assert len({v['uuid'] for v in variants.values()})==4
    put(P/'VARIANTS.json',variants);put(P/'SOURCE_MATRIX.json',inputs)
    frozen={f.relative_to(P).as_posix():sha(f) for f in (P/'reference').rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    assert (P/'common/replay.hpp').read_bytes()==(R/'reference/common/replay.hpp').read_bytes()
    assert (P/'reference/cpu/cached_cpu.cpp').read_bytes()==(W/'board_packages/v32_coreopt_20261029/reference/cpu/cached_cpu.cpp').read_bytes()
    put(P/'SOURCE_PROVENANCE.json',dict(frozen_reference_files=frozen,prior_core_package_manifest_sha256=sha(W/'board_packages/v32_coreopt_20261029/SHA256SUMS_PACKAGE'),base_manifest_sha256=sha(W/'board_packages/v32_hs4_20261027/SHA256SUMS_PACKAGE'),modified_units=['host/bo_host.cpp','common/finish_overlap.hpp','controlled tools'],CPU_arithmetic_source_unchanged=True,baseline_scheduler_unchanged=True,physical_matrix=inputs,physical_ablations=hardware,main_v32_source_sha256=sha(W/'v32_diag_inference.py')))
    assert sha(W/'v32_diag_inference.py')=='078db343138b5f51b018bf963c5aa638c0445b6e9bb6ec0c79713f6e565e8916'
    for n in ('aie_only_chain_rtl.json','aie_only_chain_rtl_cosim.rpt','reducer_only_chain_rtl.json','reducer_only_chain_rtl_cosim.rpt','model_compile.log','model_small.log','model_full_real.log','asan.log','tsan_noaslr.log','edge_zero.log','edge_max.log','edge_random.log','CPU_selftest.log','baseline_model.log','diagnostics_test.json','diagnostics_test.log'):
        shutil.copy2(R/'evidence'/n,P/'offline_evidence'/n)
    for n in names:
        stem='aie_only' if 'aie_only' in n else 'reducer_only';facts=json.loads((R/'evidence'/ (stem+'_chain_rtl.json')).read_text());assert facts['status']=='PASS_ABLATION_ACTUAL_AIE_TO_RANDOM_STALL_REDUCER_RTL'
        assert 'Pass' in (R/'evidence'/(stem+'_chain_rtl_cosim.rpt')).read_text()
    shutil.copytree(R/'build/edge_fixtures/max',P/'test_fixture_edge')
    doc=P/'START_HERE.md';doc.write_text(doc.read_text(encoding='utf-8').replace('v32_overlap_20261029','v32_overlap_20261030'),encoding='utf-8',newline='\n')
    scripts=P/'candidate_source/overlap_build_scripts';scripts.mkdir(exist_ok=True)
    for p in R.iterdir():
        if p.is_file() and p.suffix in ('.py','.sh'):shutil.copy2(p,scripts/p.name)
    print('ALL_FOUR_ACTUAL_IMAGES_BOUND',json.dumps(variants),flush=True)
if __name__=='__main__':main()
