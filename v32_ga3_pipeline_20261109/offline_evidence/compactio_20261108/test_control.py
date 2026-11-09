from pathlib import Path
import importlib.util,json,shutil,sys,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_compactio_20261108';B=R/'build';T=B/('control_'+str(time.time_ns()));T.mkdir()
sys.path.insert(0,str(K))
spec=importlib.util.spec_from_file_location('compact_test_board',K/'ga3_board.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.ROOT=T
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes())
(T/'SHA256SUMS_PACKAGE').write_text('isolated control tests only\n')
b.write(T/'DATA_PROVENANCE.json',dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256='a'*64))
cases=[]
for name,src in [('sha256','raw_probe'),('packed','packed_probe')]:
    f=T/name;f.mkdir();shutil.copytree(B/src,f/'replay')
    ident=dict(variant='v32_core_2_pipe',hostopt_profile=name,manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256='a'*64,
        compact_cache=dict(index_sha256='b'*64) if name=='packed' else None,
        command=[f'/test/bin/ga3_host_aie_{name}','test.xclbin','data','result','probe','3','1','ascending','0'])
    b.write(f/'identity.json',ident)
    for when in ('before','after'):b.write(f/f'environment_{when}.json',dict(boot_id='CONTROL_FIXTURE_NOT_BOARD',boot_uuid=b.registry()['v32_core_2_pipe']['uuid']))
    path=f/'replay/summary.json';original=b.load(path)
    try:b.summarize(f)
    except ValueError as e:assert 'software model' in str(e)
    else:raise AssertionError('software accepted as hardware')
    valid=dict(original,backend='XRT_AIE',AIE_compute_tiles=2);b.write(path,valid);b.summarize(f)
    for label,update in [('fake_full',dict(complete_layer_raw_MAC_coverage=True)),('wrong_words',dict(verified_words=1)),('wrong_admission',dict(admission_ms=0)),('wrong_time',dict(resident_window_median_sum_hardware_ms=1))]:
        b.write(path,dict(valid,**update))
        try:b.summarize(f)
        except ValueError:cases.append(name+':'+label)
        else:raise AssertionError(label)
    b.write(path,valid)
    policy=f/'replay/hostopt.json';save=b.load(policy)
    for field in ('full_canonical_sha256_verification','full_integer_verification','packed_input_cache'):
        b.write(policy,dict(save,**{field:not save[field]}))
        try:b.summarize(f)
        except ValueError:cases.append(name+':policy:'+field)
        else:raise AssertionError(field)
    b.write(policy,save)
    ad=f/'replay/admission_profile.json';save=b.load(ad)
    for field in ('hashed_outputs','hashed_bytes','gold_read_bytes_avoided','records'):
        b.write(ad,dict(save,**{field:0}))
        try:b.summarize(f)
        except ValueError:cases.append(name+':accounting:'+field)
        else:raise AssertionError(field)
    b.write(ad,save)
    b.write(f/'runner_timing.json',dict(runner_wall_ms=0))
    try:b.summarize(f)
    except ValueError:cases.append(name+':invalid_total_runner_time')
    else:raise AssertionError('invalid runner')
    b.write(f/'runner_timing.json',dict(runner_wall_ms=valid['setup_ms']+valid['campaign_wall_ms']+10));b.summarize(f)
spec=importlib.util.spec_from_file_location('compact_summary_test',K/'summarize_compact.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
a=m.compare([1000,1000],[800,800],1000);assert not a['first_use_improves'] and a['break_even_requests']==6
assert m.compare([1000],[1100],100)['break_even_requests'] is None
assert m.compare([1000],[800],0)['first_use_improves']
b.write(B/'control_verification.json',dict(status='PASS_PROTOCOL_COVERAGE_BYTE_TIMING_MUTATIONS_AND_AMORTIZATION',cases=cases,board_executed=False));print('PASS_COMPACT_CONTROL',len(cases))
