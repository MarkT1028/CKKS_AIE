from pathlib import Path
import copy,csv,hashlib,importlib.util,json,os,shutil,subprocess,sys,time
R=Path(__file__).resolve().parents[1];W=R.parents[1];K=W/'board_packages/v32_ga3_20261104'
def main(testdir):
    td=Path(testdir);case_root=td/('contracts_run_'+str(time.time_ns()));case_root.mkdir();data=td/'data_pilot';binary=R/'build/ga3_model';cases=[]
    def call(d,name,valid=False,validate=False):
        cmd=[binary,'--validate',d] if validate else [binary,'unused',d,case_root/('out_'+name),'smoke','1','0','descending','2']
        p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        assert (p.returncode==0)==valid,(name,p.stdout,p.stderr);cases.append(dict(name=name,returncode=p.returncode,stderr=p.stderr[-1000:]))
    def mutant(name):
        d=case_root/('mutant_'+name);d.mkdir()
        for p in data.iterdir():
            if p.suffix=='.bin':os.link(p,d/p.name)
            else:shutil.copy2(p,d/p.name)
        return d
    d=mutant('duplicate');p=d/'jobs.tsv';p.write_text(p.read_text()+p.read_text().splitlines()[1]+'\n');call(d,'duplicate',validate=True)
    d=mutant('missing_tail');p=d/'jobs.tsv';p.write_text('\n'.join(p.read_text().splitlines()[:-1])+'\n');call(d,'missing_tail',validate=True)
    d=mutant('unsafe');p=d/'jobs.tsv';p.write_text(p.read_text().replace('record_3_16.bin','../record_3_16.bin'));call(d,'unsafe',validate=True)
    for name,record,offset in [('gold_corrupt','record_2_16.bin',64+24*16),('tail_corrupt','record_2_5.bin',64+24*5),('baby_kind','record_4_16.bin',12)]:
        d=mutant(name);p=d/record;blob=bytearray(p.read_bytes());blob[offset]^=1;p.unlink();p.write_bytes(blob);call(d,name)
    # Every downloaded actual-byte sample and every digest is checked using
    # Python hashlib, independent of the vendored C++ SHA implementation.
    audited=td/'model_audit_pilot/outputs';digest_files=list(audited.rglob('*.sha256'));assert len(digest_files)==512
    for p in digest_files:
        lt=5 if '/r48_' in p.as_posix() else 16;gold=data/f'record_2_{lt}.bin';want=hashlib.sha256(gold.read_bytes()).hexdigest();assert p.read_text().strip()==want
        sample=Path(str(p)[:-7])
        if sample.exists():assert hashlib.sha256(sample.read_bytes()).hexdigest()==want
    assert len(list(audited.rglob('*.bin')))==8
    # The independently recomputed summarizer must reject model output as real
    # hardware evidence, missing trials and mislabeled full-layer coverage.
    spec=importlib.util.spec_from_file_location('ga3_control',K/'ga3_board.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
    fake=case_root/'control';fake.mkdir();shutil.copy2(K/'WINDOW_VARIANTS.json',fake/'WINDOW_VARIANTS.json');control.ROOT=fake
    (fake/'SHA256SUMS_PACKAGE').write_text('synthetic validator fixture only\n');package_sha=hashlib.sha256((fake/'SHA256SUMS_PACKAGE').read_bytes()).hexdigest();data_sha=hashlib.sha256(b'synthetic').hexdigest()
    (fake/'DATA_PROVENANCE.json').write_text(json.dumps(dict(L=53,coefficient_windows=2,checked_words=64*16384*53*3,manifest_sha256=data_sha)))
    folder=fake/'result';folder.mkdir();shutil.copytree(td/'model_windows_pilot',folder/'replay');(folder/'identity.json').write_text(json.dumps(dict(variant='v32_core_2_pipe',manifest_sha256=package_sha,data_manifest_sha256=data_sha,command=['/synthetic/bin/ga3_host_aie','synthetic.xclbin','synthetic_data','synthetic_results','windows','3','1','descending','0'])))
    env=dict(boot_id='synthetic_boot',boot_uuid=control.registry()['v32_core_2_pipe']['uuid'])
    for name in ('environment_before.json','environment_after.json'):(folder/name).write_text(json.dumps(env))
    try:control.summarize(folder)
    except ValueError:cases.append(dict(name='reject_model_as_hardware',pass_=True))
    else:raise AssertionError('model falsely counted as board evidence')
    sp=folder/'replay/summary.json';s=json.loads(sp.read_text());s['backend']='XRT_AIE';s['AIE_compute_tiles']=2;sp.write_text(json.dumps(s));control.summarize(folder)
    s['complete_layer_raw_MAC_coverage']=True;sp.write_text(json.dumps(s))
    try:control.summarize(folder)
    except ValueError:cases.append(dict(name='reject_pilot_as_full_layer',pass_=True))
    else:raise AssertionError('subset falsely called full layer')
    report=json.dumps(dict(status='PASS_GA3_CONTRACTS',cases=cases,actual_digest_files=512,actual_samples=8,synthetic_only=True),indent=2)+'\n'
    (case_root/'contracts.json').write_text(report);(td/'contracts.json').write_text(report)
    print('PASS_GA3_CONTRACTS',len(cases))
if __name__=='__main__':main(sys.argv[1])
