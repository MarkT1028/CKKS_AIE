"""Isolated protocol fixtures, explicitly not real board output."""
from pathlib import Path
import contextlib,copy,csv,hashlib,json,shutil,sys,tarfile,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_splitbo_20261109';B=R/'build'
sys.path.insert(0,str(K));import ga3_board as b;import collect_results as c
T=B/('control_'+str(time.time_ns()));T.mkdir();b.ROOT=T
v=b.load(K/'WINDOW_VARIANTS.json');v['v32_native_splitbo_2_pipe']=dict(uuid='0'*31+'1',execution_backend='XRT_PURE_PL',AIE_compute_tiles=0);b.write(T/'WINDOW_VARIANTS.json',v)
(T/'SHA256SUMS_PACKAGE').write_text('LOCAL_ONLY_PROTOCOL_NOT_BOARD\n')
b.write(T/'DATA_PROVENANCE.json',dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256='a'*64))
timer_keys=('code_check_ms','source_snapshot_before_ms','source_snapshot_after_ms','cache_snapshot_before_ms','cache_snapshot_after_ms','environment_before_ms','environment_after_ms','binary_identity_ms','child_process_wall_ms')
cases=[]
def fixture(variant,profile):
 f=T/f'results_ga3_LOCAL_{variant}_{profile}';shutil.copytree(B/'probe_guard',f/'replay');cfg=b.TUNINGS[profile]
 ident=dict(variant=variant,hostopt_profile=profile,tuning=cfg,manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256='a'*64,compact_cache=dict(index_sha256='b'*64),command=[b.binary_name(variant,profile),'x','d','r','probe','3','1','descending','0'])
 b.write(f/'identity.json',ident)
 for x in ('before','after'):b.write(f/f'environment_{x}.json',dict(utc='LOCAL',boot_id='LOCAL_PROTOCOL_NOT_BOARD',boot_uuid=v[variant]['uuid']))
 b.write(f/'controller_profile.json',dict(snapshot_engine=cfg['snapshot'],timings_ms={k:1 for k in timer_keys},source_files_checked_each=5378,fresh_before_after_identities=True,skipped_output_verification=False))
 s=b.load(f/'replay/summary.json');b.write(f/'runner_timing.json',dict(runner_wall_ms=s['setup_ms']+s['campaign_wall_ms']+100))
 try:b.summarize(f)
 except ValueError as e:assert 'software model' in str(e)
 else:raise AssertionError('model accepted as hardware')
 s.update(backend=v[variant]['execution_backend'],AIE_compute_tiles=v[variant]['AIE_compute_tiles']);b.write(f/'replay/summary.json',s)
 if variant=='v32_native_splitbo_2_pipe':
  refresh=profile=='refresh';b.write(f/'replay/split_bo.json',dict(protocol='separate_canonical_AB_v1',copy_and_sync_inside_resident_trial=True,refresh_each_trial=refresh))
  p=f/'replay/samples.csv';rows=list(csv.DictReader(p.open()));last=None
  for x in rows:
   if x['phase']!='hardware':continue
   size=8192*int(x['L'])*16*2*8;key=(x['tower_start'],x['coefficient_start']);count=5 if refresh or (int(x['repetition'])==0 and key!=last) else 1 if int(x['repetition'])==0 else 0
   x.update(device_input_copied_bytes=str(size*count),device_input_synced_bytes=str(size*count),device_input_cache_hits=str(8-count));last=key
  with p.open('w',newline='')as out:w=csv.DictWriter(out,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
 b.summarize(f);b.write(f/'status.json',dict(status='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN'));return f
def reject_json(f,path,edit,label):
 p=f/path;original=b.load(p);obj=copy.deepcopy(original);edit(obj);b.write(p,obj)
 try:b.summarize(f)
 except (ValueError,KeyError):cases.append(label)
 else:raise AssertionError('accepted '+label)
 finally:b.write(p,original)
for variant in b.VARIANTS:
 for profile in ('guard','refresh') if variant=='v32_native_splitbo_2_pipe' else ('guard',):
  f=fixture(variant,profile)
  reject_json(f,'replay/summary.json',lambda x:x.update(verified_words=1),variant+':wrong_words')
  reject_json(f,'replay/summary.json',lambda x:x.update(complete_layer_raw_MAC_coverage=True),variant+':subset_label')
  reject_json(f,'replay/admission_profile.json',lambda x:x.update(hashed_outputs=0),variant+':hash_coverage')
  reject_json(f,'controller_profile.json',lambda x:x.update(fresh_before_after_identities=False),variant+':source_identity')
  reject_json(f,'runner_timing.json',lambda x:x.update(runner_wall_ms=0),variant+':wall_scope')
  if variant=='v32_native_splitbo_2_pipe':
   reject_json(f,'replay/split_bo.json',lambda x:x.update(refresh_each_trial=not x['refresh_each_trial']),profile+':refresh_policy')
   reject_json(f,'replay/split_bo.json',lambda x:x.update(copy_and_sync_inside_resident_trial=False),profile+':hidden_uploads')
   p=f/'replay/samples.csv';raw=p.read_bytes();rows=list(csv.DictReader(p.open()));sample=next(x for x in rows if x['phase']=='hardware');sample['device_input_synced_bytes']='0'
   with p.open('w',newline='')as out:w=csv.DictWriter(out,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
   try:b.summarize(f)
   except ValueError:cases.append(profile+':missing_sync')
   else:raise AssertionError('missing sync accepted')
   p.write_bytes(raw)
try:b.binary_name('v32_native_splitbo_2_pipe','baseline')
except ValueError:cases.append('incompatible_frozen_split_host_refused')
else:raise AssertionError('wrong ABI allowed')
for name in ('BASELINE_PROVENANCE.json','IO_BASELINE_PROVENANCE.json','OPTIMIZATION_PLAN.json','GPU_REFERENCE.json','BUILD_IDENTITY.json','OFFLINE_VERIFICATION.json','HARDWARE_PROVENANCE.json','SOURCE_PROVENANCE.json','COMPACT_BASELINE_PROVENANCE.json','PIPELINE_BASELINE_PROVENANCE.json','CUDA_TARGET_ASSESSMENT.json','SPLIT_BO_PROVENANCE.json'):b.write(T/name,dict(scope='LOCAL_PROTOCOL_NOT_BOARD'))
b.board=lambda:None;b.lock=contextlib.nullcontext;c.main();archive=next(T.glob('collected_ga3_splitbo_*.tar.gz'))
with tarfile.open(archive,'r:gz')as tf:entries={x.name:tf.extractfile(x).read() for x in tf}
idx=json.loads(entries['COLLECTION_INDEX.json']);assert not idx['review_required_folders'] and len(entries)==len(idx['entries'])+1
assert all(hashlib.sha256(entries[e['path']]).hexdigest()==e['sha256'] for e in idx['entries'])
b.write(B/'control_verification.json',dict(status='PASS_FOUR_VARIANT_SPLIT_ACCOUNTING_NEGATIVE_CASES_AND_COLLECTION',rejected_cases=cases,archive_members=len(entries),real_board=False,scope='Local protocol fixtures only; software-model labels explicitly rejected before isolated protocol substitution.'))
print('PASS_CONTROL',len(cases),'negative cases')
