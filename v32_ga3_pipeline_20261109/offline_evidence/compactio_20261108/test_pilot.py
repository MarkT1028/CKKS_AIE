from pathlib import Path
import importlib.util,json,os,shutil,subprocess,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_compactio_20261108';B=R/'build';T=B/('pilot_'+str(time.time_ns()));T.mkdir()
spec=importlib.util.spec_from_file_location('compact_pilot_test',K/'ga3_board.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.ROOT=T
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes());(T/'SHA256SUMS_PACKAGE').write_text('LOCAL_PILOT_TEST_ONLY\n')
b.write(T/'DATA_PROVENANCE.json',dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256='a'*64))
results=[]
for num,name in enumerate(b.PROFILES):
 for order in ('descending','ascending'):
    f=T/f'{name}_{order}';f.mkdir()
    p=subprocess.run([str(B/f'model_{num}'),'unused',str(B/'synthetic'),str(f/'replay'),'pilot','1','0',order,'0'],env=dict(os.environ,V32_GA3_CACHE=str(B/'synthetic_cache')),capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    b.write(f/'identity.json',dict(variant='v32_native_pl_2_pipe',hostopt_profile=name,manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256='a'*64,compact_cache=dict(index_sha256='b'*64) if name=='packed' else None,command=[f'/test/ga3_host_native_{name}','none','data','results','pilot','1','0',order,'0']))
    for when in ('before','after'):b.write(f/f'environment_{when}.json',dict(boot_id='LOCAL_TEST_NOT_BOARD',boot_uuid=b.registry()['v32_native_pl_2_pipe']['uuid']))
    s=b.load(f/'replay/summary.json');assert s['backend']=='SOFTWARE_MODEL_NOT_HARDWARE'
    s.update(backend='XRT_PURE_PL',AIE_compute_tiles=0);b.write(f/'replay/summary.json',s)
    answer=b.summarize(f);assert answer['windows']==16 and not answer['complete_layer_raw_MAC_coverage'] and answer['review_required']
    results.append(dict(profile=name,order=order,status='PASS_SOFTWARE_AND_CONTROL_ONLY'))
b.write(B/'pilot_verification.json',dict(status='PASS_BOTH_PROFILES_BOTH_ORDERS_PILOT',cases=results,board_executed=False));print('PASS_PILOT_4_CASES')
