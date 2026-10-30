"""Run the actual step coordinator against fake board/run functions, no XRT."""
from pathlib import Path
import hashlib,importlib.util,json,sys,tempfile
R=Path(__file__).resolve().parent;P=R/'board_files';sys.path.insert(0,str(P))
import board_runner as r
import study as d
import study_tools as t
import summarize_results as s
spec=importlib.util.spec_from_file_location('study_mocks',R/'test_study.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def main():
    saved=(r.ROOT,r.base,r.check,r.board,r.environment,r.run,d.R,t.R,d.diag.main)
    calls=[];diag_calls=[];variant=t.CORE;boot=m.boot(1);fail_formal=False
    with tempfile.TemporaryDirectory(prefix='research-driver-') as tmp:
        root=Path(tmp);base=root/'base';(base/'fixture/chunks').mkdir(parents=True);(root/'bin').mkdir();(root/'SHA256SUMS_PACKAGE').write_text('offline mock package');(root/'STUDY_PROTOCOL.json').write_bytes((P/'STUDY_PROTOCOL.json').read_bytes());pin=r.records.sha(root/'SHA256SUMS_PACKAGE')
        for i in range(16):(base/'fixture/chunks'/f'chunk_{i}_expected.bin').write_bytes(b'MOCK_ONLY'+bytes([i]))
        for name in r.BINARIES:(root/'bin'/name).write_bytes(('offline_fake_'+name).encode())
        build=dict(package_manifest_sha256=pin,base_manifest_sha256=r.BASE_MANIFEST,architecture='aarch64',flags='-O3 -std=c++17 -pthread; host additionally -I/usr/include/xrt -lxrt_coreutil',compiler='SYNTHETIC_DRIVER_COMPILER',binaries={n:r.records.sha(root/'bin'/n) for n in r.BINARIES});m.put(root/'bin/build_identity.json',build)
        def env():return dict(boot_id=boot,boot_uuid=r.VARIANTS[variant]['uuid'])
        def run(kind,v,reverse=False,campaign='host',study_context=None):
            assert r._DEVICE_LOCK is not None,'device lock must span entire coordinator step'
            calls.append((kind,v,reverse,campaign,study_context['step_id']))
            if fail_formal and kind=='formal':raise RuntimeError('synthetic formal interruption')
            folder=root/f'results_overlap_{campaign}_mock_{len(calls):03}';m.h.mock_result(folder,camp=campaign,variant=v,boot=boot,reverse=reverse);rid=t.load(folder/'run_identity.json');rid.update(manifest_sha256=pin,profiling=False,study_context=study_context,build_identity=build,reverse_order=reverse,mode=kind);m.put(folder/'run_identity.json',rid)
            for mode in rid['order']:
                q=folder/mode/'hardware/setup.json';x=t.load(q);x['setup_ms']=3.;m.put(q,x)
            if kind=='smoke':m.convert_smoke(folder)
            s.summarize(folder);return folder
        def diagnostic(perf=False):
            assert r._DEVICE_LOCK is not None and perf is False
            diag_calls.append(boot);folder=root/f'results_cpu_diag_mock_{len(diag_calls):03}'
            m.put(folder/'status.json',dict(status='PASS_CPU_DIAGNOSTIC',measured=12,all_formal_compute_samples_ms=[100.]*12,compute_first6_median_ms=100.,compute_last6_median_ms=100.,drift_percent=0.,review=False));m.put(folder/'identity.json',dict(diagnostic_only=True,perf_requested=False,boot_id=boot,cpu_sha256=build['binaries']['cached_cpu'],manifest_sha256=pin))
            for n in ('environment_before.json','environment_after.json'):m.put(folder/n,env())
            return folder
        try:
            r.ROOT=d.R=t.R=root;r.base=lambda:base;r.check=lambda:dict(manifest_sha256=pin);r.board=lambda:None;r.environment=env;r.run=run;d.diag.main=diagnostic
            d.run_step('host');assert t.summarize()['completed_steps']==1 and (root/'study_summary.csv').is_file()
            n=len(calls);m.reject(lambda:d.run_step('host'));assert len(calls)==n
            boot=m.boot(2);d.run_step('host');assert [x[2] for x in calls[-3:]]==[False,True,False]
            boot=m.boot(3);fail_formal=True;m.reject(lambda:d.run_step('host'));assert t.summarize()['completed_steps']==2 and len(t.summarize()['failed_attempts'])==1
            fail_formal=False;d.run_step('host');out=t.summarize();assert out['host_repeatability']['completed'] and out['review_required']
            n=len(calls);m.reject(lambda:d.run_step('host'));assert len(calls)==n
            variant=t.AIE;m.reject(lambda:d.run_step('ablation'));assert len(calls)==n
            variant=t.CORE;d.run_step('ablation');assert t.summarize()['completed_ablation_steps']==1 and len(diag_calls)==3
            variant=t.AIE;n=len(calls);m.reject(lambda:d.run_step('ablation'));assert len(calls)==n
            boot=m.boot(4);d.run_step('ablation');assert t.summarize()['completed_ablation_steps']==2 and all(x[3]=='ablation' for x in calls[-3:])
            assert r._DEVICE_LOCK is None
        finally:r.ROOT,r.base,r.check,r.board,r.environment,r.run,d.R,t.R,d.diag.main=saved
    result=dict(status='PASS_ACTUAL_COORDINATOR_WITH_SYNTHETIC_BACKEND',three_independent_host_boots=True,H02_reverse_formal_order=True,whole_step_lock_held_across_calls=True,same_boot_rejected_before_hardware=True,wrong_phase_and_variant_rejected_before_hardware=True,failed_partial_step_retained_and_retry_allowed=True,A01_reuses_H03_boot_but_A02_requires_new_boot=True,CPU_diagnostics_host_only=True,summary_JSON_CSV_generated=True,hardware_executed=False,boot_files_or_registers_changed=False)
    (R/'evidence/driver_test.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
