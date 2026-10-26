#!/usr/bin/env python3
"""Preparation/validation suite. Firmware switches remain explicit guarded commands."""
from pathlib import Path
import argparse,csv,json,os,platform,shutil,subprocess,sys,tempfile
import validation_common as v
from cpu_aa_analysis import analyze_case
ROOT=v.ROOT
def build():
    v.check_package();v.board_check()
    with v.BoardLock():
        # Original formal binaries retain the original E8 package identity.
        v.formal.build('all')
        bin_dir=ROOT/'bin';bin_dir.mkdir(exist_ok=True)
        compiler=subprocess.check_output(['g++','--version'],text=True)
        specs=[('cpu_aa',ROOT/'diagnostics/cpu_aa.cpp',[],list((ROOT/'diagnostics').rglob('*.hpp'))+[ROOT/'diagnostics/cpu_reference.inc',ROOT/'comparison/cpu/cpu_bench.cpp']),
               ('profile_host_diag_2_pipe',ROOT/'profile_host/perf_host.cpp',['-lxrt_coreutil'],list((ROOT/'profile_host').glob('*.hpp')))]
        for name,source,libs,headers in specs:
            with tempfile.TemporaryDirectory(prefix='build_',dir=bin_dir) as td:
                temporary=Path(td)/name
                v.formal.logged(['g++',*v.FLAGS,source,*libs,'-o',temporary],bin_dir/(name+'.compile.log'))
                if name=='cpu_aa':v.formal.logged([temporary,'--self-test'],bin_dir/'cpu_aa_selftest.log')
                linked=v.formal.logged(['ldd',temporary],bin_dir/(name+'.ldd.log'))
                destination=bin_dir/name;os.replace(temporary,destination)
                v.write_json(bin_dir/(name+'.build.json'),{'name':name,'built_at_utc':v.stamp(),'architecture':platform.machine(),
                    'compiler_version':compiler,'flags':v.FLAGS,'libraries':libs,'binary_sha256':v.sha(destination),
                    'package_manifest_sha256':v.sha(ROOT/'SHA256SUMS_PACKAGE'),
                    'source_files':{p.relative_to(ROOT).as_posix():v.sha(p) for p in sorted([source,*headers])},'linked_libraries':linked,
                    'scope':'diagnostic_only_not_formal_performance'})
                print('BUILD_READY='+str(destination),flush=True)
    print('BUILD_READY_ALL: self-tests only; no PL/AIE execution, boot write, register change or reboot.')
def repeat(variant,selection):
    v.check_package();v.board_check()
    prior=json.loads((ROOT/'references/a1_b1_identity.json').read_text())
    old=next(x for x in prior['formal_runs'] if x['variant']==variant)
    expected=(v.COMPARISON/'variants'/variant/'EXPECTED_BOOT_UUID').read_text().strip()
    v.require(v.boot_uuid()==expected,'BOOT_MISMATCH: switch and reboot to '+variant+' first')
    if selection=='formal':v.require(v.snapshot()['boot_id']!=old['boot_id'],'Need a different boot from the recorded A1/B1; relabeling is insufficient')
    suffix='A2' if variant=='raw_2_pipe' else 'B2';label=suffix if selection=='formal' else 'smoke_'+suffix
    reps=30 if selection=='formal' else 1
    # Child takes the same global BoardLock and maintains its unchanged identity.
    rc=subprocess.call([sys.executable,str(v.COMPARISON/'controlled_board.py'),'run',variant,str(reps),label,'reverse'])
    v.require(rc==0,'Repeat failed; preserve the entire child result directory')
def fresh(variant,label):
    package=v.check_package();v.board_check();v.require(v.re.fullmatch(r'[A-Za-z0-9_-]{1,32}',label),'Use short ASCII label')
    expected=(v.COMPARISON/'variants'/variant/'EXPECTED_BOOT_UUID').read_text().strip()
    v.require(v.boot_uuid()==expected,'BOOT_MISMATCH; no fresh case started')
    record=v.formal.binary_record('perf_host_'+variant)
    registry=json.loads((ROOT/'fresh_fixtures/registry.json').read_text())
    with v.BoardLock():
        result=Path(tempfile.mkdtemp(prefix=f'results_fresh_{variant}_{label}_',dir=ROOT))
        meta={'schema':'ckks_fresh_board_v1','status':'RUNNING','variant':variant,'package':package,'board_run':True,
              'formal_build':record,'started_at_utc':v.stamp(),'environment_before':v.snapshot(),'repetitions':1,'warmups':1,
              'scope':'new_encrypted_fixture_correctness_not_formal_timing','secret_keys_on_board':False,'cases':[]}
        def save():v.write_json(result/'experiment.json',meta)
        save();print('FRESH_RESULTS='+str(result),flush=True)
        try:
            for spec in registry['cases']:
                directory=ROOT/'fresh_fixtures'/spec['id'];inputs=directory/'inputs.bin';golden=directory/'expected_raw.bin'
                v.require(v.sha(inputs)==spec['inputs_sha256'] and v.sha(golden)==spec['expected_sha256'],'Fixture identity mismatch')
                for mode in ['resident','transfer']:
                    v.require(v.boot_uuid()==expected,'Boot changed')
                    case=result/(spec['id']+'_'+mode);case.mkdir()
                    ini=case/'xrt.ini';ini.write_text('[Debug]\naie_profile=false\naie_trace=false\nprofile=false\nnative_xrt_trace=false\n')
                    env=v.environment();env['XRT_INI_PATH']=str(ini)
                    command=[v.COMPARISON/'bin'/('perf_host_'+variant),v.COMPARISON/'variants'/variant/'ckks_hw_boot.xclbin',inputs,golden,case/'host',1,1,mode,'run']
                    before=v.snapshot()
                    with v.Telemetry(case/'telemetry.jsonl'):log=v.logged(command,case,env,600)
                    v.require('PASS FULL_MAC' in log,'Missing hardware correctness marker')
                    output=case/'host/output_last.bin';v.require(output.read_bytes()==golden.read_bytes(),'Fresh full output mismatch')
                    item={'id':spec['id'],'K':spec['K'],'mode':mode,'path':case.name,'status':'PASS','output_sha256':v.sha(output),
                          'inputs_sha256':spec['inputs_sha256'],'expected_sha256':spec['expected_sha256'],
                          'environment_before':before,'environment_after':v.snapshot()}
                    v.write_json(case/'case.json',item);meta['cases'].append(item);save()
            meta.update(status='PASS_ALL_8_FRESH_HARDWARE_CASES',completed_at_utc=v.stamp(),environment_after=v.snapshot());save()
            (result/'STATUS.txt').write_text(meta['status']+'\n');print('DOWNLOAD_ENTIRE_RESULTS='+str(result),flush=True)
        except BaseException as error:
            meta.update(status='FAIL_STOPPED',error=str(error),environment_after=v.snapshot());save();(result/'STATUS.txt').write_text('FAIL_STOPPED\n');raise
def cpu_aa(preset,label):
    package=v.check_package();v.board_check();v.require(v.re.fullmatch(r'[A-Za-z0-9_-]{1,32}',label),'Use short ASCII label')
    build=v.binary_record('cpu_aa');cpus=sorted(os.sched_getaffinity(0))[:2]
    v.require(len(cpus)==2,'CPU A/A requires two allowed CPU cores')
    settings={'quick':(3,2,1,3),'full':(20,3,3,30)}
    reps,blocks,sw,lw=settings[preset];inputs,golden=v.fixtures(16)
    with v.BoardLock():
        result=Path(tempfile.mkdtemp(prefix=f'results_cpu_aa_{preset}_{label}_',dir=ROOT))
        meta={'schema':'ckks_cpu_aa_board_v1','status':'RUNNING','package':package,'board_run':True,'build':build,
              'started_at_utc':v.stamp(),'environment_before':v.snapshot(),'K':16,'repetitions_per_block':reps,
              'blocks_per_phase':blocks,'short_warmups_per_block':sw,'long_warmups_per_block':lw,
              'phase_order':'reuse-copy-reuse-reallocate-reuse, then repeat with long warmups',
              'scope':'diagnostic_cpu_only_no_PL_execution_not_formal_CPU_HW_comparison','cases':[]}
        def save():v.write_json(result/'experiment.json',meta)
        save();print('CPU_AA_RESULTS='+str(result),flush=True)
        try:
            for name,targets in [('pinned_t1_c0',[cpus[0]]),('pinned_t1_c1',[cpus[1]]),('pinned_t2_c01',cpus)]:
                case=result/name;case.mkdir();before=v.snapshot()
                command=[ROOT/'bin/cpu_aa',inputs,golden,case/'host',len(targets),','.join(map(str,targets)),reps,blocks,sw,lw,'run']
                with v.Telemetry(case/'telemetry.jsonl'):log=v.logged(command,case,v.environment(),600)
                v.require('PASS CPU_AA_ALL_PHASES' in log,'Missing A/A success marker')
                analysis=analyze_case(case/'host',golden,targets,reps,blocks,sw,lw);v.write_json(case/'recomputed.json',analysis)
                item={'path':name,'threads':len(targets),'target_cpus':targets,'status':'PASS','output_sha256':v.sha(case/'host/output_last.bin'),
                      'environment_before':before,'environment_after':v.snapshot()}
                v.write_json(case/'case.json',item);meta['cases'].append(item);save()
            meta.update(status='PASS_CPU_AA_ALL_3_AFFINITY_CASES',completed_at_utc=v.stamp(),environment_after=v.snapshot());save()
            (result/'STATUS.txt').write_text(meta['status']+'\n');print('DOWNLOAD_ENTIRE_RESULTS='+str(result),flush=True)
        except BaseException as error:
            meta.update(status='FAIL_STOPPED',error=str(error),environment_after=v.snapshot());save();(result/'STATUS.txt').write_text('FAIL_STOPPED\n');raise
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ['check','detect','build']:sub.add_parser(name)
    q=sub.add_parser('repeat');q.add_argument('variant',choices=v.VARIANTS);q.add_argument('selection',choices=['smoke','formal'])
    q=sub.add_parser('fresh');q.add_argument('variant',choices=v.VARIANTS);q.add_argument('label',nargs='?',default='fresh1')
    q=sub.add_parser('cpu-aa');q.add_argument('preset',choices=['quick','full']);q.add_argument('label',nargs='?',default='AA1')
    a=p.parse_args()
    if a.command=='check':print(json.dumps(v.check_package(),indent=2));return
    if a.command=='detect':
        v.check_package();v.board_check();actual=v.boot_uuid()
        print(json.dumps({'boot_uuid':actual,'matching_variants':[x for x in v.VARIANTS if (v.COMPARISON/'variants'/x/'EXPECTED_BOOT_UUID').read_text().strip()==actual],'environment':v.snapshot()},indent=2));return
    if a.command=='build':build()
    elif a.command=='repeat':repeat(a.variant,a.selection)
    elif a.command=='fresh':fresh(a.variant,a.label)
    elif a.command=='cpu-aa':cpu_aa(a.preset,a.label)
if __name__=='__main__':
    try:main()
    except Exception as error:print('FAIL: '+str(error),file=sys.stderr);sys.exit(1)
