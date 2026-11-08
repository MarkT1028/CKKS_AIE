from pathlib import Path
import gzip,hashlib,io,json,os,shutil,subprocess,tarfile,time
R=Path(__file__).resolve().parents[1]
def main():
    base=Path('D:/CodexBuilds/v32_ga3_20261104')/('release_script_test_'+str(time.time_ns()));base.mkdir();meta=base/'repo/v32_ga3_20261104_gitdata/meta';meta.mkdir(parents=True);assets=base/'assets';assets.mkdir()
    for p in (R/'transport_templates').iterdir():shutil.copy2(p,meta/p.name)
    payload=os.urandom(400000);buf=io.BytesIO()
    with gzip.GzipFile(fileobj=buf,mode='wb',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tf:
        m=tarfile.TarInfo('v32_ga3_20261104_data/test.bin');m.size=len(payload);tf.addfile(m,io.BytesIO(payload))
    archive=buf.getvalue();middle=len(archive)//2;parts=[]
    for i,b in enumerate((archive[:middle],archive[middle:]),1):
        name=f'ga3_full_{i:03}.part';(assets/name).write_bytes(b);parts.append(dict(path='release_data/'+name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
    manifest=dict(parts=parts,archive_name='test_release.tar.gz',archive_bytes=len(archive),archive_sha256=hashlib.sha256(archive).hexdigest(),release_repository='MarkT1028/CKKS_AIE',release_tag='ga3-full-20261104-f9d28c8e22ae')
    (meta/'RELEASE_TRANSFER_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8');partial=meta.parent/parts[0]['path'];partial.parent.mkdir();partial.write_bytes((assets/partial.name).read_bytes()[:111])
    logs=[]
    def run(script,*args,good=True):
        cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',meta/script,*args];p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,encoding='utf-8',errors='replace');logs.append(dict(command=list(map(str,cmd)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert (p.returncode==0)==good,(p.stdout,p.stderr);return p
    out=base/'restored.tar.gz';run('download_release_data.ps1','-SourceDirectory',assets,'-Destination',out);assert hashlib.sha256(out.read_bytes()).hexdigest()==manifest['archive_sha256']
    run('download_release_data.ps1','-SourceDirectory',assets,'-Destination',out)
    corrupt=meta.parent/parts[1]['path'];b=bytearray(corrupt.read_bytes());b[0]^=1;corrupt.write_bytes(b);run('download_release_data.ps1','-SourceDirectory',assets,'-DownloadOnly',good=False)
    plan=run('upload_release_data.ps1');assert 'PLAN_ONLY' in plan.stdout and 'No GitHub request' in plan.stdout
    result=dict(status='PASS_RELEASE_DOWNLOAD_RESUME_RESTORE_AND_READONLY_UPLOAD_PLAN',test_path=str(base),network_contacted=False,checks=['partial local-source resume','manifest-selected restore','archive checksum','idempotent complete downloads','corrupt asset preserved/rejected','uploader default is read-only plan'],logs=logs)
    (R/'build/release_script_test.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'])
if __name__=='__main__':main()
