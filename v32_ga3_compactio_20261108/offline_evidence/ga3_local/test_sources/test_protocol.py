"""Small control/packaging tests. All identities and timings here are synthetic."""
from pathlib import Path
import contextlib,gzip,hashlib,importlib.util,io,json,os,shutil,subprocess,sys,tarfile,time
R=Path(__file__).resolve().parents[1];W=R.parents[1];K=W/'board_packages/v32_ga3_20261104';sys.path.insert(0,str(K));sys.path.insert(0,str(R))
import ga3_board as b,collect_results as collect,summarize_campaign as campaign,unpack_data as unpack
import reconstruct_audit
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x),encoding='utf-8')
def main():
    td=R/'build'/('protocol_'+str(time.time_ns()));td.mkdir();cases=[];old_root=b.ROOT;old_summarize=b.summarize
    b.board=lambda:None;b.lock=contextlib.nullcontext
    # A cancelled controller owns only its new-session child. It cannot leave
    # a subprocess running after releasing the experiment lock or reuse an
    # uncertain hardware state within the same boot.
    root=td/'recovery/kit';root.mkdir(parents=True);b.ROOT=root
    owned=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    sentinel=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    try:
        assert b.stop_owned_child(owned) and owned.poll() is not None and sentinel.poll() is None
        assert not b.stop_owned_child(owned)
    finally:b.stop_owned_child(sentinel)
    put(root/'RECOVERY_REQUIRED.json',dict(boot_id='old_boot'))
    try:b.guard_recovery(dict(boot_id='old_boot'))
    except ValueError:pass
    else:raise AssertionError('uncertain interrupted hardware could run again in same boot')
    b.guard_recovery(dict(boot_id='new_boot'));cases.append('owned_child_cleanup_and_same_boot_interruption_guard')
    # Collection must retain failures/incomplete runs, while verifying bytes.
    root=td/'collection/kit';root.mkdir(parents=True);b.ROOT=root
    for name in ('BUILD_IDENTITY.json','DATA_PROVENANCE.json','OFFLINE_VERIFICATION.json','HARDWARE_PROVENANCE.json','SOURCE_PROVENANCE.json'):put(root/name,{'synthetic_only':True})
    (root/'SHA256SUMS_PACKAGE').write_text('synthetic fixture')
    for name,status in [('good','PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN'),('failed','FAILED_RETAINED'),('interrupted',None)]:
        d=root/('results_ga3_'+name);d.mkdir();(d/'payload.txt').write_text(name)
        if status:put(d/'status.json',dict(status=status))
    (root/'switch_logs').mkdir();(root/'switch_logs/test.txt').write_text('synthetic switch record');b.summarize=lambda folder:dict(status='synthetic_validated_fixture')
    collect.main();archive=next(root.glob('collected_*.tar.gz'))
    with tarfile.open(archive) as tf:
        index=json.load(tf.extractfile('COLLECTION_INDEX.json'));assert len(index['review_required_folders'])==2
        assert any(x['path']=='switch_logs/test.txt' for x in index['entries'])
        for e in index['entries']:assert hashlib.sha256(tf.extractfile(e['path']).read()).hexdigest()==e['sha256']
    cases.append('failed_and_interrupted_runs_retained_with_verified_archive')
    # ABA accepts all required runs; CPU drift/duplicate reruns are not hidden.
    root=td/'campaign/kit';root.mkdir(parents=True);b.ROOT=root;shutil.copy2(K/'WINDOW_VARIANTS.json',root/'WINDOW_VARIANTS.json')
    for boot,variant,hw in [(0,'v32_core_2_pipe',300),(1,'v32_native_pl_2_pipe',200),(2,'v32_core_2_pipe',310)]:
        for order in ('ascending','descending'):
            d=root/f'results_ga3_{boot}_{order}';d.mkdir();put(d/'status.json',dict(status='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN'))
            put(d/'identity.json',dict(variant=variant,data_manifest_sha256='a'*64,manifest_sha256='b'*64,command=['bin','x','d','r','windows','3','1',order,'0']))
            put(d/'environment_before.json',dict(boot_id=str(boot),utc=f'20261104T00000{boot}Z'))
            put(d/'fixture_summary.json',dict(mode='windows',resident_window_median_sum_hardware_ms=hw,resident_window_median_sum_cpu_before_ms=500,resident_window_median_sum_cpu_after_ms=500,CPU_window_sum_drift_percent=0,review_required=False,coefficient_windows=16))
    b.summarize=lambda folder:b.load(Path(folder)/'fixture_summary.json');campaign.main();assert b.load(root/'campaign_summary.json')['performance_comparison_eligible']
    d=root/'results_ga3_1_ascending';s=b.load(d/'fixture_summary.json');s['resident_window_median_sum_cpu_before_ms']=600;s['resident_window_median_sum_cpu_after_ms']=600;put(d/'fixture_summary.json',s);campaign.main();assert not b.load(root/'campaign_summary.json')['performance_comparison_eligible']
    s['resident_window_median_sum_cpu_before_ms']=500;s['resident_window_median_sum_cpu_after_ms']=500;put(d/'fixture_summary.json',s)
    shutil.copytree(d,root/'results_ga3_1_duplicate');campaign.main();assert not b.load(root/'campaign_summary.json')['performance_comparison_eligible'];cases.append('ABA_CPU_cross_boot_guard_and_duplicate_retention')
    # Extraction has no shell, overwrite, symlink or traversal path.
    for kind in ('good','corrupt','traversal','symlink','duplicate'):
        root=td/('unpack_'+kind)/'kit';root.mkdir(parents=True);b.ROOT=root;data=b'fixture payload';buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as tf:
            for index in range(2 if kind=='duplicate' else 1):
                name='v32_ga3_20261104_data/../escape.txt' if kind=='traversal' else 'v32_ga3_20261104_data/test.bin';m=tarfile.TarInfo(name)
                if kind=='symlink':m.type=tarfile.SYMTYPE;m.linkname='../../escape.txt';tf.addfile(m)
                else:m.size=len(data);tf.addfile(m,io.BytesIO(data))
        archive=root.parent/'test.tar.gz';archive.write_bytes(buf.getvalue());put(root/'TRANSFER_MANIFEST.json',dict(archive_sha256=b.sha(archive),data_files={'test.bin':dict(bytes=len(data),sha256=hashlib.sha256(data if kind!='corrupt' else b'wrong').hexdigest())}))
        failed=False
        try:unpack.main(archive)
        except ValueError:failed=True
        assert failed==(kind!='good');assert not (root.parent/'escape.txt').exists()
        if kind=='good':assert (root.parent/'v32_ga3_20261104_data/test.bin').read_bytes()==data
    cases.append('stream_archive_hash_member_hash_path_and_symlink_guards')
    # Actual model hashes are linked to references, preserving origin labels.
    previous=Path((R/'build/latest_host_tests.txt').read_text().strip());data=previous/'data_pilot';lines=[]
    for p in sorted(p for p in data.iterdir() if p.is_file() and p.name!='SHA256SUMS_DATA'):lines.append(b.sha(p)+'  '+p.name+'\n')
    (data/'SHA256SUMS_DATA').write_text(''.join(lines),encoding='ascii');digest=b.sha(data/'SHA256SUMS_DATA');actual=previous/'model_audit_pilot/outputs'
    out=reconstruct_audit.reconstruct(data,actual,td/'reconstructed',digest,evidence_kind='OFFLINE_SOFTWARE_MODEL_TEST_NOT_BOARD');assert out['files']==512 and out['downloaded_actual_byte_files']==8 and not out['complete_raw_MAC_coefficient_coverage']
    bad=td/'bad_audit';shutil.copytree(actual,bad,copy_function=os.link);p=next(bad.rglob('*.sha256'));p.unlink();p.write_text('0'*64+'\n')
    try:reconstruct_audit.reconstruct(data,bad,td/'bad_reconstruction',digest)
    except ValueError:pass
    else:raise AssertionError('corrupt witness accepted')
    assert not (td/'bad_reconstruction').exists();cases.append('hash_linked_reconstruction_preserves_actual_vs_reference_and_subset_scope')
    b.ROOT=old_root;b.summarize=old_summarize
    result=dict(status='PASS_GA3_PROTOCOL_COLLECTION_EXTRACTION_AND_RECONSTRUCTION',synthetic_only=True,board_executed=False,tests=cases,test_path=str(td));(R/'build/protocol_tests.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
