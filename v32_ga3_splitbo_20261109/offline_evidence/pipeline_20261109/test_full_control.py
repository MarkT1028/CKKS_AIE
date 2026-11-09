from pathlib import Path
import json,shutil,sys,time
R=Path(__file__).resolve().parent;W=R.parents[1];K=W/'board_packages/v32_ga3_pipeline_20261109';B=R/'build'
sys.path.insert(0,str(K));import ga3_board as b
T=B/('full_control_'+str(time.time_ns()));T.mkdir();b.ROOT=T
for n in ('WINDOW_VARIANTS.json','DATA_PROVENANCE.json'):(T/n).write_bytes((K/n).read_bytes())
(T/'SHA256SUMS_PACKAGE').write_text('ISOLATED_FULL_MODEL_SCHEMA_NOT_BOARD\n');f=T/'run';shutil.copytree(B/'full_real_combined',f/'replay')
i=dict(variant='v32_core_2_pipe',hostopt_profile='combined',tuning=b.TUNINGS['combined'],manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256=b.load(T/'DATA_PROVENANCE.json')['manifest_sha256'],compact_cache=dict(index_sha256='a'*64,all_inputs_cached=True,cached_inputs=1280),command=[b.binary_name('v32_core_2_pipe','combined'),'none','data','results','stream','1','0','ascending','0'])
b.write(f/'identity.json',i)
for when in ('before','after'):b.write(f/f'environment_{when}.json',dict(boot_id='LOCAL_NOT_BOARD',boot_uuid=b.registry()['v32_core_2_pipe']['uuid']))
keys=('code_check_ms','source_snapshot_before_ms','source_snapshot_after_ms','cache_snapshot_before_ms','cache_snapshot_after_ms','environment_before_ms','environment_after_ms','binary_identity_ms','child_process_wall_ms')
b.write(f/'controller_profile.json',dict(snapshot_engine='dirfd',timings_ms={k:1 for k in keys},source_files_checked_each=5378,fresh_before_after_identities=True,skipped_output_verification=False))
s=b.load(f/'replay/summary.json');assert s['backend']=='SOFTWARE_MODEL_NOT_HARDWARE'
b.write(f/'runner_timing.json',dict(runner_wall_ms=s['setup_ms']+s['campaign_wall_ms']+100))
try:b.summarize(f)
except ValueError as e:assert 'software model' in str(e)
else:raise AssertionError('software accepted as board')
s.update(backend='XRT_AIE',AIE_compute_tiles=2);b.write(f/'replay/summary.json',s)
out=b.summarize(f);assert out['complete_layer_raw_MAC_coverage'] and out['windows']==1024 and out['verified_words']==1333788672
i['compact_cache']['cached_inputs']=1279;b.write(f/'identity.json',i)
try:b.summarize(f)
except ValueError as e:assert 'cache activity' in str(e)
else:raise AssertionError('wrong full input coverage accepted')
synthetic=W/'integration/ga3_compactio_20261108/build/synthetic';b.data=lambda:synthetic
audit_root=T/'synthetic_export';shutil.copytree(B/'full_synthetic_export',audit_root/'replay')
audit=b.verify_audit(audit_root);assert audit['hash_linked_output_files']==512 and audit['actual_byte_files']==8
ts=B/'tsan_smoke';st=b.load(ts/'summary.json');assert st['backend']=='SOFTWARE_MODEL_NOT_HARDWARE' and st['windows']==2
log=(B/'tsan_smoke.txt').read_text();assert 'WARNING: ThreadSanitizer' not in log and 'FATAL: ThreadSanitizer' not in log
b.write(B/'thread_verification.json',dict(status='PASS_THREAD_SANITIZER_PREFETCH_TWO_WINDOWS',source='host/ga3_host.cpp',flags=['-fsanitize=thread','-no-pie'],summary=st,board_executed=False))
b.write(B/'full_control_verification.json',dict(status='PASS_FULL_REAL_MODEL_1024_COORDINATES_4096_DIGESTS_PREFETCH_1023',source_model_is_not_board=True,real_words=out['verified_words'],synthetic_export=audit,board_executed=False))
print('PASS_FULL_MODEL_SCHEMA_AND_EXPORTED_DIGESTS')
