from pathlib import Path
import hashlib,json,shutil,subprocess,tempfile
R=Path(__file__).resolve().parent;W=R.parents[1];K=W/'board_packages/v32_ga3_pipeline_20261109'
T=Path(tempfile.mkdtemp(prefix='git_transport_pipeline_',dir=R/'build'));repo=T/'repo';repo.mkdir();checkout=T/'checkout';checkout.mkdir()
def git(*args):return subprocess.run(['git','-C',str(repo),*map(str,args)],check=True,capture_output=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
entries=[(name,digest) for digest,name in (line.split('  ',1) for line in (K/'SHA256SUMS_PACKAGE').read_text('ascii').splitlines())]
entries.append(('SHA256SUMS_PACKAGE',sha(K/'SHA256SUMS_PACKAGE')))
for name,want in entries:
    p=repo/K.name/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(K/name,p);assert sha(p)==want
git('init','--quiet');git('config','user.name','Offline package validation');git('config','user.email','package-validation@example.invalid');git('config','commit.gpgsign','false');git('config','core.autocrlf','true');git('config','core.hooksPath',str(T/'no-hooks'))
git('add','--',K.name);git('commit','--quiet','--no-verify','-m','Validate sealed pipeline transport')
proc=subprocess.Popen(['git','-C',str(repo),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
for name,want in entries:
    proc.stdin.write(('HEAD:'+K.name+'/'+name+'\n').encode());proc.stdin.flush();parts=proc.stdout.readline().decode().split();assert parts[1]=='blob'
    blob=proc.stdout.read(int(parts[2]));assert proc.stdout.read(1)==b'\n';assert hashlib.sha256(blob).hexdigest()==want,name
proc.stdin.close();assert proc.wait()==0
results=[]
for autocrlf in ('true','false'):
    git('config','core.autocrlf',autocrlf);out=checkout/autocrlf;out.mkdir();git('checkout-index','--all','--prefix='+out.as_posix()+'/')
    for name,want in entries:assert sha(out/K.name/name)==want,(autocrlf,name)
    results.append(dict(core_autocrlf=autocrlf,files_checked=len(entries),all_SHA256_equal=True))
result=dict(status='PASS_ACTUAL_GIT_COMMIT_BLOBS_AND_FRESH_CHECKOUTS',manifest_sha256=sha(K/'SHA256SUMS_PACKAGE'),files=len(entries),commit=git('rev-parse','HEAD').stdout.decode().strip(),checkouts=results,scope='New isolated local test repository only; user Git index and commits not modified.')
(R/'git_transport_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps(result,indent=2))
