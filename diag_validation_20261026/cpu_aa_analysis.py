"""Independent recomputation of CPU A/A CSVs. No claim of a causal attribution."""
from pathlib import Path
import csv,json,math,statistics
PHASES=[('short_A1','reuse',False),('short_B','copy',False),('short_A2','reuse',False),('short_C','reallocate',False),('short_A3','reuse',False),('long_A1','reuse',True),('long_B','copy',True),('long_A2','reuse',True),('long_C','reallocate',True),('long_A3','reuse',True)]
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def stats(values):
    v=sorted(values);require(v and all(math.isfinite(x) and x>=0 for x in v),'Invalid samples')
    return {'n':len(v),'median':statistics.median(v),'p95':v[math.ceil(.95*len(v))-1],'min':v[0],'max':v[-1]}
def readcsv(path):
    with Path(path).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def analyze_case(host,golden,targets,reps,blocks,sw,lw):
    host=Path(host);session=json.loads((host/'session.json').read_text());rows=readcsv(host/'iterations.csv');summaries=readcsv(host/'blocks.csv')
    require(session['scope']=='diagnostic_cpu_AA_not_formal_CPU_HW_comparison','Wrong diagnostic scope')
    require(session['same_process_and_thread_pool'] is True and session['physical_page_identity_not_measured'] is True,'Wrong A/A contract')
    require((session['repetitions_per_block'],session['blocks_per_phase'],session['short_warmups_per_block'],session['long_warmups_per_block'])==(reps,blocks,sw,lw),'Session count mismatch')
    require(session['threads']==len(targets) and session['N']==8192 and session['L']==3 and session['K']==16,'CPU workload mismatch')
    affinity=json.loads((host/'affinity_before.json').read_text())
    require(affinity==json.loads((host/'affinity_after.json').read_text()),'Worker pool or affinity changed')
    require(len(affinity['workers'])==len(targets),'Worker count mismatch')
    for lane,w in enumerate(affinity['workers']):require(w['allowed_cpus']==[targets[lane]] and w['target_cpu']==targets[lane] and w['tid']>0,'Worker not pinned')
    require(len(rows)==10*blocks*reps+5*blocks*(sw+lw) and len(summaries)==10*blocks,'Incorrect row count')
    pointer=0;result=[]
    for name,policy,long in PHASES:
        phase=[];prev=None;warm=lw if long else sw
        for block in range(blocks):
            blockrows=rows[pointer:pointer+reps+warm];pointer+=reps+warm
            summary=summaries[len(result)*blocks+block]
            require(summary['phase']==name and summary['policy']==policy and int(summary['block'])==block,'Block sequence mismatch')
            ia,oa=int(summary['input_address']),int(summary['output_address'])
            stable=(session['stable_input_virtual_address'],session['stable_output_virtual_address'])
            if policy=='reallocate':
                require(ia!=stable[0] and oa!=stable[1],'Reallocation did not change backing storage')
                if prev:require(ia!=prev[0] and oa!=prev[1],'Adjacent live allocation reused')
            else:require((ia,oa)==stable,'Reuse phase backing storage changed')
            prev=(ia,oa);measured=[]
            for i,row in enumerate(blockrows):
                require((row['phase'],row['policy'],int(row['block']),int(row['repetition']),int(row['warmup']))==(name,policy,block,i,int(i<warm)),'Iteration sequence mismatch')
                require(int(row['verified_words'])==73728 and int(row['K'])==16 and int(row['threads'])==len(targets),'Workload/verification mismatch')
                require((int(row['input_address']),int(row['output_address']))==(ia,oa),'Pointer changed inside block')
                times=[float(row[k]) for k in ['poison_ms','compute_ms','validation_ms','verified_call_ms']]
                require(all(math.isfinite(x) and x>=0 for x in times) and abs(sum(times[:3])-times[3])<=.000010,'Invalid timing sum')
                for lane,cpu in enumerate(targets):require([int(row[f'cpu{lane}_start']),int(row[f'cpu{lane}_end'])]==[cpu,cpu],'Pinned endpoint mismatch')
                if i>=warm:measured.append(row)
            for column,field in [('compute_ms','compute'),('verified_call_ms','verified_call')]:
                s=stats([float(r[column]) for r in measured])
                require(abs(s['median']-float(summary[field+'_median_ms']))<.0000011,'Block median mismatch')
                if column=='compute_ms':
                    for metric in ['p95','min','max']:require(abs(s[metric]-float(summary['compute_'+metric+'_ms']))<.0000011,'Block statistic mismatch')
            phase.extend(measured)
        result.append({'phase':name,'policy':policy,'warmups_per_block':warm,'compute_ms':stats([float(r['compute_ms']) for r in phase]),'verified_call_ms':stats([float(r['verified_call_ms']) for r in phase])})
    require(pointer==len(rows),'Unconsumed samples')
    require((host/'output_last.bin').read_bytes()==Path(golden).read_bytes(),'Full golden mismatch')
    lookup={r['phase']:r for r in result}
    drift={}
    for name in ['short','long']:
        a,b=[lookup[name+'_'+s]['compute_ms']['median'] for s in ['A1','A3']]
        drift[name]={'same_process_same_base_buffers_change_percent':100*(b/a-1),'reporting_flag_over_5_percent':abs(b/a-1)>.05}
    return {'status':'PASS_CPU_AA_RECOMPUTED','total_iterations':len(rows),'measured_iterations':10*blocks*reps,'phases':result,'reuse_drift':drift,
            'interpretation':'Descriptive controls within one process and pool. Reallocation also changes copying/cache activity. No physical-page measurement or unique causal attribution.'}
