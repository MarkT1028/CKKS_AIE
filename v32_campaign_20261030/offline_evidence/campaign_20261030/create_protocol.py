from pathlib import Path
import json
R=Path(__file__).resolve().parent;P=R/'board_files'
def main():
    variants=['v32_core_2_pipe','v32_aie_only_2_pipe','v32_reducer_only_2_pipe','v32_diag_2_pipe']
    steps=[dict(id=f'H{i+1:02}',phase='host',variant=variants[0],block=0,formal_reverse_flags=[True,False] if i==1 else [False,True]) for i in range(3)]
    steps += [dict(id=f'A{i+1:02}',phase='ablation',variant=v,block=1 if i<4 else 2,formal_reverse_flags=[False,True]) for i,v in enumerate(variants+list(reversed(variants)))]
    d=dict(schema='v32_research_campaign_v1',host_target_independent_boots=3,ablation_mode='map_pingpong',formal_hardware_repetitions_per_run=5,formal_runs_per_step=2,hardware_warmups_per_formal=1,cpu_repetitions_per_adjacent_stage=3,cpu_threads=2,steps=steps,workload=dict(N=131072,L=14,K=16,chunks=16,fixed_capture='h_s.4 BSGS5 diagonals80..95'),host_modes=['map_pingpong','map_finish_overlap'],boot_policy='Different Linux boot_id for every enrolled step within each phase. A01 may reuse the H03 boot. A04 and A05 require different boots despite using the same variant.',counterbalancing_scope='Two reverse-order hardware blocks are descriptive cross-boot controls, not a randomized causal experiment.',primary_metric='Actual full resident verified replay wall; warmups, smoke, one-time setup and independent export replay excluded and retained separately.',cpu_drift_review_threshold_percent=5,cryptographic_return='PENDING_NEW_BOARD_OUTPUTS')
    (P/'STUDY_PROTOCOL.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8',newline='\n')
    p=P/'run_study.sh';p.write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -eq 0 ]; then set -- next; fi
exec python3 "$root/study.py" "$@"
''',encoding='utf-8',newline='\n')
    print('FROZEN_PROTOCOL_3_HOST_BOOTS_2_COUNTERBALANCED_ABLATION_BLOCKS')
if __name__=='__main__':main()
