#!/usr/bin/env python3
"""Aggregate complete runs by firmware and boot, keeping every formal sample."""
from pathlib import Path
import json,statistics
import board_runner as runner
import summarize_results as summary
R=Path(__file__).resolve().parent
def _main():
    runs=[];failed=[]
    for folder in sorted(R.glob('results_core_*')):
        status=json.loads((folder/'status.json').read_text()) if (folder/'status.json').exists() else {}
        if status.get('status')!='PASS_CORE_BOARD_COMPARISON':failed.append(folder.name);continue
        result=summary.summarize(folder);identity=json.loads((folder/'run_identity.json').read_text());e=json.loads((folder/'environment_before.json').read_text())
        variant=identity['variant'];runner.require(identity['boot_uuid']==runner.VARIANTS[variant]['uuid']==e['boot_uuid'],'run firmware identity mismatch')
        runner.require(identity['base_manifest_sha256']==runner.BASE_MANIFEST,'different fixture dependency')
        m=result['modes']['map_pingpong'];h=m['hardware']
        for name,digest in h['output_sha256'].items():
            runner.require(digest==runner.records.sha(runner.base()/'fixture/chunks'/name.replace('_output','_expected')),'saved full output differs from original golden: '+name)
        runs.append(dict(folder=folder.name,kind=identity['mode'],variant=variant,boot_id=e['boot_id'],package_manifest=identity['manifest_sha256'],hardware_wall_ms=[x['replay_wall_ms'] for x in h['all_samples'] if not x['warmup'] and not x['export_only']],execute_sum_ms=[x['execute_sum_ms'] for x in h['all_samples'] if not x['warmup'] and not x['export_only']],cpu_before_full_ms=m['cpu2_before']['recomputed_ms']['full_replay_median_ms'],cpu_after_full_ms=m['cpu2_after']['recomputed_ms']['full_replay_median_ms'],cpu_before_compute_ms=m['cpu2_before']['recomputed_ms']['compute_sum_median_ms'],cpu_after_compute_ms=m['cpu2_after']['recomputed_ms']['compute_sum_median_ms'],cpu_drift_percent=m['cpu_compute_drift_percent']))
    runner.require(runs,'No complete runs')
    cohorts={}
    for item in runs:
        if item['kind']!='formal':continue
        key=item['variant']+'/'+item['boot_id'];cohorts.setdefault(key,[]).append(item)
    groups={}
    for key,items in cohorts.items():
        values=[v for r in items for v in r['hardware_wall_ms']];execute=[v for r in items for v in r['execute_sum_ms']]
        walls=[r[k] for r in items for k in ('cpu_before_full_ms','cpu_after_full_ms')];computes=[r[k] for r in items for k in ('cpu_before_compute_ms','cpu_after_compute_ms')]
        med=statistics.median(values)
        groups[key]=dict(runs=len(items),samples=len(values),all_hardware_walls_ms=values,wall_median_ms=med,wall_min_ms=min(values),wall_max_ms=max(values),execute_sum_median_ms=statistics.median(execute),adjacent_cpu_full_medians_ms=walls,adjacent_cpu_compute_medians_ms=computes,speedup_vs_each_cpu_full=[v/med for v in walls],speedup_vs_each_cpu_compute=[v/med for v in computes],median_beats_every_adjacent_cpu_full=med<min(walls),median_beats_every_adjacent_cpu_compute=med<min(computes),worst_hw_sample_beats_every_adjacent_cpu_full=max(values)<min(walls),cpu_drift_over_5_percent=any(abs(r['cpu_drift_percent'])>5 for r in items))
    out=dict(status='RECOMPUTED_CAMPAIGN_PENDING_INDEPENDENT_CRYPTO_RETURN',runs=runs,formal_boot_groups=groups,failed_or_incomplete_folders=failed,scope='One real v32 MAC group. Preserve per-boot groups; no multi-boot stability claim for a single boot; CPU drift and every measured sample retained. Setup/export and full-model inference excluded from primary wall.')
    runner.write(R/'campaign_summary.json',out)
    for key,g in groups.items():print(key,'wall_ms=',round(g['wall_median_ms'],3),'samples=',g['samples'],'beat_all_adjacent_CPU_full=',g['median_beats_every_adjacent_cpu_full'],'beat_all_CPU_compute=',g['median_beats_every_adjacent_cpu_compute'],'CPU_drift_review=',g['cpu_drift_over_5_percent'])
    print('CAMPAIGN_SUMMARY='+str(R/'campaign_summary.json'))
def main():
    try:return _main()
    except Exception as exc:
        runner.write(R/'campaign_summary.json',dict(status='FAILED_CAMPAIGN_RECOMPUTATION',error=repr(exc)))
        raise
if __name__=='__main__':main()
