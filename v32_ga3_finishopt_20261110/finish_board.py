"""Host-only overlay; immutable parent image, exact complete-output verification."""
from pathlib import Path
import argparse,contextlib,csv,datetime,hashlib,importlib,json,math,os,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parent
PARENT_SHA='9046e08779347d8b766f5341264ca71fa24914b0a50fb2cd988f59661b0fa2a7'
UUID='9bee253b8f345f39bd9c18d612897ce3'
DATA_SHA='d1bc302affb05586f8a9e875a12efc1b9db7f009a573a09986355b77402218a3'
PROFILES=('merge1','direct1','direct2')
MODES=('smoke','pilot','full','export')

def need(ok,message):
    if not ok:raise ValueError(message)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
    return h.hexdigest()
def stamp():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def parent():return Path(os.environ.get('V32_GA3_SPLITBO_BASE',ROOT.parent/'v32_ga3_splitbo_20261109')).resolve(strict=True)
def verify_manifest(root,manifest):
    seen=set();total=0
    for line in Path(manifest).read_text('ascii').splitlines():
        digest,name=line.split('  ',1);rel=Path(name)
        need(len(digest)==64 and all(x in '0123456789abcdef' for x in digest) and name not in seen and not rel.is_absolute() and '..' not in rel.parts and '\\' not in name,'unsafe manifest entry')
        path=root/rel;need(path.is_file() and not path.is_symlink(),'missing/unsafe package file '+name)
        path.resolve().relative_to(root.resolve());need(sha(path)==digest,'hash mismatch '+name)
        seen.add(name);total+=path.stat().st_size
    need(seen,'empty manifest');return dict(files=len(seen),bytes=total,manifest_sha256=sha(manifest))
def code_check():
    own=verify_manifest(ROOT,ROOT/'SHA256SUMS_PACKAGE');base=parent()
    need(sha(base/'SHA256SUMS_PACKAGE')==PARENT_SHA,'wrong parent package version')
    old=verify_manifest(base,base/'SHA256SUMS_PACKAGE')
    return dict(status='PASS_FINISHOPT_OVERLAY_CODE',**own,parent_manifest_sha256=old['manifest_sha256'],parent=str(base),firmware_changed=False)
def dependencies():
    base=parent();sys.path.insert(0,str(base))
    prior=importlib.import_module('ga3_board');cache=importlib.import_module('compact_cache');identity=importlib.import_module('identity_fast')
    need(Path(prior.__file__).resolve().parent==base,'unexpected ga3_board module')
    return prior,cache,identity
def admission_identity(prior,cache,identity):
    data=prior.data();manifest=sha(data/'SHA256SUMS_DATA')
    need(manifest==DATA_SHA==load(parent()/'DATA_PROVENANCE.json')['manifest_sha256'],'wrong original data')
    fresh=identity.data_snapshot(data);receipt=None
    for path in (ROOT/'DATA_CHECK_RECEIPT.json',parent()/'DATA_CHECK_RECEIPT.json'):
        if path.is_file() and not path.is_symlink():
            value=load(path)
            if value.get('path')==str(data) and value.get('manifest_sha256')==manifest and value.get('files')==fresh:
                receipt=dict(path=str(path),sha256=sha(path));break
    need(receipt is not None,'no unchanged full data hash receipt; run parent check_package.sh first')
    compact=cache.checked_identity()
    return data,fresh,compact,receipt
def check():
    checked=code_check();prior,cache,identity=dependencies()
    data,snapshot,compact,receipt=admission_identity(prior,cache,identity)
    write(ROOT/'DATA_CHECK_RECEIPT.json',dict(path=str(data),manifest_sha256=sha(data/'SHA256SUMS_DATA'),files=snapshot,verification='PRIOR_FULL_SHA256_WITH_FRESH_IDENTITIES',prior_receipt=receipt))
    return dict(**checked,status_detail='PASS_FINISHOPT_OVERLAY_AND_REUSED_ORIGINAL_DATA',source_files=len(snapshot),cache=compact,new_fixture_required=False)
def expected_coordinates(mode):
    all_coordinates=[(t,c,o,min(16,53-t)) for t in range(0,53,16) for c in range(0,131072,8192) for o in range(16)]
    if mode=='smoke':return [all_coordinates[0],all_coordinates[-1]]
    if mode=='pilot':return [x for x in all_coordinates if x[1] in (0,122880) and x[2] in (0,15)]
    return all_coordinates
def expected_digests(data):
    hashes={name:digest for digest,name in (x.split('  ',1) for x in (data/'SHA256SUMS_DATA').read_text('ascii').splitlines())}
    with (data/'jobs.tsv').open(newline='') as f:
        return {(int(x['tower_start']),int(x['coefficient_start']),int(x['output_ct']),int(x['group'])):hashes[x['expected']] for x in csv.DictReader(f,delimiter='\t')}
def readcsv(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))
def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0
def summarize(folder):
    folder=Path(folder);ident=load(folder/'identity.json');s=load(folder/'replay/summary.json')
    need(ident['manifest_sha256']==sha(ROOT/'SHA256SUMS_PACKAGE') and ident['parent_manifest_sha256']==PARENT_SHA,'recorded package differs')
    need(s['backend']=='XRT_PURE_PL' and s['protocol']=='finish_batch_v1','software model is not board evidence')
    profile,mode,order=ident['profile'],ident['mode'],ident['order']
    need(profile in PROFILES and mode in MODES and order in ('ascending','descending'),'invalid run identity')
    need((s['profile'],s['mode'],s['order'])==(profile,mode,order),'executed profile/mode differs')
    need(ident['command'][4:]==[profile,mode,order] and Path(ident['command'][0]).name=='finish_host','command identity mismatch')
    before,after=load(folder/'environment_before.json'),load(folder/'environment_after.json')
    need(before['boot_id']==after['boot_id'] and before['boot_uuid']==after['boot_uuid']==UUID,'boot identity changed')
    need((s['full_N'],s['L'],s['K'],s['coefficient_windows'],s['warmups'],s['repetitions'])==(131072,53,16,16,0,1),'workload/trial policy differs')
    need(s['direct_canonical_SHA256']==(profile!='merge1') and s['batch_limit']==(2 if profile=='direct2' else 1) and s['export']==(mode=='export'),'candidate policy differs')
    for key in ('resident_batch_wall_sum_ms','admission_ms','request_wall_ms','setup_ms','copied_bytes','synced_bytes','cache_hits','hashed_outputs','hashed_bytes'):
        need(finite(s[key]),'bad/nonfinite measurement '+key)
    coords=expected_coordinates(mode);windows=readcsv(folder/'replay/windows.csv');batches=readcsv(folder/'replay/batches.csv');admission=readcsv(folder/'replay/admission.csv');traces=readcsv(folder/'replay/traces.csv')
    need(len(windows)==len(coords)==len(admission)==s['windows'] and len(batches)==s['batches'],'incomplete window/batch/admission coverage')
    data=folder/'data_evidence'
    need(sha(data/'SHA256SUMS_DATA')==ident['data_manifest_sha256']==DATA_SHA,'data manifest differs')
    sealed={name:digest for digest,name in (x.split('  ',1) for x in (data/'SHA256SUMS_DATA').read_text('ascii').splitlines())}
    for name in ('shape.json','jobs.tsv'):need(sha(data/name)==sealed[name],'sealed data metadata differs')
    hashes=expected_digests(data);words=copied=synced=hits=0;batch_rows={}
    for index,row in enumerate(windows):
        actual=tuple(int(row[k]) for k in ('tower_start','coefficient_start','output_ct','L'))
        need(int(row['window'])==index and actual==coords[index],'missing/reordered/duplicate coordinate')
        count=8192*actual[3]*3*4;need(int(row['verified_words'])==count,'wrong output word coverage');words+=count
        for group in range(4):need(row['digest'+str(group)]==hashes[actual[:3]+(group,)],'sealed complete output SHA256 differs')
        vals=[int(row[k]) for k in ('copied_bytes','synced_bytes','cache_hits')];size=8192*actual[3]*16*2*8
        changed=5 if index==0 or coords[index-1][:2]!=actual[:2] else 1
        need(vals==[changed*size,changed*size,8-changed],'first-upload/BO-reuse accounting differs')
        copied+=vals[0];synced+=vals[1];hits+=vals[2];batch_rows.setdefault(int(row['batch']),[]).append(row)
        a=admission[index];need(all(a[k]==row[k] for k in ('window','batch','slot','tower_start','coefficient_start','output_ct','L')) and finite(float(a['admission_ms'])),'admission identity differs')
    wall=0
    for index,batch in enumerate(batches):
        selected=batch_rows.get(index,[]);need(selected and int(batch['batch'])==index and int(batch['windows'])==len(selected),'missing batch')
        need([int(x['slot']) for x in selected]==list(range(len(selected))) and int(batch['first_window'])==int(selected[0]['window']),'batch ownership differs')
        need(len(selected)<=s['batch_limit'] and (len(selected)==s['batch_limit'] or mode=='smoke'),'incorrect batch width')
        need(len({(x['tower_start'],x['coefficient_start'],x['L']) for x in selected})==1,'batch crosses weight/RNS block')
        need(finite(float(batch['wall_ms'])) and float(batch['wall_ms'])>0,'bad batch wall');wall+=float(batch['wall_ms'])
        for key in ('verified_words','copied_bytes','synced_bytes','cache_hits'):need(int(batch[key])==sum(int(x[key]) for x in selected),'batch ledger differs '+key)
    need(abs(wall-s['resident_batch_wall_sum_ms'])<.01 and abs(sum(float(x['admission_ms']) for x in admission)-s['admission_ms'])<.05,'summary differs from raw CSV')
    need((words,copied,synced,hits)==(s['verified_words'],s['copied_bytes'],s['synced_bytes'],s['cache_hits']) and s['warmup_copied_bytes']==0,'summary word/upload totals differ')
    need(s['complete_raw_MAC_coverage']==(mode in ('full','export')) and (mode in ('smoke','pilot') or words==1333788672),'full scope mislabeled')
    need(s['hashed_outputs']==len(coords)*4 and s['hashed_bytes']==sum((64+24*x[3]+8192*x[3]*3*8)*4 for x in coords),'complete canonical digest byte coverage differs')
    ad=load(folder/'replay/admission_profile.json');need(ad['logical_input_bytes']==copied and ad['records']==ad['packed_records']+ad['raw_records'],'admission/input ledger differs')
    need(ad['retirement_advice']=='POSIX_FADV_DONTNEED' and ad['global_cache_clear'] is False,'cache policy changed')
    signatures={};seen_tasks=set()
    allowed={'baby_copy','baby_sync','weight_copy','weight_sync','parameter_pack','parameter_write','parameter_sync','output_poison','output_poison_sync','execute','status','output_sync','merge_copy','canonical_sha256','verify_digest','output_save'}
    for row in traces:
        batch,task=int(row['batch']),int(row['task']);need(0<=batch<len(batches),'trace batch out of range');selected=batch_rows[batch]
        slot=task//4;need(0<=slot<len(selected) and int(row['slot'])==slot and row['window']==selected[slot]['window'] and int(row['bank'])==task%2,'trace task/window/bank ownership')
        need(int(row['group'])==(task%4 if order=='ascending' else 3-task%4),'trace group order differs')
        start,end=float(row['begin_ms']),float(row['end_ms']);need(finite(start) and finite(end) and start<=end<=float(batches[batch]['wall_ms'])+.001 and row['stage'] in allowed,'invalid trace timing/stage')
        signature=signatures.setdefault((batch,task),{});key=(row['stage'],int(row['lane']));signature[key]=signature.get(key,0)+1;seen_tasks.add((batch,task))
    need(len(seen_tasks)==len(coords)*4,'missing task traces')
    for signature in signatures.values():
        for stage in ('execute','status','canonical_sha256','verify_digest'):need(signature.get((stage,-1))==1,'missing/duplicate complete task stage '+stage)
        for lane in (0,1):
            for stage in ('parameter_pack','parameter_write','parameter_sync','output_poison','output_poison_sync','output_sync'):need(signature.get((stage,lane))==1,'missing lane stage '+stage)
            need(signature.get(('merge_copy',lane),0)==(1 if profile=='merge1' else 0),'merge policy differs')
        need(signature.get(('output_save',-1),0)==int(mode=='export'),'export timing policy differs')
    for (batch,task),signature in signatures.items():
        w=int(batch_rows[batch][task//4]['window']);changed=(w==0 or coords[w-1][:2]!=coords[w][:2])
        for stage in ('baby_copy','baby_sync'):need(signature.get((stage,-1),0)==int(task%4==0),'baby upload trace differs')
        for stage in ('weight_copy','weight_sync'):need(signature.get((stage,-1),0)==int(changed),'weight upload trace differs')
    if mode=='export':
        actual_files=0
        for row in windows:
            for group in range(4):
                p=folder/'replay/outputs'/f"r{row['tower_start']}_c{row['coefficient_start']}_o{row['output_ct']}"/f'group_{group}'/'chunk_0_output.bin'
                need(Path(str(p)+'.sha256').read_text().strip()==row['digest'+str(group)],'missing export digest witness')
                required=(row['tower_start'],row['coefficient_start'],row['output_ct']) in (('0','0','0'),('48','122880','15'))
                need(p.exists()==(required or ident['export_all']),'missing or unexpected actual export byte file')
                if p.exists():
                    need(not p.is_symlink() and sha(p)==row['digest'+str(group)],'export actual bytes differ');actual_files+=1
        need(actual_files==(s['hashed_outputs'] if ident['export_all'] else 8),'actual export byte coverage differs')
    runner=load(folder/'runner_timing.json');need(finite(runner['runner_wall_ms']) and runner['runner_wall_ms']>=s['setup_ms']+s['request_wall_ms'],'runner wall differs')
    need(runner['fresh_source_identities_before_after'] is True and runner['source_files_checked']==5378 and runner['fresh_cache_identities_before_after'] is True,'fresh source/cache identity policy differs')
    need(ident['effective_environment']['V32_GA3_READ_MIB']=='4' and ident['effective_environment']['V32_GA3_PREFETCH']=='0','read/prefetch policy differs')
    need(before['affinity']==after['affinity']==[0,1] and not any(before['inherited_runtime_environment'].values()) and not any(after['inherited_runtime_environment'].values()),'runtime environment differs')
    need(s['request_wall_ms']+.1>=s['resident_batch_wall_sum_ms']+s['admission_ms'],'batch wall overlaps unaccounted admission')
    s.update(runner_wall_ms=runner['runner_wall_ms'],performance='PENDING_MATCHED_REPEAT_AND_FULL_BOARD_REVIEW',review_required=True,
        canonical_verification='FULL_ORIGINAL_HEADER_AND_PAYLOAD_SHA256',scope_note='Batch wall includes all needed BO preparation and full verification; file admission/setup separate. No window latency invented from overlap.')
    write(folder/'independently_recomputed_summary.json',s);return s

def run(profile,mode,order):
    start=time.perf_counter();checked=code_check();prior,cache,identity=dependencies();prior.board()
    need(profile in PROFILES and mode in MODES and order in ('ascending','descending'),'invalid experiment')
    with prior.lock():
        data,snapshot,compact,receipt=admission_identity(prior,cache,identity);before=prior.environment();prior.guard_recovery(before)
        if (ROOT/'RECOVERY_REQUIRED.json').exists():need(load(ROOT/'RECOVERY_REQUIRED.json')['boot_id']!=before['boot_id'],'previous active failure: reboot before reusing hardware')
        need(before['boot_uuid']==UUID and before['affinity']==[0,1] and not any(before['inherited_runtime_environment'].values()),'require exact Split BO boot, both ARM cores and clean XRT environment')
        mem={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in before['meminfo'].splitlines())}
        need(mem['MemAvailable']>=1024*1024 and mem['CmaTotal']>=256*1024,'insufficient available RAM/CMA total; actual BO allocation remains mandatory; no cache clearing')
        disk_min=12*2**30 if mode=='export' and os.environ.get('V32_GA3_EXPORT_ALL')=='1' else 256*2**20
        need(shutil.disk_usage(ROOT).free>=disk_min,'insufficient result space (256MiB default;12GiB for all-output export)')
        binary=ROOT/'bin/finish_host';build=load(ROOT/'BUILD_IDENTITY.json')
        need(build['manifest_sha256']==checked['manifest_sha256'] and build['parent_manifest_sha256']==PARENT_SHA and sha(binary)==build['binary_sha256'],'build differs; rebuild overlay')
        folder=ROOT/f'results_finish_{profile}_{mode}_{order}_{stamp()}';folder.mkdir()
        command=[str(binary),str(parent()/'variants/v32_native_splitbo_2_pipe/ckks_hw_boot.xclbin'),str(data),str(folder/'replay'),profile,mode,order]
        child_env=dict(os.environ,XRT_INI_PATH=str(parent()/'configs/baseline.ini'),V32_GA3_CACHE=compact['path'],V32_GA3_READ_MIB='4',V32_GA3_PREFETCH='0')
        need(child_env.get('V32_GA3_EXPORT_ALL','0') in ('0','1'),'invalid export policy')
        write(folder/'environment_before.json',before);write(folder/'identity.json',dict(**checked,profile=profile,mode=mode,order=order,data_path=str(data),data_manifest_sha256=sha(data/'SHA256SUMS_DATA'),source_receipt=receipt,compact_cache=compact,build=build,command=command,export_all=child_env.get('V32_GA3_EXPORT_ALL')=='1',effective_environment={k:child_env[k] for k in ('XRT_INI_PATH','V32_GA3_CACHE','V32_GA3_READ_MIB','V32_GA3_PREFETCH')}))
        evidence=folder/'data_evidence';evidence.mkdir()
        for name in ('SHA256SUMS_DATA','shape.json','jobs.tsv'):shutil.copyfile(data/name,evidence/name)
        evidence=folder/'cache_evidence';evidence.mkdir()
        for name in ('CACHE_INDEX.tsv','CACHE_PLAN.json','CACHE_COMPLETE.json','CACHE_RECEIPT.json'):shutil.copyfile(Path(compact['path'])/name,evidence/name)
        write(folder/'status.json',dict(status='RUNNING'));process=None
        try:
            with (folder/'execution.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,env=child_env,start_new_session=True)
                for line in process.stdout:print(line,end='',flush=True);log.write(line);log.flush()
                need(process.wait()==0,'host failed; preserve output')
            after=prior.environment();write(folder/'environment_after.json',after)
            need(snapshot==identity.data_snapshot(data) and compact==cache.checked_identity(),'source/cache identity changed while active')
            write(folder/'runner_timing.json',dict(runner_wall_ms=(time.perf_counter()-start)*1000,fresh_source_identities_before_after=True,source_files_checked=len(snapshot),fresh_cache_identities_before_after=True))
            answer=summarize(folder);write(folder/'status.json',dict(status='PASS_FINISH_BOARD_REPLAY_PENDING_INDEPENDENT_REVIEW'))
            print(json.dumps(answer,indent=2));print('RESULTS='+str(folder))
        except BaseException as e:
            unsafe=process is not None and (folder/'replay/HARDWARE_ENTERED').is_file()
            if unsafe:write(ROOT/'RECOVERY_REQUIRED.json',dict(boot_id=before['boot_id'],reason='failed/interrupted hardware entry',folder=folder.name))
            prior.stop_owned_child(process);write(folder/'status.json',dict(status='FAILED_RETAINED',error=str(e),reboot_required=unsafe));raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['base-path','code-check','check','detect','record-build','run','summarize']);parser.add_argument('profile',nargs='?',default='direct2');parser.add_argument('mode',nargs='?',default='smoke');parser.add_argument('order',nargs='?',default='descending');a=parser.parse_args()
    if a.action=='base-path':print(parent())
    elif a.action=='code-check':print(json.dumps(code_check(),indent=2))
    elif a.action=='check':print(json.dumps(check(),indent=2))
    elif a.action=='detect':
        code_check();prior,_,_=dependencies();prior.board();env=prior.environment();print(json.dumps(dict(matching_variant='v32_native_splitbo_2_pipe' if env['boot_uuid']==UUID else None,environment=env),indent=2))
    elif a.action=='record-build':
        checked=code_check();write(ROOT/'BUILD_IDENTITY.json',dict(manifest_sha256=checked['manifest_sha256'],parent_manifest_sha256=PARENT_SHA,binary_sha256=sha(ROOT/'bin/finish_host'),compiler=subprocess.run(['g++','--version'],capture_output=True,text=True,check=True).stdout,sha256_selfcheck=subprocess.run([str(ROOT/'bin/finish_host'),'--crypto-check'],capture_output=True,text=True,check=True).stdout,compile_policy='g++ -O3 -std=c++17 -pthread; exact pinned splitBO identity override; XRT coreutil and existing libcrypto; no FINISH_MODEL or parser execution backend',hardware_changed=False))
    elif a.action=='run':run(a.profile,a.mode,a.order)
    else:print(json.dumps(summarize(a.profile),indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL:',e,file=sys.stderr);raise SystemExit(1)
