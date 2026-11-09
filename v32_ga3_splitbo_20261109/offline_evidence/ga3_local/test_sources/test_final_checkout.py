"""Isolated local checkout of sealed delivery, including Windows autocrlf."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
R=Path(__file__).resolve().parents[1];W=R.parents[1];K=W/'board_packages/v32_ga3_20261104';G=R/'git_transport_full'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    base=Path('D:/CodexBuilds/v32_ga3_20261104')/('final_checkout_'+str(time.time_ns()));repo=base/'repo';repo.mkdir(parents=True);logs=[]
    for source,target,manifest in [(K,repo/K.name,'SHA256SUMS_PACKAGE'),(G/'meta',repo/'v32_ga3_20261104_gitdata/meta','SHA256SUMS_META')]:
        target.mkdir(parents=True)
        for line in (source/manifest).read_text(encoding='ascii').splitlines():
            digest,name=line.split('  ',1);p=source/name;assert sha(p)==digest,name;out=target/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
        shutil.copy2(source/manifest,target/manifest)
    for name in ('.gitattributes','.gitignore'):shutil.copy2(G/name,repo/'v32_ga3_20261104_gitdata'/name)
    (repo/'.gitignore').write_text('*.log\n__pycache__/\n',encoding='ascii')
    hidden=repo/'v32_ga3_20261104_gitdata/batch_1';hidden.mkdir();(hidden/'test_should_stay_ignored.part').write_bytes(b'not complete data')
    def run(cmd,good=True):
        p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,encoding='utf-8',errors='replace');logs.append(dict(command=list(map(str,cmd)),returncode=p.returncode,stdout=p.stdout[-5000:],stderr=p.stderr[-5000:]));assert (p.returncode==0)==good,(cmd,p.stdout[-3000:],p.stderr[-3000:]);return p
    run(['git','init','-b','main',repo]);run(['git','-C',repo,'config','user.name','GA3 isolated delivery QA']);run(['git','-C',repo,'config','user.email','ga3-delivery@example.invalid']);run(['git','-C',repo,'add','.'])
    tracked=run(['git','-C',repo,'ls-files']).stdout.splitlines();assert not any('/batch_' in p for p in tracked)
    run(['git','-C',repo,'commit','-m','Local sealed delivery test, no network'])
    checkout=base/'checkout';run(['git','-c','core.autocrlf=true','clone','--local',repo,checkout])
    checked=0
    for target,manifest in [(checkout/K.name,'SHA256SUMS_PACKAGE'),(checkout/'v32_ga3_20261104_gitdata/meta','SHA256SUMS_META')]:
        for line in (target/manifest).read_text(encoding='ascii').splitlines():
            h,name=line.split('  ',1);assert sha(target/name)==h,('checkout SHA changed',name);checked+=1
    def linux(p):return '/mnt/'+str(p)[0].lower()+'/'+str(p)[3:].replace('\\','/')
    kit=checkout/K.name;cli=linux(kit/'ga3_board.py')
    run(['wsl.exe','-d','Ubuntu','--','python3',cli,'code-check'])
    shell=[linux(p) for p in kit.rglob('*.sh')]
    for p in shell:run(['wsl.exe','-d','Ubuntu','--','sh','-n',p])
    # Altered required source must fail before loading any device.
    original=(kit/'host/ga3_host.cpp').read_bytes();(kit/'host/ga3_host.cpp').write_bytes(original+b'\n')
    run(['wsl.exe','-d','Ubuntu','--','python3',cli,'code-check'],False);(kit/'host/ga3_host.cpp').write_bytes(original)
    # Re-seal deliberately malformed metadata to test structural validation,
    # independently of the ordinary checksum failure above.
    reg=kit/'WINDOW_VARIANTS.json';registry_bytes=reg.read_bytes();manifest=kit/'SHA256SUMS_PACKAGE';manifest_bytes=manifest.read_bytes();registry=json.loads(registry_bytes)
    metadata=kit/'variants/v32_native_pl_2_pipe/ckks_hw_boot.xclbin';metadata_bytes=metadata.read_bytes();changed=bytearray(metadata_bytes);changed[332]=1;metadata.write_bytes(changed)
    registry['v32_native_pl_2_pipe']['metadata_sha256']=sha(metadata);reg.write_text(json.dumps(registry),encoding='utf-8')
    rows=[]
    for line in manifest.read_text(encoding='ascii').splitlines():
        _,name=line.split('  ',1);rows.append(sha(kit/name)+'  '+name+'\n')
    manifest.write_text(''.join(rows),encoding='ascii');bad=run(['wsl.exe','-d','Ubuntu','--','python3',cli,'code-check'],False);assert 'flat xclbin metadata mismatch' in bad.stdout+bad.stderr
    metadata.write_bytes(metadata_bytes);reg.write_bytes(registry_bytes);manifest.write_bytes(manifest_bytes)
    run(['wsl.exe','-d','Ubuntu','--','python3',cli,'code-check'])
    result=dict(status='PASS_SEALED_WINDOWS_GIT_CHECKOUT_AND_STRUCTURAL_GUARDS',test_path=str(base),network_push=False,board_executed=False,verified_files=checked,shell_scripts_checked=len(shell),checks=['required files tracked despite root log-ignore','large parts ignored on ordinary git add','Windows autocrlf preserves every required SHA','code-check passes on WSL without board access','required-file change rejects','rehashed malformed flat xclbin rejects'],logs=logs)
    (R/'build/final_checkout.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'],checked)
if __name__=='__main__':main()
