from pathlib import Path
R=Path(__file__).resolve().parent;OLD=R.parent/'v32_coreopt_20261029'
def main():
    s=(OLD/'verify_transport.py').read_text()
    s=s.replace("P=W/'board_packages/v32_coreopt_20261029'","P=W/'board_packages/v32_overlap_20261030'")
    s=s.replace('coreopt-transport-','overlap-transport-').replace('codex/transport','codex/overlap-transport')
    s=s.replace("('v32_diag_2_pipe','v32_core_2_pipe')","('v32_diag_2_pipe','v32_aie_only_2_pipe','v32_reducer_only_2_pipe','v32_core_2_pipe')")
    s=s.replace("q/('host/bo_host.cpp' if variant=='v32_diag_2_pipe' else 'variants/v32_core_2_pipe/host/bo_host.cpp')","q/('variants/'+variant+'/host/bo_host.cpp')")
    s=s.replace("q/('reference/host/perf_host.cpp' if variant=='v32_diag_2_pipe' else 'variants/v32_core_2_pipe/host/perf_host.cpp')","q/('variants/'+variant+'/host/perf_host.cpp')")
    s=s.replace("'PASS_FINAL_COREOPT_TRANSPORT_AND_RELEASE'","'PASS_FINAL_OVERLAP_TRANSPORT_AND_RELEASE'").replace('both_release_hosts','all_four_release_hosts').replace('both_matching_metadata','all_four_matching_metadata')
    needle="        run(['python3',q/'board_runner.py','detect']"
    assert needle in s
    extra='''        run(['g++','-O3','-std=c++17','-pthread',q/'tests/finish_overlap_test.cpp','-o',root/'finish_schedule'],root,'release_finish_compile.log')
        run([root/'finish_schedule',q/'test_fixture',root/'finish_results'],root,'release_finish_schedule.log')
        run([root/'finish_schedule',q/'test_fixture_edge',root/'finish_edge_results'],root,'release_finish_edge.log')
'''
    s=s.replace(needle,extra+needle)
    (R/'verify_transport.py').write_text(s,encoding='utf-8',newline='\n')
    print('TRANSPORT_VERIFIER_READY')
if __name__=='__main__':main()
