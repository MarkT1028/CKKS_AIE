from pathlib import Path
import copy, importlib.util, json, shutil, time

R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_ioopt_20261108';B=R/'build';T=B/('control_'+str(time.time_ns()));T.mkdir()
spec=importlib.util.spec_from_file_location('control_ioopt',K/'ga3_board.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.ROOT=T
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes())
(T/'SHA256SUMS_PACKAGE').write_text('isolated schema mutation test only\n')
(T/'DATA_PROVENANCE.json').write_text(json.dumps(dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256='a'*64)))
cases=[]
for index,name in enumerate(b.PROFILES):
    folder=T/name;folder.mkdir();shutil.copytree(B/f'final_probe_{index}',folder/'replay')
    ident=dict(variant='v32_core_2_pipe',hostopt_profile=name,manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256='a'*64,
        command=[f'/test/bin/ga3_host_aie_{name}','test.xclbin','data','result','probe','3','1','ascending','0'])
    (folder/'identity.json').write_text(json.dumps(ident))
    for when in ('before','after'):(folder/f'environment_{when}.json').write_text(json.dumps(dict(boot_id='unit-test',boot_uuid=b.registry()['v32_core_2_pipe']['uuid'])))
    summary=folder/'replay/summary.json';original=json.loads(summary.read_text())
    try:b.summarize(folder)
    except ValueError as e:assert 'software model' in str(e)
    else:raise AssertionError('software model passed as board execution')
    valid=dict(original,backend='XRT_AIE',AIE_compute_tiles=2)
    summary.write_text(json.dumps(valid));answer=b.summarize(folder)
    assert answer['verification_protocol']==('FULL_CANONICAL_SHA256' if index==2 else 'FULL_CANONICAL_WORD_COMPARE')
    assert not answer['complete_layer_raw_MAC_coverage']
    for label,update in [('subset_as_full',dict(complete_layer_raw_MAC_coverage=True)),('wrong_words',dict(verified_words=1)),
                        ('wrong_timing',dict(resident_window_median_sum_hardware_ms=1)),('wrong_admission',dict(admission_ms=0))]:
        summary.write_text(json.dumps(dict(valid,**update)))
        try:b.summarize(folder)
        except ValueError:cases.append(dict(profile=name,case=label,status='REJECTED'))
        else:raise AssertionError(label)
    summary.write_text(json.dumps(valid))
    policy=folder/'replay/hostopt.json';backup=policy.read_text();bad=json.loads(backup);bad['full_integer_verification']=not bad['full_integer_verification'];policy.write_text(json.dumps(bad))
    try:b.summarize(folder)
    except ValueError:cases.append(dict(profile=name,case='wrong_verification_protocol',status='REJECTED'))
    else:raise AssertionError('wrong protocol passed')
    policy.write_text(backup)
    if index==2:
        ap=folder/'replay/admission_profile.json';saved=ap.read_text()
        for field in ('hashed_outputs','hashed_bytes','gold_read_bytes_avoided'):
            bad=json.loads(saved);bad[field]=0;ap.write_text(json.dumps(bad))
            try:b.summarize(folder)
            except ValueError:cases.append(dict(profile=name,case='missing_'+field,status='REJECTED'))
            else:raise AssertionError(field)
        ap.write_text(saved)
    b.summarize(folder)
(B/'control_verification.json').write_text(json.dumps(dict(status='PASS_IOOPT_CONTROL_PROTOCOL_COVERAGE_MUTATIONS',cases=cases,board_executed=False),indent=2)+'\n')
print('PASS_IOOPT_CONTROL_PROTOCOL_COVERAGE_MUTATIONS',len(cases))
