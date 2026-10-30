#!/usr/bin/env python3
"""Separate firmware, schedule, boot and order; never pool independent protocols."""
from pathlib import Path
import json,statistics
import board_runner as r
import summarize_results as s
R=Path(__file__).resolve().parent
def main():
    runs=[];failed=[];cohorts={}
    for folder in sorted(R.glob('results_overlap_*')):
        status=s.load(folder/'status.json') if (folder/'status.json').exists() else {}
        if status.get('status')!='PASS_OVERLAP_BOARD_COMPARISON':failed.append(folder.name);continue
        result=s.summarize(folder);identity=s.load(folder/'run_identity.json');env=s.load(folder/'environment_before.json')
        variant=identity['variant'];r.require(identity['boot_uuid']==env['boot_uuid']==r.VARIANTS[variant]['uuid'],'firmware identity mismatch')
        r.require(identity['boot_id']==env['boot_id'] and identity['base_manifest_sha256']==r.BASE_MANIFEST,'boot/fixture identity mismatch')
        r.require(s.load(folder/'environment_after.json')['boot_id']==env['boot_id'],'boot changed inside run')
        for mode,data in result['modes'].items():
            h=data['hardware']
            for name,digest in h['output_sha256'].items():r.require(digest==r.records.sha(r.base()/'fixture/chunks'/name.replace('_output','_expected')),'saved output differs from golden')
            item=dict(folder=folder.name,kind=identity['mode'],variant=variant,campaign=identity['campaign'],mode=mode,boot_id=env['boot_id'],order=identity['order'],hardware_wall_ms=[x['replay_wall_ms'] for x in h['all_samples'] if not x['warmup'] and not x['export_only']],start_to_wait_return_ms=[x['execute_sum_ms'] for x in h['all_samples'] if not x['warmup'] and not x['export_only']],cpu_full_medians_ms=[data[k]['recomputed_ms']['full_replay_median_ms'] for k in ('cpu2_before','cpu2_after')],cpu_compute_medians_ms=[data[k]['recomputed_ms']['compute_sum_median_ms'] for k in ('cpu2_before','cpu2_after')],cpu_drift_percent=data['cpu_compute_drift_percent'])
            runs.append(item)
            if item['kind']=='formal':cohorts.setdefault('/'.join([variant,identity['campaign'],mode,env['boot_id']]),[]).append(item)
    r.require(runs,'No complete runs');groups={}
    for key,items in cohorts.items():
        values=[x for row in items for x in row['hardware_wall_ms']];cpus=[x for row in items for x in row['cpu_full_medians_ms']];compute=[x for row in items for x in row['cpu_compute_medians_ms']];med=statistics.median(values)
        groups[key]=dict(runs=len(items),samples=len(values),all_hardware_walls_ms=values,wall_median_ms=med,wall_min_ms=min(values),wall_max_ms=max(values),adjacent_CPU_full_medians_ms=cpus,adjacent_CPU_compute_medians_ms=compute,median_beats_all_adjacent_CPU_full=med<min(cpus),median_beats_all_adjacent_CPU_compute=med<min(compute),CPU_drift_review=any(abs(row['cpu_drift_percent'])>5 for row in items),orders=[row['order'] for row in items])
    boots={v:sorted({x['boot_id'] for x in runs if x['kind']=='formal' and x['variant']==v}) for v in r.VARIANTS}
    host_boots={v:sorted({x['boot_id'] for x in runs if x['kind']=='formal' and x['variant']==v and x['campaign']=='host' and x['mode']=='map_finish_overlap'}) for v in r.VARIANTS}
    ablation={v:sorted({x['boot_id'] for x in runs if x['kind']=='formal' and x['variant']==v and x['campaign']=='ablation' and x['mode']=='map_pingpong'}) for v in r.VARIANTS}
    cell_ready={v:any(g['samples']>=10 for k,g in groups.items() if k.startswith(v+'/ablation/map_pingpong/')) for v in r.VARIANTS}
    out=dict(status='RECOMPUTED_OVERLAP_CAMPAIGN_PENDING_CRYPTO_RETURN',runs=runs,formal_boot_groups=groups,formal_boot_ids_by_variant=boots,host_candidate_boot_ids_by_variant=host_boots,ablation_boot_ids=ablation,all_four_ablation_cells_present=len(ablation)==4 and all(ablation.values()),ablation_10_samples_per_cell=cell_ready,all_four_ablation_cells_have_10_samples=len(cell_ready)==4 and all(cell_ready.values()),failed_or_incomplete_folders=failed,scope='Same fixed real MAC group; keep firmware/schedule/campaign/boot/order cohorts separate. Candidate speed and crypto return pending. Host start-to-wait envelopes are not device event durations.')
    r.write(R/'campaign_summary.json',out)
    for key,g in groups.items():print(key,'wall_ms='+format(g['wall_median_ms'],'.3f'),'samples='+str(g['samples']),'CPU_drift_review='+str(g['CPU_drift_review']))
    print('CORE_HOST_FORMAL_BOOTS='+str(len(host_boots.get('v32_core_2_pipe',[]))));print('ALL_ABLATION_CELLS_PRESENT='+str(out['all_four_ablation_cells_present']));print('ALL_ABLATION_CELLS_10_SAMPLES='+str(out['all_four_ablation_cells_have_10_samples']));print('CAMPAIGN_SUMMARY='+str(R/'campaign_summary.json'))
if __name__=='__main__':
    try:main()
    except Exception as exc:r.write(R/'campaign_summary.json',dict(status='FAILED_CAMPAIGN_RECOMPUTATION',error=repr(exc)));raise
