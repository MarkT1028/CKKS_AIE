#!/usr/bin/env python3
"""Recompute every aggregate from CSV. Never drop saved-output outliers."""
from pathlib import Path
import csv,json,math,statistics,sys
MODES=('stream_scalar','resident_scalar','resident_block')
def need(ok,msg):
    if not ok:raise ValueError(msg)
def load(p):return json.loads(p.read_text())
def rows(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def close(a,b):return math.isclose(a,b,rel_tol=1e-7,abs_tol=.0001)
def sample(root,cpu=False):
    summary=load(root/'summary.json');chunks=rows(root/'chunks.csv');iterations=rows(root/'iterations.csv')
    need(summary['status']==('PASS_FULL_RAW_MAC_CPU_REPLAY' if cpu else 'PASS_FULL_REAL_V32_RAW_MAC_REPLAY'),'invalid raw replay status')
    if cpu:need(summary['threads']==2,'expected matching two-thread ARM CPU reference')
    measured=int(summary['measured']);warm=int(summary['warmups']);n=int(summary['chunks'])
    need(measured>0 and len(iterations)==measured+warm and len(chunks)==n*len(iterations),'sample count mismatch')
    need(n==16,'expected 16 real chunks')
    timing=('compute_ms','verified_call_ms') if cpu else ('execution_ms','transaction_ms')
    sums=('compute_sum_ms','verified_call_sum_ms') if cpu else ('execution_sum_ms','transaction_sum_ms')
    keys=('compute_sum_median_ms','chunk_verified_call_sum_median_ms') if cpu else ('execution_sum_median_ms','chunk_transaction_sum_median_ms')
    measured_rows=[];phases={};save=[]
    for i,row in enumerate(iterations):
        need(int(row['repetition'])==i and int(row['warmup'])==int(i<warm),'iteration/warmup order')
        group=chunks[i*n:(i+1)*n]
        need([r['chunk'] for r in group]==[f'chunk_{x}' for x in range(n)],'missing/duplicate chunks')
        need(all(int(r['repetition'])==i and int(r['warmup'])==int(i<warm) and int(r['verified_words'])==8192*14*3 for r in group),'chunk metadata mismatch')
        for r in group:
            for k,v in r.items():
                if k.endswith('_ms'):need(math.isfinite(float(v)) and float(v)>=0,'negative/nonfinite time')
        for source,target in zip(timing,sums):need(close(sum(float(r[source]) for r in group),float(row[target])),'CSV aggregate mismatch: '+target)
        total_save=sum(float(r['output_save_ms']) for r in group)
        need(float(row['full_replay_ms'])+.001>=float(row[sums[1]])+total_save,'full replay shorter than verified calls plus saving')
        save.append(dict(repetition=i,warmup=i<warm,output_save_sum_ms=total_save,full_replay_ms=float(row['full_replay_ms'])))
        if i>=warm:
            measured_rows.append(row)
            for key in group[0]:
                if key.endswith('_ms'):phases.setdefault(key,[]).append(sum(float(r[key]) for r in group))
    medians={}
    for source,key in zip(sums,keys):
        medians[key]=statistics.median(float(r[source]) for r in measured_rows)
        need(close(medians[key],float(summary[key])),'summary mismatch: '+key)
    medians['full_replay_median_ms']=statistics.median(float(r['full_replay_ms']) for r in measured_rows)
    need(close(medians['full_replay_median_ms'],summary['full_replay_median_ms']),'full replay summary mismatch')
    return dict(recomputed=medians,measured=measured,warmups=warm,setup=load(root/'setup.json') if (root/'setup.json').exists() else dict(xrt_init_ms=summary.get('xrt_init_ms'),note='streaming data admission remains inside every iteration'),phase_sum_medians_ms={k:statistics.median(v) for k,v in phases.items()},all_iteration_save_times=save,command=load(root.with_suffix('.command.json')))
def summarize(directory):
    need(load(directory/'status.json')['status']=='PASS_HOSTOPT_BOARD_COMPARISON','run incomplete/failed')
    identity=load(directory/'run_identity.json');need(set(identity['order'])==set(MODES) and len(identity['order'])==3,'comparison mode inventory')
    result=dict(status='PASS_RECOMPUTED_HOSTOPT_COMPARISON',mode=identity['mode'],order=identity['order'],modes={},scope='same fixed real v32 fixture; steady-state cache/setup reported separately; CPU u128 reference, not fastest possible CPU; final saved-output sample retained')
    for mode in MODES:
        folder=directory/mode
        h=sample(folder/'hardware');b=sample(folder/'cpu2_before',True);a=sample(folder/'cpu2_after',True)
        for x,is_cpu in ((h,False),(b,True),(a,True)):
            need((x['measured'],x['warmups'])==((1,0) if identity['mode']=='smoke' else (3 if is_cpu else 5,1)),'wrong planned measured/warmup count')
        cpu_compute=[x['recomputed']['compute_sum_median_ms'] for x in (b,a)]
        cpu_call=[x['recomputed']['chunk_verified_call_sum_median_ms'] for x in (b,a)]
        drift=(cpu_compute[1]/cpu_compute[0]-1)*100
        result['modes'][mode]=dict(hardware=h,cpu2_before=b,cpu2_after=a,cpu_compute_drift_percent=drift,drift_over_5_percent=abs(drift)>5,hardware_core_speedup_vs_each_cpu=[x/h['recomputed']['execution_sum_median_ms'] for x in cpu_compute],hardware_transaction_speedup_vs_each_cpu=[x/h['recomputed']['chunk_transaction_sum_median_ms'] for x in cpu_call])
    comparisons={}
    for older,newer in zip(MODES,MODES[1:]):
        old=result['modes'][older]['hardware'];new=result['modes'][newer]['hardware']
        comparisons[older+'__to__'+newer]={k:dict(old_ms=old['recomputed'][k],new_ms=new['recomputed'][k],speedup=old['recomputed'][k]/new['recomputed'][k],reduction_percent=(1-new['recomputed'][k]/old['recomputed'][k])*100) for k in old['recomputed']}
    result['attributed_comparisons']=comparisons
    (directory/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['Host-only experiment; firmware unchanged.','Setup/admission are outside resident iteration times and listed separately.']
    for mode in MODES:
        m=result['modes'][mode];h=m['hardware']['recomputed']
        lines.append(f"{mode}: main={h['execution_sum_median_ms']:.3f} ms; verified transaction={h['chunk_transaction_sum_median_ms']:.3f} ms; replay={h['full_replay_median_ms']:.3f} ms; CPU before/after drift={m['cpu_compute_drift_percent']:+.2f}%")
    lines.append('All full-replay samples, including final output saving, are retained. Return the collected archive for independent and cryptographic verification.')
    text='\n'.join(lines)+'\n';(directory/'comparison.txt').write_text(text);print(text,end='');return result
if __name__=='__main__':summarize(Path(sys.argv[1]))
