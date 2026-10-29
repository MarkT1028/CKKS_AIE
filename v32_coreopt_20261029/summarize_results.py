#!/usr/bin/env python3
"""Recompute latency and host interval overlap; never infer DMA from host spans."""
from pathlib import Path
from collections import Counter
import csv, hashlib, json, math, statistics, sys

MODES=('map_pingpong',)
STAGES=('split','input_write','input_sync','parameter_pack','parameter_write',
        'parameter_sync','output_poison','output_poison_write','output_poison_sync',
        'status','merge_poison','output_sync','output_read','merge','verify','output_save','execute')
PREP=set(STAGES[:9])
SINGLE={'status','merge_poison','verify','execute','output_save'}
WORDS=8192*14*3
TOL=.002  # milliseconds: CSV endpoints are independently rounded to six decimals

def need(ok,msg):
    if not ok:raise ValueError(msg)

def load(path):return json.loads(path.read_text())
def rows(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))

def number(v):
    x=float(v);need(math.isfinite(x) and x>=0,'negative/nonfinite timing');return x

def close(a,b):return math.isclose(a,b,rel_tol=1e-7,abs_tol=TOL)
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def overlap(spans,stage):
    return sum(max(0.,min(a['end'],b['end'])-max(a['begin'],b['begin']))
               for a in spans if a['stage']==stage
               for b in spans if b['stage']=='execute' and a['chunk']!=b['chunk'])

def hardware(root,mode,measured,warm):
    summary=load(root/'summary.json');setup=load(root/'setup.json')
    need(summary['status']=='PASS_VERIFIED_BO_REPLAY' and summary['mode']==mode,'hardware status/mode')
    need((summary['measured'],summary['warmups'],summary['chunks'],summary['export_replays'])==(measured,warm,16,1),'hardware planned counts')
    need(summary['stage_sum_is_not_wall_time'] is True and summary['firmware_changed'] is False,'hardware timing scope')
    need(setup['mode']==mode and setup['banks']==(2 if mode=='map_pingpong' else 1),'BO bank count')
    need((setup['input_bytes'],setup['golden_bytes'])==(896*1024**2,42*1024**2),'cached real data sizes')
    for k,v in setup.items():
        if k.endswith('_ms'):number(v)
    iterations=rows(root/'iterations.csv');trace=rows(root/'timeline.csv')
    need(len(iterations)==measured+warm+1,'hardware iteration count')
    grouped={i:[] for i in range(len(iterations))}
    for row in trace:
        rep=int(row['repetition']);need(rep in grouped,'unexpected trace repetition')
        grouped[rep].append(row)
    all_samples=[];stages={k:[] for k in STAGES};selected=[]
    for rep,row in enumerate(iterations):
        exporting=rep==measured+warm;iswarm=rep<warm
        need((int(row['repetition']),int(row['warmup']),int(row['export_only']),int(row['chunks']),int(row['verified_words']))==(rep,int(iswarm),int(exporting),16,WORDS*16),'hardware iteration identity')
        wall=number(row['replay_wall_ms']);need(wall>0,'zero replay duration')
        spans=[];frames=[]
        for t in grouped[rep]:
            need(int(t['warmup'])==int(iswarm) and int(t['export_only'])==int(exporting),'trace flags')
            chunk=int(t['chunk']);bank=int(t['bank']);stage=t['stage'];lane=int(t['lane'])
            begin=number(t['begin_ms']);end=number(t['end_ms'])
            need(0<=chunk<16 and bank==(chunk%2 if mode=='map_pingpong' else 0),'trace chunk/bank')
            need(stage in STAGES and (lane==-1 if stage in SINGLE else lane in (0,1)),'trace stage/lane')
            need(begin<=end and end<=wall+TOL,'invalid trace interval')
            spans.append(dict(chunk=chunk,bank=bank,stage=stage,lane=lane,begin=begin,end=end))
        expected=Counter({(k,-1):1 for k in ('execute','status','merge_poison','verify')})
        for k in ('split','input_sync','parameter_pack','parameter_write','parameter_sync','output_poison','output_poison_sync','output_sync','merge'):
            for lane in (0,1):expected[k,lane]=1
        if mode=='copy_serial':
            for k in ('input_write','output_poison_write','output_read'):
                for lane in (0,1):expected[k,lane]=1
        if exporting:expected['output_save',-1]=1
        for chunk in range(16):
            frame=[s for s in spans if s['chunk']==chunk]
            need(Counter((s['stage'],s['lane']) for s in frame)==expected,'missing/duplicate/unexpected span')
            by={(s['stage'],s['lane']):s for s in frame};execute=by['execute',-1];verify=by['verify',-1]
            need(all(s['end']<=execute['begin']+TOL for s in frame if s['stage'] in PREP),'own preparation overlaps own execution')
            need(all(s['begin']+TOL>=execute['end'] for s in frame if s['stage'] not in PREP|{'execute'}),'readback before execution complete')
            need(all(s['end']<=verify['begin']+TOL for s in frame if s['stage'] not in PREP|{'verify','output_save'}),'verify before merge complete')
            if exporting:need(by['output_save',-1]['begin']+TOL>=verify['end'],'export before verification')
            # Every frame is written in true within-frame order by one owner.
            need(all(a['end']<=b['begin']+TOL for a,b in zip(frame,frame[1:])),'overlapping/reordered per-frame stages')
            frames.append(dict(prep_begin=min(s['begin'] for s in frame if s['stage'] in PREP),prep_end=max(s['end'] for s in frame if s['stage'] in PREP),execute=execute,done=max(s['end'] for s in frame)))
        for i in range(1,16):
            need(frames[i]['execute']['begin']+TOL>=frames[i-1]['done'],'concurrent kernels or unfinished previous output')
            need(frames[i]['prep_begin']+TOL>=frames[i-1]['prep_end'],'multiple concurrent preparation jobs')
            if mode=='map_pingpong':
                need(frames[i]['prep_begin']+TOL>=frames[i-1]['execute']['begin'],'next preparation before controller launch')
                if i>=2:need(frames[i]['prep_begin']+TOL>=frames[i-2]['done'],'bank reused before prior verification/export')
            else:need(frames[i]['prep_begin']+TOL>=frames[i-1]['done'],'serial preparation unexpectedly overlaps')
        sums={k:sum(s['end']-s['begin'] for s in spans if s['stage']==k) for k in STAGES}
        for k in STAGES:
            column='execute_sum_ms' if k=='execute' else k+'_sum_ms'
            need(close(sums[k],number(row[column])),'stage aggregate mismatch: '+k)
        need(close(sum(sums.values()),number(row['stage_work_sum_ms'])),'total work sum mismatch')
        for stage in ('split','input_sync'):
            value=overlap(spans,stage)
            need(close(value,number(row[stage+'_during_other_execute_ms'])),'overlap aggregate mismatch')
            if mode!='map_pingpong':need(value<=TOL,'serial path has overlap')
        if mode!='map_pingpong':need(sum(sums.values())<=wall+TOL,'serial work exceeds wall')
        item={k:number(v) for k,v in row.items() if k.endswith('_ms')}
        item.update(repetition=rep,warmup=iswarm,export_only=exporting)
        all_samples.append(item)
        if not iswarm and not exporting:
            selected.append(item)
            for k in STAGES:stages[k].append(sums[k])
    medians={k:statistics.median(r[k] for r in selected) for k in selected[0] if k.endswith('_ms')}
    need(close(medians['replay_wall_ms'],number(summary['replay_wall_median_ms'])),'hardware wall median mismatch')
    need(close(medians['execute_sum_ms'],number(summary['host_observed_execute_sum_median_ms'])),'hardware execution median mismatch')
    output=root/'outputs';files=sorted(output.glob('*'))
    need(sorted(p.name for p in files)==sorted(f'chunk_{i}_output.bin' for i in range(16)) and all(p.is_file() and not p.is_symlink() for p in files),'final raw output inventory')
    command=load(root.with_suffix('.command.json'));need(command['exit_code']==0,'hardware command failed')
    return dict(medians_ms=medians,stage_work_medians_ms={k:statistics.median(v) for k,v in stages.items()},all_samples=all_samples,setup=setup,command=command,output_sha256={p.name:digest(p) for p in files})

def cpu(root,measured,warm):
    summary=load(root/'summary.json');setup=load(root/'setup.json')
    need(summary['status']=='PASS_FULL_RAW_MAC_CPU_REPLAY' and summary['threads']==2,'cached two-thread CPU status')
    need((summary['measured'],summary['warmups'],summary['chunks'])==(measured,warm,16),'CPU planned counts')
    need((setup['input_bytes'],setup['golden_bytes'])==(896*1024**2,42*1024**2),'CPU cached real data sizes')
    chunks=rows(root/'chunks.csv');iterations=rows(root/'iterations.csv')
    need(len(iterations)==measured+warm and len(chunks)==16*len(iterations),'CPU iteration count')
    selected=[]
    for i,row in enumerate(iterations):
        need((int(row['repetition']),int(row['warmup']))==(i,int(i<warm)),'CPU iteration order')
        group=chunks[16*i:16*(i+1)]
        need([r['chunk'] for r in group]==[f'chunk_{j}' for j in range(16)],'CPU missing/duplicate chunks')
        for r in group:
            need((int(r['repetition']),int(r['warmup']),int(r['verified_words']))==(i,int(i<warm),WORDS),'CPU chunk identity')
            for k,v in r.items():
                if k.endswith('_ms'):number(v)
            need(number(r['output_save_ms'])<.05,'CPU must not save outputs in this comparison')
        for source,target in (('compute_ms','compute_sum_ms'),('verified_call_ms','verified_call_sum_ms')):
            need(close(sum(number(r[source]) for r in group),number(row[target])),'CPU aggregate mismatch')
        need(number(row['full_replay_ms'])+TOL>=number(row['verified_call_sum_ms']),'CPU full wall shorter than calls')
        if i>=warm:selected.append(row)
    pairs=(('compute_sum_ms','compute_sum_median_ms'),('verified_call_sum_ms','chunk_verified_call_sum_median_ms'),('full_replay_ms','full_replay_median_ms'))
    medians={key:statistics.median(number(r[source]) for r in selected) for source,key in pairs}
    for key,value in medians.items():need(close(value,number(summary[key])),'CPU median mismatch')
    command=load(root.with_suffix('.command.json'));need(command['exit_code']==0,'CPU command failed')
    return dict(recomputed_ms=medians,all_samples=iterations,setup=setup,command=command)

def summarize(directory):
    need(load(directory/'status.json')['status']=='PASS_CORE_BOARD_COMPARISON','run incomplete/failed')
    identity=load(directory/'run_identity.json');kind=identity['mode']
    need(kind in ('smoke','formal') and len(identity['order'])==1 and set(identity['order'])==set(MODES),'run order/mode inventory')
    reps,warm=(1,0) if kind=='smoke' else (5,1);creps=1 if kind=='smoke' else 3
    result=dict(status='PASS_RECOMPUTED_CORE_COMPARISON',variant=identity['variant'],mode=kind,order=identity['order'],modes={},
                primary_metric='actual replay wall: first preparation to final full integer check; excludes setup, trace writing and separate export replay',
                CPU_scope='unchanged cached two-thread u128 reference; full replay includes its small CSV logging overhead; not optimal CPU or full v32 model',
                overlap_scope='host intervals only: preparation versus XRT run/wait; no proof of actual DMA transfer or AIE activity overlap',
                historical_scope='compare separate boots only with matching fixture and map_pingpong protocol; prior historical CPU cohorts are not substituted')
    common_outputs=None
    for mode in MODES:
        folder=directory/mode;h=hardware(folder/'hardware',mode,reps,warm);b=cpu(folder/'cpu2_before',creps,warm);a=cpu(folder/'cpu2_after',creps,warm)
        if common_outputs is None:common_outputs=h['output_sha256']
        need(h['output_sha256']==common_outputs,'different raw outputs between BO modes')
        computes=[x['recomputed_ms']['compute_sum_median_ms'] for x in (b,a)]
        cpu_walls=[x['recomputed_ms']['full_replay_median_ms'] for x in (b,a)]
        drift=(computes[1]/computes[0]-1)*100
        result['modes'][mode]=dict(hardware=h,cpu2_before=b,cpu2_after=a,cpu_compute_drift_percent=drift,drift_over_5_percent=abs(drift)>5,
                                  hardware_wall_speedup_vs_each_cpu=[c/h['medians_ms']['replay_wall_ms'] for c in cpu_walls])
    comparisons={}
    for old,new in ():
        x=result['modes'][old]['hardware']['medians_ms']['replay_wall_ms'];y=result['modes'][new]['hardware']['medians_ms']['replay_wall_ms']
        comparisons[old+'__to__'+new]=dict(old_wall_ms=x,new_wall_ms=y,speedup=x/y,reduction_percent=(1-y/x)*100)
    result['same_protocol_comparisons']=comparisons
    m=result['modes']['map_pingpong'];h=m['hardware']['medians_ms']['replay_wall_ms']
    m['hardware_wall_speedup_vs_each_cpu_compute']=[m[k]['recomputed_ms']['compute_sum_median_ms']/h for k in ('cpu2_before','cpu2_after')]
    result['beats_both_adjacent_cpu_full_wall']=all(x>1 for x in m['hardware_wall_speedup_vs_each_cpu'])
    result['beats_both_adjacent_cpu_compute_only']=all(x>1 for x in m['hardware_wall_speedup_vs_each_cpu_compute'])
    result['cpu_drift_requires_review']=m['drift_over_5_percent']
    (directory/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['Core candidate '+identity['variant']+'. Primary: actual verified replay wall; setup and export are separate.']
    for mode in MODES:
        m=result['modes'][mode];h=m['hardware']['medians_ms']
        lines.append(f"{mode}: verified wall={h['replay_wall_ms']:.3f} ms; host run/wait sum={h['execute_sum_ms']:.3f} ms; input-sync host overlap={h['input_sync_during_other_execute_ms']:.3f} ms; CPU drift={m['cpu_compute_drift_percent']:+.2f}%")
    for name,c in comparisons.items():lines.append(f"{name}: {c['reduction_percent']:+.2f}% less wall time; {c['speedup']:.4f}x")
    lines.append('Faster than BOTH adjacent CPU full walls: '+str(result['beats_both_adjacent_cpu_full_wall'])+'; faster than BOTH CPU compute-only times: '+str(result['beats_both_adjacent_cpu_compute_only']))
    lines.append('Stage work sums are not wall latency. Return the archive for independent original-context verification.')
    text='\n'.join(lines)+'\n';(directory/'comparison.txt').write_text(text);print(text,end='');return result

if __name__=='__main__':summarize(Path(sys.argv[1]))
