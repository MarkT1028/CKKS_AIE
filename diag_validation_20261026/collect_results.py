#!/usr/bin/env python3
"""Collect result folders, build identities and switch logs without fixtures/keys."""
from pathlib import Path
import datetime as dt,hashlib,json,tarfile
import validation_common as v
def main():
    package=v.check_package();root=v.ROOT
    files=set()
    for parent in [root,v.COMPARISON]:
        for p in parent.glob('results_*'):
            if p.is_dir():files.update(x for x in p.rglob('*') if x.is_file())
        for name in ['bin','switch_logs']:
            if (parent/name).is_dir():files.update(x for x in (parent/name).rglob('*') if x.is_file())
    v.require(any('/results_' in x.as_posix() for x in files),'No result directories to collect')
    for parent in [root,v.COMPARISON]:files.add(parent/'SHA256SUMS_PACKAGE')
    for name in ['PACKAGE_STATUS.json','OFFLINE_VERIFICATION.json','references/a1_b1_identity.json','references/profiling_mapping.json','fresh_fixtures/registry.json']:
        files.add(root/name)
    for p in files:v.require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()),'Unsafe collection path')
    try:
        import lzma
        compression='xz';options={'preset':6}
    except ImportError:
        compression='gz';options={}
    archive=root/('collected_results_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.tar.'+compression)
    v.require(not archive.exists(),'Archive exists')
    manifest={'schema':'ckks_collected_results_v1','package':package,'contains_private_material':False,
              'files':[{'path':p.relative_to(root).as_posix(),'sha256':v.sha(p),'bytes':p.stat().st_size} for p in sorted(files)]}
    record=json.dumps(manifest,indent=2).encode('utf-8')
    import io
    print('COLLECTING_RESULTS compression='+compression+' files='+str(len(files)),flush=True)
    with tarfile.open(archive,'x:'+compression,**options) as tar:
        for p in sorted(files):tar.add(p,arcname='diag_validation_results/'+p.relative_to(root).as_posix(),recursive=False)
        info=tarfile.TarInfo('diag_validation_results/COLLECTION.json');info.size=len(record);tar.addfile(info,io.BytesIO(record))
    with tarfile.open(archive,'r:*') as tar:
        for m in manifest['files']:
            f=tar.extractfile('diag_validation_results/'+m['path']);v.require(f is not None and hashlib.sha256(f.read()).hexdigest()==m['sha256'],'Archive verification failed')
    print(json.dumps({'status':'COLLECTED_AND_VERIFIED','download_this_file':str(archive),'files':len(files)+1,'bytes':archive.stat().st_size,'sha256':v.sha(archive)},indent=2))
if __name__=='__main__':main()
