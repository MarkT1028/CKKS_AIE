from pathlib import Path
import contextlib,copy,hashlib,json,os,shutil,sys,tarfile,time
R=Path(__file__).resolve().parent;W=R.parents[1];K=W/'board_packages/v32_ga3_pipeline_20261109';B=R/'build'
sys.path.insert(0,str(K));import ga3_board as b;import summarize_pipeline as m;import collect_results as c
T=B/('control_'+str(time.time_ns()));T.mkdir();b.ROOT=T
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes());(T/'SHA256SUMS_PACKAGE').write_text('LOCAL_CONTROL_FIXTURE_NOT_BOARD\n')
b.write(T/'DATA_PROVENANCE.json',dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256='a'*64))
timer_keys=('code_check_ms','source_snapshot_before_ms','source_snapshot_after_ms','cache_snapshot_before_ms','cache_snapshot_after_ms','environment_before_ms','environment_after_ms','binary_identity_ms','child_process_wall_ms')

def fixture(name,profile,src,mode='probe',order='descending',seq=0):
    f=T/name;shutil.copytree(B/src,f/'replay');cfg=b.TUNINGS[profile]
    ident=dict(variant='v32_core_2_pipe',hostopt_profile=profile,tuning=cfg,manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256='a'*64,
       compact_cache=dict(index_sha256='b'*64),command=[b.binary_name('v32_core_2_pipe',profile),'none','data','results',mode,'3' if mode=='probe' else '1','1' if mode=='probe' else '0',order,'0'])
    b.write(f/'identity.json',ident)
    for when in ('before','after'):b.write(f/f'environment_{when}.json',dict(utc=f'{seq:04d}',boot_id='LOCAL_CONTROL_NOT_BOARD',boot_uuid=b.registry()['v32_core_2_pipe']['uuid']))
    b.write(f/'controller_profile.json',dict(snapshot_engine=cfg['snapshot'],timings_ms={k:1 for k in timer_keys},source_files_checked_each=5378,fresh_before_after_identities=True,skipped_output_verification=False))
    s=b.load(f/'replay/summary.json');b.write(f/'runner_timing.json',dict(runner_wall_ms=s['setup_ms']+s['campaign_wall_ms']+100))
    return f

cases=[]
def rejects(f,path,edit,label):
    original=b.load(f/path);mutated=copy.deepcopy(original);edit(mutated);b.write(f/path,mutated)
    try:b.summarize(f)
    except (ValueError,KeyError):cases.append(label)
    else:raise AssertionError('accepted '+label)
    finally:b.write(f/path,original)

for profile in b.PROFILES:
    f=fixture('probe_'+profile,profile,'probe_'+profile)
    try:b.summarize(f)
    except ValueError as e:assert 'software model' in str(e)
    else:raise AssertionError('software accepted as hardware')
    # Only isolated protocol fixtures change this label; source model logs remain intact.
    s=b.load(f/'replay/summary.json');s.update(backend='XRT_AIE',AIE_compute_tiles=2);b.write(f/'replay/summary.json',s);checked=b.summarize(f)
    assert checked['CPU_anchor_prefetch_overlap']==bool(b.TUNINGS[profile]['prefetch'])
    if b.TUNINGS[profile]['prefetch']:assert checked['review_required'] and checked['CPU_anchor_note']
    for field,value in [('complete_layer_raw_MAC_coverage',True),('verified_words',1),('admission_ms',0),('resident_window_median_sum_hardware_ms',1)]:
        rejects(f,'replay/summary.json',lambda x,k=field,v=value:x.update({k:v}),profile+':'+field)
    for field in ('full_canonical_sha256_verification','full_integer_verification','packed_input_cache'):
        rejects(f,'replay/hostopt.json',lambda x,k=field:x.update({k:not x[k]}),profile+':policy:'+field)
    for field in ('hashed_outputs','hashed_bytes','gold_read_bytes_avoided','records'):
        rejects(f,'replay/admission_profile.json',lambda x,k=field:x.update({k:0}),profile+':accounting:'+field)
    rejects(f,'identity.json',lambda x:x['tuning'].update(read_MiB=8),profile+':wrong_tuning')
    rejects(f,'identity.json',lambda x:x['command'].__setitem__(0,'wrong_binary'),profile+':wrong_binary')
    rejects(f,'controller_profile.json',lambda x:x['timings_ms'].pop('source_snapshot_after_ms'),profile+':missing_timing')
    rejects(f,'controller_profile.json',lambda x:x.update(skipped_output_verification=True),profile+':verification_skipped')
    rejects(f,'controller_profile.json',lambda x:x.update(fresh_before_after_identities=False),profile+':cached_identity')
    rejects(f,'runner_timing.json',lambda x:x.update(runner_wall_ms=0),profile+':invalid_total_time')
    if profile!='baseline':
        for field,value in [('read_chunk_bytes',8*2**20),('prefetch_enabled',not bool(b.TUNINGS[profile]['prefetch'])),('prefetched_records',1000),('prefetch_wait_ms',-1)]:
            rejects(f,'replay/io_tuning.json',lambda x,k=field,v=value:x.update({k:v}),profile+':'+field)

for variant in b.VARIANTS[1:]:
    for profile in b.PROFILES:
        f=fixture('protocol_'+variant+'_'+profile,profile,'probe_'+profile)
        ident=b.load(f/'identity.json');ident.update(variant=variant);ident['command'][0]=b.binary_name(variant,profile);b.write(f/'identity.json',ident)
        for when in ('before','after'):b.write(f/f'environment_{when}.json',dict(utc='0000',boot_id='LOCAL_CONTROL_NOT_BOARD',boot_uuid=b.registry()[variant]['uuid']))
        s=b.load(f/'replay/summary.json');s.update(backend='XRT_PURE_PL',AIE_compute_tiles=0);b.write(f/'replay/summary.json',s);b.summarize(f)
        rejects(f,'replay/summary.json',lambda x:x.update(AIE_compute_tiles=2),variant+':'+profile+':wrong_compute_identity')

# Same-boot/profile/cache/order nearest baseline anchors, no cross-order mixing.
for seq,(profile,total,order) in enumerate([('baseline',100000,'ascending'),('combined',80000,'ascending'),('guard',90000,'ascending'),('baseline',100100,'ascending'),('combined',10000,'descending')]):
    f=fixture('results_ga3_'+str(seq),profile,'pilot_'+profile+'_ascending','pilot',order,seq)
    s=b.load(f/'replay/summary.json');s.update(backend='XRT_AIE',AIE_compute_tiles=2);b.write(f/'replay/summary.json',s)
    b.write(f/'runner_timing.json',dict(runner_wall_ms=total));b.write(f/'status.json',dict(status='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN'))
m.main();screen=b.load(T/'pipeline_screen_summary.json');assert len(screen['comparisons'])==2
assert {x['profile'] for x in screen['comparisons']}=={'combined','guard'}
assert all(x['baseline_runner_ms']==100050 and x['review_required'] and not x['complete_layer_raw_MAC_coverage'] and x['CUDA_speedup'].startswith('NOT_ESTABLISHED') for x in screen['comparisons'])
for name in ('BASELINE_PROVENANCE.json','IO_BASELINE_PROVENANCE.json','OPTIMIZATION_PLAN.json','GPU_REFERENCE.json','BUILD_IDENTITY.json','OFFLINE_VERIFICATION.json','HARDWARE_PROVENANCE.json','SOURCE_PROVENANCE.json','COMPACT_BASELINE_PROVENANCE.json','PIPELINE_BASELINE_PROVENANCE.json','CUDA_TARGET_ASSESSMENT.json'):
    b.write(T/name,dict(scope='LOCAL_CONTROL_NOT_BOARD'))
b.board=lambda:None;b.lock=contextlib.nullcontext;c.main();archive=next(T.glob('collected_ga3_pipeline_*.tar.gz'))
with tarfile.open(archive,'r:gz') as tf:entries={x.name:tf.extractfile(x).read() for x in tf}
idx=json.loads(entries['COLLECTION_INDEX.json']);assert not idx['review_required_folders'];assert len(entries)==len(idx['entries'])+1
assert all(hashlib.sha256(entries[e['path']]).hexdigest()==e['sha256'] for e in idx['entries'])
b.write(B/'control_verification.json',dict(status='PASS_SIX_TUNING_PROTOCOL_MUTATIONS_MATCHED_ANCHORS_COLLECTION',rejected_cases=cases,collection_members=len(entries),board_executed=False))
print('PASS_PIPELINE_CONTROLLER',len(cases),'mutations',len(entries),'archive members')
