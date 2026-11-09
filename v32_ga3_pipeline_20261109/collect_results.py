"""Fast gzip collection of results only; no keys or multi-GiB input fixture."""
from pathlib import Path
import gzip, hashlib, io, json, os, tarfile
import ga3_board as b
def main():
    b.board()
    with b.lock():
        folders=sorted(b.ROOT.glob('results_ga3_*'));b.need(folders,'No g_a.3 result folders')
        files=[];reviews=[]
        for folder in folders:
            try:
                status=b.load(folder/'status.json')['status']
                if status=='PASS_BOARD_REPLAY_PENDING_INDEPENDENT_GROUND_RETURN':b.summarize(folder)
                else:reviews.append(dict(folder=folder.name,status=status))
            except Exception as e:reviews.append(dict(folder=folder.name,status='INCOMPLETE_OR_REVIEW_REQUIRED',reason=str(e)))
            for p in sorted(folder.rglob('*')):
                b.need(not p.is_symlink(),'result symlink unsupported')
                if p.is_file():files.append(p)
        for p in sorted((b.ROOT/'switch_logs').glob('*')):
            b.need(not p.is_symlink(),'switch log symlink unsupported')
            if p.is_file():files.append(p)
        if (b.ROOT/'HASH_CAPABILITIES.json').is_file():files.append(b.ROOT/'HASH_CAPABILITIES.json')
        if (b.ROOT/'campaign_summary.json').is_file():files.append(b.ROOT/'campaign_summary.json')
        if (b.ROOT/'compact_screen_summary.json').is_file():files.append(b.ROOT/'compact_screen_summary.json')
        if (b.ROOT/'pipeline_screen_summary.json').is_file():files.append(b.ROOT/'pipeline_screen_summary.json')
        files.extend(sorted(b.ROOT.glob('CACHE_PREPARATION_*.json')))
        files.append(b.ROOT/'COMPACT_BASELINE_PROVENANCE.json')
        for name in ('PIPELINE_BASELINE_PROVENANCE.json','CUDA_TARGET_ASSESSMENT.json','OFFLINE_HARDWARE_CANDIDATE.json'):
            if (b.ROOT/name).exists():files.append(b.ROOT/name)
        if (b.ROOT/'RECOVERY_REQUIRED.json').is_file():files.append(b.ROOT/'RECOVERY_REQUIRED.json')
        for name in ('BASELINE_PROVENANCE.json','IO_BASELINE_PROVENANCE.json','OPTIMIZATION_PLAN.json','GPU_REFERENCE.json','BUILD_IDENTITY.json','DATA_PROVENANCE.json','OFFLINE_VERIFICATION.json','HARDWARE_PROVENANCE.json','SOURCE_PROVENANCE.json','SHA256SUMS_PACKAGE'):
            files.append(b.ROOT/name)
        entries=[];total=0
        for i,p in enumerate(files):
            s=p.stat();entries.append(dict(path=p.relative_to(b.ROOT).as_posix(),bytes=s.st_size,sha256=b.sha(p)));total+=s.st_size
            if i%100==0:print(f'INDEX {i}/{len(files)} MiB={total/2**20:.1f}',flush=True)
        archive=b.ROOT/f'collected_ga3_pipeline_{b.stamp()}.tar.gz'
        with archive.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|',dereference=True) as tf:
            for p,e in zip(files,entries):
                b.need(p.stat().st_size==e['bytes'] and b.sha(p)==e['sha256'],'result changed during collection')
                tf.add(p,arcname=e['path'],recursive=False)
            payload=json.dumps(dict(status='INDEXED_GA3_RESULTS',review_required_folders=reviews,entries=entries),indent=2).encode();info=tarfile.TarInfo('COLLECTION_INDEX.json');info.size=len(payload);tf.addfile(info,io.BytesIO(payload))
        verified={}
        with tarfile.open(archive,'r:gz') as tf:
            for member in tf:
                b.need(member.isfile() and member.name not in verified,'invalid/duplicate collection member')
                f=tf.extractfile(member);h=hashlib.sha256()
                for block in iter(lambda:f.read(2**20),b''):h.update(block)
                verified[member.name]=h.hexdigest()
        b.need(all(verified[e['path']]==e['sha256'] for e in entries),'archive verification mismatch')
        print(json.dumps(dict(status='COLLECTED_AND_VERIFIED',review_required_folders=reviews,download_this_file=str(archive),files=len(verified),bytes=archive.stat().st_size,sha256=b.sha(archive)),indent=2))
if __name__=='__main__':main()
