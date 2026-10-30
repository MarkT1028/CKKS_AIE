from pathlib import Path
import hashlib,json,re,sys
R=Path(__file__).resolve().parent;W=R.parents[1];P=R/'board_files'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    sys.path.insert(0,str(P));import board_runner as runner
    runner.validate_images();matrix=json.loads((P/'SOURCE_MATRIX.json').read_text());assert len(matrix)==4
    a=[matrix[v]['aie_sha256'] for v in ('v32_diag_2_pipe','v32_aie_only_2_pipe','v32_reducer_only_2_pipe','v32_core_2_pipe')]
    b=[matrix[v]['reducer_sha256'] for v in ('v32_diag_2_pipe','v32_aie_only_2_pipe','v32_reducer_only_2_pipe','v32_core_2_pipe')]
    assert a[0]==a[2] and a[1]==a[3] and a[0]!=a[1];assert b[0]==b[1] and b[2]==b[3] and b[0]!=b[2]
    assert len({v['reader_sha256'] for v in matrix.values()})==len({v['clock_config_sha256'] for v in matrix.values()})==1
    assert all(v['cores']==2 and v['PL_Hz']==225000000 for v in matrix.values())
    timing={}
    for name in ('v32_aie_only_2_pipe','v32_reducer_only_2_pipe'):
        h=json.loads((R/'evidence'/('hardware_'+name+'.json')).read_text());system=Path(h['build']);sign=json.loads((system/'postcheck_signoff.json').read_text());assert sign['setup_slack_ns']>=0 and sign['hold_slack_ns']>=0 and sign['drc_errors']==0
        assert 'VIOLATED' not in (system/'postcheck_bus_skew.rpt').read_text()
        assert re.search(r'# of nets with routing errors[.\s]*:\s*0\b',(system/'postcheck_route_status.rpt').read_text(),re.I)
        timing[name]=sign
    for name in ('aie_only','reducer_only'):
        c=json.loads((R/'evidence'/(name+'_chain_rtl.json')).read_text());assert c['status']=='PASS_ABLATION_ACTUAL_AIE_TO_RANDOM_STALL_REDUCER_RTL' and c['frames_each']==896 and c['verified_words_each']==2688 and c['lanes']==2
        assert 'Pass' in (R/'evidence'/(name+'_chain_rtl_cosim.rpt')).read_text()
    for name in ('model_small.log','model_full_real.log','asan.log','tsan_noaslr.log','edge_zero.log','edge_max.log','edge_random.log'):
        text=(R/'evidence'/name).read_text();assert 'PASS FINISH_OVERLAP_FUNCTIONAL' in text and 'FAIL ' not in text and 'ERROR: AddressSanitizer' not in text and 'WARNING: ThreadSanitizer' not in text
    tools=json.loads((R/'evidence/tools_test.json').read_text());assert tools['status']=='PASS_ISOLATED_OVERLAP_TOOLS'
    for n,h in tools['source_sha256'].items():assert sha(P/n)==h,'tools changed after test: '+n
    diagnostic=json.loads((R/'evidence/diagnostics_test.json').read_text());assert diagnostic['status']=='PASS_CPU_DIAGNOSTIC_ORCHESTRATION' and diagnostic['source_sha256']==sha(P/'cpu_diagnostics.py')
    for name in matrix:
        assert 'PASS ALL_MAPPED_SPLITS_AND_MERGES chunks=16 raw_words=5505024' in (R/'evidence'/('full_partition_'+name+'.log')).read_text()
        assert not any(x in (R/'evidence'/('XRT_syntax_'+name+'.log')).read_text() for x in ('error:','fatal error:'))
    provenance=json.loads((P/'SOURCE_PROVENANCE.json').read_text())
    for name,h in provenance['frozen_reference_files'].items():assert sha(P/name)==h
    assert sha(P/'common/replay.hpp')==sha(R/'reference/common/replay.hpp')
    assert sha(W/'v32_diag_inference.py')=='078db343138b5f51b018bf963c5aa638c0445b6e9bb6ec0c79713f6e565e8916'
    packages={}
    for name in ('v32_hs4_20261027','v32_hostopt_20261029','v32_bo_20261029','v32_coreopt_20261029'):
        root=W/'board_packages'/name
        for line in (root/'SHA256SUMS_PACKAGE').read_text().splitlines():
            h,n=line.split('  ',1);assert sha(root/n)==h,(name,n)
        packages[name]=sha(root/'SHA256SUMS_PACKAGE')
    result=dict(status='PASS_OVERLAP_OFFLINE_AUDIT',four_actual_boot_images_and_matching_flat_metadata=True,physical_two_by_two_XO_libadf_matrix_verified=True,new_ablations_timing=timing,CPU_source_and_baseline_scheduler_unchanged=True,full_real_independent_host_model_chunks=16,full_real_raw_words_per_replay=5505024,small_and_single_chunk_zero_max_random_cases=True,address_and_undefined_sanitizers=True,thread_sanitizer=True,thread_sanitizer_environment='setarch x86_64 -R for the one test process only',eight_fault_types_at_first_middle_last=True,all_four_hosts_official_XRT_header_syntax=True,all_four_hosts_real_partitions=True,both_actual_AIE_to_reducer_random_stall_RTL_endpoint_words=5376,tools=tools,previous_frozen_packages_unchanged=packages,original_v32_source_unchanged=True,board_tested=False,board_performance='PENDING',cryptographic_return='PENDING_NEW_BOARD_OUTPUTS',limitations=['Independent asynchronous arithmetic model is not XRT or device execution.','RTL chains cover endpoint residues, not concurrent full PL/AIE system simulation.','Current input remains the one fixed real h_s.4 group.','New start-to-wait envelopes can include prior-output work; primary comparison must use actual full wall.'])
    (R/'evidence/offline_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
