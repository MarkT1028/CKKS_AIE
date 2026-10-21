#!/usr/bin/env python3
"""Compare saved raw_2_pipe board results with validated raw_2_full results.

Only complete, profiling-disabled suites with >=30 measured repetitions qualify.
The bundled default reference is historical data from 2026-10-19, not a new run.
"""
from pathlib import Path
import argparse,configparser,csv,hashlib,json,math,re,statistics,sys

ROOT=Path(__file__).resolve().parent
CASES=[(1,'resident'),(1,'transfer'),(16,'resident'),(16,'transfer')]
PHASES=['upload_ms','poison_ms','execution_ms','status_ms','readback_ms','merge_ms','validation_ms']

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def readcsv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def hashes(text):
    result={}
    for line in text.splitlines():
        m=re.match(r'^([a-f0-9]{64})\s+\*?(.*)$',line)
        if m:
            name=m[2].replace('\\','/').rsplit('/',1)[-1]
            require(name not in result or result[name]==m[1],'Conflicting hash records: '+name)
            result[name]=m[1]
    return result

def finite(row,key):
    value=float(row[key]);require(math.isfinite(value) and value>=0,'Invalid timing: '+key)
    return value

def load_suite(folder,variant,fixtures):
    folder=folder.resolve()
    require(folder.is_dir(),'Result folder missing: '+str(folder))
    require((folder/'STATUS.txt').read_text().strip()=='PASS_ALL_REQUESTED_CASES','Suite did not finish all requested cases')
    expected_manifest=json.loads((ROOT/'variants'/variant/'manifest.json').read_text())
    manifest=json.loads((folder/'variant_manifest.json').read_text())
    for key in ['xclbin_uuid_hex','candidate_sha256','metadata_sha256']:
        require(manifest[key]==expected_manifest[key],'Hardware identity mismatch: '+variant+' '+key)
    recorded=hashes((folder/'fixture_sha256.txt').read_text())
    for name in ['inputs.bin','expected_raw.bin','inputs_k16.bin','expected_k16_raw.bin']:
        require(recorded.get(name)==sha(fixtures/name),'Fixture mismatch: '+name)
    build=(folder/'host_build.txt').read_text()
    source_hashes=hashes(build)
    for name in ['perf_host.cpp','timed_base.hpp','expected_reader.hpp','variant_config.hpp']:
        require(source_hashes.get(name)==sha(ROOT/'variants'/variant/'host'/name),'Host source mismatch: '+name)
    require('COMPILE_FLAGS=-std=c++17 -O3 -Wall -Wextra -pthread; XRT ABI checks enabled' in build,'Unexpected host build flags')
    compiler=re.search(r'^g\+\+.*$',build,re.M)
    require(compiler is not None,'Compiler version record missing')
    env=(folder/'board_env.txt').read_text()
    require('aarch64' in env,'Expected board ARM environment record')
    known_uuid=folder/'boot_uuid.txt'
    if known_uuid.exists():require(known_uuid.read_text().strip()==manifest['xclbin_uuid_hex'],'Recorded running UUID mismatch')
    actual_cases={p.parent.parent.name for p in folder.glob('k*/host/summary.csv')}
    require(actual_cases=={'k1_resident','k1_transfer','k16_resident','k16_transfer'},'Expected exactly four K/mode cases')
    result={}
    for k,mode in CASES:
        case=folder/f'k{k}_{mode}';host=case/'host'
        summaries=readcsv(host/'summary.csv');require(len(summaries)==1,'Expected one summary row')
        s=summaries[0]
        for field,value in [('variant',variant),('K',str(k)),('mode',mode),('cores','2'),('topology','split'),('format','raw'),('scope','raw_ckks_mac')]:
            require(s.get(field)==value,'Case identity/scope mismatch: '+field)
        n,w=int(s['repetitions']),int(s['warmups'])
        require(30<=n<=10000 and w==3,'Use formal runs with >=30 measured repetitions and three warmups')
        ini=configparser.ConfigParser();ini.read(case/'xrt.ini')
        require(ini.has_section('Debug') and ini.getboolean('Debug','aie_profile') is False and ini.getboolean('Debug','aie_trace') is False,'Profiling must be disabled')
        log=(case/'host.log').read_text()
        require('PASS FULL_MAC' in log and 'FAIL' not in log and f'variant={variant}' in log,'Host log is not a full passing MAC run')
        rows=readcsv(host/'iterations.csv')
        require(len(rows)==n+w,'Iteration count mismatch')
        measured=[]
        for i,row in enumerate(rows):
            require(int(row['repetition'])==i and int(row['warmup'])==int(i<w),'Repetition/warmup sequence mismatch')
            require(row['variant']==variant and row['K']==str(k) and row['mode']==mode,'Iteration identity mismatch')
            require(int(row['verified_words'])==73728,'Not every raw residue was verified')
            values={key:finite(row,key) for key in PHASES+['transaction_ms','launch_ms']}
            require(values['execution_ms']>0 and values['launch_ms']<=values['execution_ms']+0.000002,'Invalid execution/launch timing')
            require(abs(sum(values[key] for key in PHASES)-values['transaction_ms'])<=0.000010,'Transaction phase accounting mismatch')
            if i>=w:measured.append(values)
        for key in ['execution_ms','transaction_ms','validation_ms']:
            med=statistics.median(row[key] for row in measured)
            require(abs(med-float(s[key.replace('_ms','_median_ms')]))<=0.0000011,'Summary median mismatch: '+key)
        execution=sorted(row['execution_ms'] for row in measured)
        for field,value in [('execution_p95_ms',execution[math.ceil(.95*n)-1]),('execution_min_ms',execution[0]),('execution_max_ms',execution[-1])]:
            require(abs(value-float(s[field]))<=0.0000011,'Summary distribution mismatch: '+field)
        expected=fixtures/('expected_raw.bin' if k==1 else 'expected_k16_raw.bin')
        require((host/'output_last.bin').read_bytes()==expected.read_bytes(),'Saved full output differs from golden')
        session=dict(line.split('=',1) for line in (host/'session.txt').read_text().splitlines() if '=' in line)
        for key,value in [('variant',variant),('N','8192'),('L','3'),('K',str(k)),('mode',mode),('cores','2'),('repetitions',str(n)),('warmups','3')]:
            require(session.get(key)==value,'Session metadata mismatch: '+key)
        result[(k,mode)]={'n':n,'execution':statistics.median(row['execution_ms'] for row in measured),
            'transaction':statistics.median(row['transaction_ms'] for row in measured),'p95':execution[math.ceil(.95*n)-1],
            'summary':str(host/'summary.csv'),'session_epoch_ns':session.get('session_start_epoch_ns','')}
    historical=(folder/'REFERENCE_INFO.json').exists()
    return result,{'directory':str(folder),'variant':variant,'historical_bundled_reference':historical,
        'compiler':compiler[0],'board_environment':env,'boot_uuid':manifest['xclbin_uuid_hex'],
        'host_source_sha256':{name:source_hashes[name] for name in ['perf_host.cpp','timed_base.hpp','expected_reader.hpp']}}

def compare(reference,candidate,fixtures):
    old,oldmeta=load_suite(reference,'raw_2_full',fixtures)
    new,newmeta=load_suite(candidate,'raw_2_pipe',fixtures)
    require(oldmeta['compiler']==newmeta['compiler'],'Compiler versions differ; collect a matched reference')
    require(oldmeta['host_source_sha256']==newmeta['host_source_sha256'],'Host timing/validation implementations differ')
    result=[]
    for k,mode in CASES:
        a,b=old[(k,mode)],new[(k,mode)]
        require(a['n']==b['n'],'Reference and candidate measured repetition counts differ')
        result.append({'K':k,'mode':mode,'reference_variant':'raw_2_full','candidate_variant':'raw_2_pipe',
            'repetitions_each':a['n'],'reference_is_historical':oldmeta['historical_bundled_reference'],
            'reference_execution_ms':a['execution'],'candidate_execution_ms':b['execution'],
            'execution_speedup':a['execution']/b['execution'],
            'execution_time_reduction_percent':100*(1-b['execution']/a['execution']),
            'reference_transaction_ms':a['transaction'],'candidate_transaction_ms':b['transaction'],
            'transaction_speedup':a['transaction']/b['transaction'],
            'reference_execution_p95_ms':a['p95'],'candidate_execution_p95_ms':b['p95'],
            'reference_summary':a['summary'],'candidate_summary':b['summary']})
    return result,{'status':'VALIDATED_SAVED_BOARD_RESULTS','reference':oldmeta,'candidate':newmeta,
        'comparison_scope':'Raw CKKS MAC; execution includes launch and waiting. No CPU comparison or decryption timing.',
        'historical_reference_caveat':'Bundled reference was measured on 2026-10-19. It is not a same-day interleaved A/B experiment. Review frequency/temperature/environment before causal conclusions.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate',type=Path)
    p.add_argument('--reference',type=Path,default=ROOT/'reference_results_20261019')
    p.add_argument('--fixtures',type=Path,default=ROOT/'fixtures')
    p.add_argument('--output',type=Path,default=Path('comparison_reducer.csv'))
    a=p.parse_args();sidecar=a.output.with_suffix('.json')
    require(not a.output.exists() and not sidecar.exists(),'Choose a new output path; existing comparisons are preserved')
    rows,meta=compare(a.reference,a.candidate,a.fixtures)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    meta['cases']=rows;sidecar.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: four complete, profile-disabled raw MAC cases validated.')
    if meta['reference']['historical_bundled_reference']:
        print('REFERENCE: historical board measurements from 2026-10-19; no new reference run was performed.')
    print('COMPARISON_CSV='+str(a.output));print('COMPARISON_METADATA='+str(sidecar))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,configparser.Error) as e:
        print('REFUSED_COMPARISON: '+str(e),file=sys.stderr);sys.exit(2)
