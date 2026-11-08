from pathlib import Path
import importlib.util, json, shutil, subprocess, time

R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_ioopt_20261108';B=R/'build';T=B/('pilot_'+str(time.time_ns()));T.mkdir()
spec=importlib.util.spec_from_file_location('pilot_control',K/'ga3_board.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.ROOT=T
(T/'WINDOW_VARIANTS.json').write_bytes((K/'WINDOW_VARIANTS.json').read_bytes())
(T/'SHA256SUMS_PACKAGE').write_text('isolated pilot schema tests only\n')
(T/'DATA_PROVENANCE.json').write_text(json.dumps(dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256='a'*64)))
results=[]
for profile,name in enumerate(b.PROFILES):
    for order in ('ascending','descending'):
        folder=T/f'{name}_{order}';folder.mkdir()
        done=subprocess.run([str(B/f'model_{profile}'),'unused',str(B/'synthetic'),str(folder/'replay'),'pilot','1','0',order,'0'],capture_output=True,text=True,timeout=120)
        assert done.returncode==0,done.stderr
        ident=dict(variant='v32_native_pl_2_pipe',hostopt_profile=name,manifest_sha256=b.sha(T/'SHA256SUMS_PACKAGE'),data_manifest_sha256='a'*64,
            command=[f'/test/bin/ga3_host_native_{name}','test.xclbin','data','result','pilot','1','0',order,'0'])
        (folder/'identity.json').write_text(json.dumps(ident))
        for when in ('before','after'):(folder/f'environment_{when}.json').write_text(json.dumps(dict(boot_id='unit-test',boot_uuid=b.registry()['v32_native_pl_2_pipe']['uuid'])))
        # Controlled schema fixture: NOT evidence that software ran on the board.
        p=folder/'replay/summary.json';summary=json.loads(p.read_text());assert summary['backend']=='SOFTWARE_MODEL_NOT_HARDWARE'
        summary.update(backend='XRT_PURE_PL',AIE_compute_tiles=0);p.write_text(json.dumps(summary))
        answer=b.summarize(folder)
        assert answer['windows']==16 and not answer['complete_layer_raw_MAC_coverage'] and answer['review_required']
        assert answer['resident_window_median_sum_cpu_before_ms']==answer['resident_window_median_sum_cpu_after_ms']==0
        results.append(dict(profile=name,order=order,verification=answer['verification_protocol'],status='PASS_SOFTWARE_AND_SCHEMA_ONLY'))
(B/'pilot_verification.json').write_text(json.dumps(dict(status='PASS_SINGLE_REQUEST_PILOT_BOTH_ORDERS_ALL_PROFILES',cases=results,board_executed=False),indent=2)+'\n')
print('PASS_SINGLE_REQUEST_PILOT_BOTH_ORDERS_ALL_PROFILES')
