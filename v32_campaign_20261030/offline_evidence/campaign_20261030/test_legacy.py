from pathlib import Path
import importlib.util,json,sys,tempfile
R=Path(__file__).resolve().parent;W=R.parents[1];P=R/'board_files';sys.path.insert(0,str(P))
import board_runner as runner
spec=importlib.util.spec_from_file_location('overlap_old_tests',W/'integration/v32_overlap_20261029/test_tools.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def main():
    with tempfile.TemporaryDirectory(prefix='campaign-legacy-test-') as tmp:
        root=Path(tmp);h.test_summary(root);h.test_runner(root);h.old.test_manifest(root)
    spec=importlib.util.spec_from_file_location('cpu_diag_regression',W/'integration/v32_overlap_20261029/test_diagnostics.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d);d.R=R;d.P=P;d.main()
    out=dict(status='PASS_REUSED_RUNNER_TIMELINE_AND_CPU_DIAGNOSTIC_REGRESSIONS',timeline_missing_duplicate_reuse_concurrent_status_and_aggregate_faults_rejected=True,all_four_variant_run_commands_checked=True,formal_counts_and_cpu_before_after_unchanged=True,wrong_boot_and_tampered_binary_rejected=True,manifest_unsafe_and_corrupt_entries_rejected=True,CPU_diagnostics_fake_child_and_failure_cleanup=True,hardware_executed=False)
    (R/'evidence/legacy_test.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
