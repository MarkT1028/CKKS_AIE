"""Indexed gzip collection by phase/block, including failed raw data."""
from pathlib import Path,PurePosixPath
import argparse,fcntl,hashlib,json,tarfile
import board_runner as r
import study_tools as t
ROOT=Path(__file__).resolve().parent
def regular(path):t.need(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'unsafe collection file: '+str(path))
def safe_name(name):
    p=PurePosixPath(name);t.need(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name,'unsafe archive name')
def collect(phase='all',block=None):
    t.need(phase in ('all','host','ablation') and (block is None or (phase=='ablation' and block in (1,2))),'invalid collection phase/block')
    with (ROOT/'.study.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with r.device_lock():return _collect(phase,block)
def _collect(phase,block):
    entries={};selected=set();refs=set();diags=set();warnings=[]
    def tree(folder):
        t.need(folder.is_dir() and not folder.is_symlink(),'unsafe result directory')
        for p in sorted(folder.rglob('*')):
            t.need(not p.is_symlink() and (p.is_dir() or p.is_file()),'unsafe/nonregular collection member')
            if p.is_file():entries[p.relative_to(ROOT).as_posix()]=p
    def optional(p):
        try:return t.load(p)
        except (OSError,ValueError):warnings.append('unreadable JSON: '+p.relative_to(ROOT).as_posix());return {}
    for attempt in sorted((ROOT/'study_runs').glob('attempt_*')):
        t.need(attempt.is_dir() and not attempt.is_symlink(),'unsafe study attempt directory')
        identity=optional(attempt/'attempt_identity.json')
        if (phase=='all' or identity.get('phase')==phase) and (block is None or identity.get('block')==block):
            selected.add(attempt.name);tree(attempt);status=optional(attempt/'status.json');refs.update(status.get('results',[]))
            if status.get('diagnostic'):diags.add(status['diagnostic'])
    t.need(selected,'no attempts for requested phase/block')
    for folder in sorted(ROOT.glob('results_overlap_*')):
        identity=optional(folder/'run_identity.json');context=identity.get('study_context') or {}
        enrolled=context.get('attempt_id') in selected
        unassigned=not context and (phase=='all' or folder.name.startswith('results_overlap_'+phase+'_'))
        if folder.name in refs or enrolled or unassigned:
            tree(folder)
            if unassigned:warnings.append('Unenrolled/invalid run retained, not counted: '+folder.name)
    for folder in sorted(ROOT.glob('results_cpu_diag_*')):
        if folder.name in diags or phase in ('all','host'):tree(folder)
    for folder in (ROOT/'switch_logs',ROOT/'offline_evidence'):
        if folder.exists():tree(folder)
    for name in ('PACKAGE_STATUS.json','SHA256SUMS_PACKAGE','STUDY_PROTOCOL.json','SOURCE_PROVENANCE.json','OFFLINE_VERIFICATION.json','RESOURCE_MATRIX.json','SOURCE_MATRIX.json','VARIANTS.json','START_HERE.md','study.py','study_tools.py','study_collect.py','board_runner.py','summarize_results.py','summarize_campaign.py','record_io.py','cpu_diagnostics.py','collect_results.py','bin/build_identity.json','bin/schedule_selftest.log','bin/finish_overlap_selftest.log',*(f'bin/{n}' for n in r.BINARIES)):
        p=ROOT/name
        if p.exists():entries[name]=p
    for name in ('SHA256SUMS_PACKAGE','fixture/shape.json','fixture/chunks.tsv','fixture/capture_provenance.json'):entries['dependency/'+name]=r.base()/name
    try:snapshot=t.summarize(phase)
    except (OSError,ValueError,RuntimeError,KeyError) as exc:snapshot=dict(status='INTEGRITY_REVIEW_REQUIRED',error=repr(exc),scope='Raw data retained; archive verification checks bytes only, not scientific validity.')
    stamp=r.stamp();tag=phase+('_block'+str(block) if block else '');snapshot_name='collection_snapshot_'+tag+'_'+stamp+'.json'
    snapshot.update(collection_phase=phase,collection_block=block,selected_attempts=sorted(selected),collection_warnings=warnings,collection_scope='Summary records global progress at collection time; raw members include only the selected phase/block plus retained unassigned failures. Other phases/blocks require their own archives.');r.write(ROOT/snapshot_name,snapshot);entries[snapshot_name]=ROOT/snapshot_name
    for name,p in entries.items():safe_name(name);regular(p)
    total=sum(p.stat().st_size for p in entries.values());print(f'INDEXING phase={tag} files={len(entries)} source_MiB={total/1024**2:.1f}',flush=True);inventory={}
    for i,(name,p) in enumerate(sorted(entries.items()),1):
        inventory[name]=dict(bytes=p.stat().st_size,sha256=r.records.sha(p))
        if i%50==0 or i==len(entries):print(f'INDEX {i}/{len(entries)}',flush=True)
    index=ROOT/f'collection_index_{tag}_{stamp}.json';t.need(not index.exists(),'index exists');r.write(index,inventory);entries[index.name]=index;inventory[index.name]=dict(bytes=index.stat().st_size,sha256=r.records.sha(index))
    archive=ROOT/f'collected_study_{tag}_{stamp}.tar.gz';t.need(not archive.exists(),'archive exists');print('PACKING gzip level=1; retaining all original files',flush=True)
    with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
        for i,(name,p) in enumerate(sorted(entries.items()),1):
            regular(p);tar.add(p,arcname=name,recursive=False)
            if i%20==0 or i==len(entries):print(f'PACK {i}/{len(entries)}',flush=True)
    print('VERIFYING compressed members against saved SHA256',flush=True);seen=set()
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            safe_name(member.name);t.need(member.isfile() and member.name in inventory and member.name not in seen,'archive inventory/member mismatch');seen.add(member.name);want=inventory[member.name];t.need(member.size==want['bytes'],'archive member size');h=hashlib.sha256()
            with tar.extractfile(member) as stream:
                for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
            t.need(h.hexdigest()==want['sha256'],'compressed member SHA mismatch')
            if len(seen)%20==0 or len(seen)==len(inventory):print(f'VERIFY {len(seen)}/{len(inventory)}',flush=True)
    t.need(seen==set(inventory),'archive incomplete');print(json.dumps(dict(status='COLLECTED_AND_BYTE_VERIFIED',download_this_file=str(archive),files=len(entries),source_bytes=total,bytes=archive.stat().st_size,sha256=r.records.sha(archive),phase=phase,block=block,scientific_summary_status=snapshot['status'],crypto='PENDING_INDEPENDENT_ORIGINAL_CONTEXT_VERIFICATION'),indent=2),flush=True);return archive
def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['all','host','ablation'],default='all');p.add_argument('--block',type=int,choices=[1,2]);a=p.parse_args();collect(a.phase,a.block)
