from pathlib import Path
import copy,csv,hashlib,importlib.util,json,shutil,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_hostopt_20261108'
T=R/'build'/('control_'+str(time.time_ns()));T.mkdir()
spec=importlib.util.spec_from_file_location('hostopt_control',K/'ga3_board.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.ROOT=T
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes())
(T/'SHA256SUMS_PACKAGE').write_text('synthetic protocol validation only\n')
data_sha=hashlib.sha256(b'test-only').hexdigest();code_sha=b.sha(T/'SHA256SUMS_PACKAGE')
(T/'DATA_PROVENANCE.json').write_text(json.dumps(dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256=data_sha)))
records=[]
for profile,name in enumerate(b.PROFILES):
    folder=T/name;folder.mkdir();shutil.copytree(R/f'build/final_synthetic_probe_{profile}',folder/'replay')
    ident=dict(variant='v32_core_2_pipe',hostopt_profile=name,manifest_sha256=code_sha,data_manifest_sha256=data_sha,command=[f'/synthetic/bin/ga3_host_aie_{name}','synthetic.xclbin','data','result','probe','3','1','descending','0'])
    (folder/'identity.json').write_text(json.dumps(ident))
    for fn in ('environment_before.json','environment_after.json'):(folder/fn).write_text(json.dumps(dict(boot_id='test-boot',boot_uuid=b.registry()['v32_core_2_pipe']['uuid'])))
    try:b.summarize(folder)
    except ValueError as e:assert 'software model' in str(e)
    else:raise AssertionError('model passed as actual hardware')
    sp=folder/'replay/summary.json';s=json.loads(sp.read_text());s['backend']='XRT_AIE';s['AIE_compute_tiles']=2;sp.write_text(json.dumps(s))
    answer=b.summarize(folder);assert answer['windows']==16 and not answer['complete_layer_raw_MAC_coverage'] and answer['review_required']
    cases=[('subset_as_full',lambda q:q.update(complete_layer_raw_MAC_coverage=True)),('wrong_words',lambda q:q.update(verified_words=q['verified_words']+1)),('wrong_backend',lambda q:q.update(backend='XRT_PURE_PL')),('wrong_window_sum',lambda q:q.update(resident_window_median_sum_hardware_ms=q['resident_window_median_sum_hardware_ms']+1))]
    for label,change in cases:
        q=copy.deepcopy(s);change(q);sp.write_text(json.dumps(q))
        try:b.summarize(folder)
        except ValueError:records.append(dict(profile=name,case=label,status='REJECTED'))
        else:raise AssertionError(label)
    sp.write_text(json.dumps(s));hp=folder/'replay/hostopt.json';hp_original=hp.read_text();q=json.loads(hp_original);q['profile']='burst' if name!='burst' else 'cacheable';hp.write_text(json.dumps(q))
    try:b.summarize(folder)
    except ValueError:records.append(dict(profile=name,case='profile_mismatch',status='REJECTED'))
    else:raise AssertionError('profile mismatch accepted')
    hp.write_text(hp_original)
    samples=folder/'replay/samples.csv';original=samples.read_text();samples.write_text('\n'.join(original.splitlines()[:-1])+'\n')
    try:b.summarize(folder)
    except ValueError:records.append(dict(profile=name,case='missing_sample',status='REJECTED'))
    else:raise AssertionError('missing sample accepted')
    samples.write_text(original);b.summarize(folder)
receipt=dict(status='PASS_HOSTOPT_MODEL_REJECTION_SUBSET_COORDINATES_PROFILES_AND_MUTATIONS',valid_profiles=list(b.PROFILES),negative_cases=records,software_model_only=True,board_executed=False)
(R/'build/control_verification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt['status'])
