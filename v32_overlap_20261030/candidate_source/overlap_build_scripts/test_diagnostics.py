"""Exercise CPU diagnostic orchestration using a tiny fake child process."""
from pathlib import Path
import hashlib,json,os,sys,tempfile
R=Path(__file__).resolve().parent;P=R/'board_files';sys.path.insert(0,str(P))
import board_runner as r
import cpu_diagnostics as d
def main():
    samples=d.task_sample(os.getpid());assert any(x['tid']==os.getpid() and x['user_ticks']>=0 and x['last_cpu']>=0 for x in samples)
    saved=(d.R,r.check,r.board,r.base,r.environment);which=d.shutil.which;affinity=os.sched_getaffinity(0)
    try:
        with tempfile.TemporaryDirectory(prefix='overlap-cpu-diag-') as t:
            root=Path(t);(root/'bin').mkdir();base=root/'base';base.mkdir();cpu=root/'bin/cached_cpu'
            cpu.write_text('''#!/usr/bin/env python3
import csv,pathlib,sys,time
assert sys.argv[-4:]==['12','2','2','nosave']
root=pathlib.Path(sys.argv[2]);root.mkdir()
with (root/'iterations.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['repetition','warmup','compute_sum_ms'])
 for i in range(14):w.writerow([i,int(i<2),100+i])
time.sleep(.15)
''');cpu.chmod(0o755)
            (root/'bin/build_identity.json').write_text(json.dumps(dict(package_manifest_sha256='mock',binaries={'cached_cpu':r.records.sha(cpu)})))
            d.R=root;r.check=lambda:dict(manifest_sha256='mock');r.board=lambda:None;r.base=lambda:base
            r.environment=lambda:dict(boot_id='test_boot',cpu_policy={},meminfo='fake memory',affinity=sorted(os.sched_getaffinity(0)))
            d.shutil.which=lambda name:None;d.main(perf=True)
            folder=next(root.glob('results_cpu_diag_*'));status=json.loads((folder/'status.json').read_text());assert status['measured']==12 and len(status['all_formal_compute_samples_ms'])==12 and status['review']
            assert json.loads((folder/'perf_status.json').read_text())['status']=='PERF_NOT_INSTALLED'
            assert json.loads((folder/'task_samples.json').read_text())
            cpu.write_text('#!/usr/bin/env python3\nraise SystemExit(3)\n');(root/'bin/build_identity.json').write_text(json.dumps(dict(package_manifest_sha256='mock',binaries={'cached_cpu':r.records.sha(cpu)})))
            caught=False
            try:d.main()
            except RuntimeError:caught=True
            assert caught and any(json.loads((q/'status.json').read_text())['status']=='FAILED_OR_INTERRUPTED' for q in root.glob('results_cpu_diag_*'))
    finally:
        d.R,r.check,r.board,r.base,r.environment=saved;d.shutil.which=which;os.sched_setaffinity(0,affinity)
    (R/'evidence/diagnostics_test.json').write_text(json.dumps(dict(status='PASS_CPU_DIAGNOSTIC_ORCHESTRATION',source_sha256=hashlib.sha256((P/'cpu_diagnostics.py').read_bytes()).hexdigest(),same_binary_identity_checked=True,same_process_AA_records=True,reported_ticks_and_last_cpu_fields=True,missing_PMU_not_zeroed=True,failed_child_retained=True,formal_comparison_not_replaced=True,hardware_executed=False),indent=2)+'\n')
    print('PASS_CPU_DIAGNOSTIC_ORCHESTRATION')
if __name__=='__main__':main()
