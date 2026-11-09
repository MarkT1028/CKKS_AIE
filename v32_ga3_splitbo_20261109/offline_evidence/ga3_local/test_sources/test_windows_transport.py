"""Local-only Git remote / CMD-compatible PowerShell transport round trip."""
from pathlib import Path
import gzip,hashlib,io,json,os,shutil,subprocess,tarfile,time
R=Path(__file__).resolve().parents[1]
def main():
    base=Path('D:/CodexBuilds/v32_ga3_20261104')/('transport_test_'+str(time.time_ns()));base.mkdir()
    repo=base/'repo';repo.mkdir();partsroot=repo/'v32_ga3_20261104_gitdata';meta=partsroot/'meta';meta.mkdir(parents=True)
    for p in (R/'transport_templates').iterdir():shutil.copy2(p,meta/p.name)
    payload=os.urandom(512*1024);buffer=io.BytesIO()
    with gzip.GzipFile(fileobj=buffer,mode='wb',compresslevel=1,mtime=0) as z,tarfile.open(fileobj=z,mode='w|') as tf:
        info=tarfile.TarInfo('v32_ga3_20261104_data/test.bin');info.size=len(payload);tf.addfile(info,io.BytesIO(payload))
    archive=buffer.getvalue();parts=[]
    for i,offset in enumerate(range(0,len(archive),32768)):
        b=archive[offset:offset+32768];p=partsroot/f'batch_{i//9+1}'/f'part_{i:04}.part';p.parent.mkdir(exist_ok=True);p.write_bytes(b);parts.append(dict(path=p.relative_to(partsroot).as_posix(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
    manifest=dict(parts=parts,batches=2,archive_name='test.tar.gz',archive_bytes=len(archive),archive_sha256=hashlib.sha256(archive).hexdigest(),data_files={'test.bin':dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())})
    (meta/'TRANSFER_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8');(partsroot/'.gitattributes').write_text('* text=auto eol=lf\n*.part -text\n',encoding='ascii');(partsroot/'.gitignore').write_text('/batch_*/\n/release_data/\n',encoding='ascii')
    logs=[]
    def run(cmd,good=True):
        p=subprocess.run(list(map(str,cmd)),cwd=base,capture_output=True,text=True,encoding='utf-8',errors='replace');logs.append(dict(command=list(map(str,cmd)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert (p.returncode==0)==good,(cmd,p.stdout,p.stderr);return p.stdout.strip()
    remote=base/'remote.git';run(['git','init','--bare',remote]);run(['git','-C',remote,'symbolic-ref','HEAD','refs/heads/main']);run(['git','init','-b','main',repo]);run(['git','-C',repo,'config','user.name','GA3 local transport test']);run(['git','-C',repo,'config','user.email','ga3-test@example.invalid']);run(['git','-C',repo,'remote','add','origin',remote]);run(['git','-C',repo,'add','--',str(meta.relative_to(repo)),str((partsroot/'.gitattributes').relative_to(repo)),str((partsroot/'.gitignore').relative_to(repo))]);run(['git','-C',repo,'commit','-m','Initial local-only transport test']);run(['git','-C',repo,'push','-u','origin','main'])
    run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',meta/'push_all_batches.ps1'])
    checkout=base/'checkout';run(['git','-c','core.autocrlf=true','clone',remote,checkout]);restore=checkout/'v32_ga3_20261104_gitdata/meta/restore_data.ps1';out=base/'restored.tar.gz'
    run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',restore,'-Destination',out]);assert hashlib.sha256(out.read_bytes()).hexdigest()==manifest['archive_sha256']
    run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',restore,'-Destination',out])
    p=checkout/'v32_ga3_20261104_gitdata'/parts[0]['path'];b=bytearray(p.read_bytes());b[0]^=1;p.write_bytes(b)
    corrupt=base/'corrupt_should_not_exist.tar.gz';run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',restore,'-Destination',corrupt],False);assert not corrupt.exists()
    before=run(['git','-C',repo,'rev-parse','HEAD']);(repo/'unrelated.txt').write_text('unrelated staged change',encoding='ascii');run(['git','-C',repo,'add','unrelated.txt']);run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',meta/'push_batch.ps1','-Batch','1'],False);assert run(['git','-C',repo,'rev-parse','HEAD'])==before
    result=dict(status='PASS_WINDOWS_LOCAL_GIT_BATCH_RESTORE',test_path=str(base),local_only=True,remote_network_push=False,parts=len(parts),batches=2,checks=['two automatic batches','Windows checkout autocrlf','actual archive SHA256','idempotent restore','corrupt part rejection before output creation','unrelated staged files protected'],logs=logs)
    (R/'build/windows_transport_test.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'])
if __name__=='__main__':main()
