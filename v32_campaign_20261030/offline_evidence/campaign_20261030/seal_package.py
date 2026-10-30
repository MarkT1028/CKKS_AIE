from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent;W=R.parents[1];S=R/'board_files';P=W/'board_packages/v32_campaign_20261030';OLD=W/'board_packages/v32_overlap_20261030'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def main():
    assert not P.exists(),'Keep each sealed package immutable'
    tests={p.stem:json.loads(p.read_text()) for p in (R/'evidence').glob('*_test.json')}
    for name in ('study_test','driver_test','legacy_test'):assert tests[name]['status'].startswith('PASS'),name
    native=json.loads((R/'evidence/native_checks.json').read_text());assert native['status']=='PASS_UNCHANGED_ARITHMETIC_AND_NATIVE_HOST_CHECKS'
    same=[]
    for folder in ('host','common','reference','tests','variants','candidate_source'):
        for f in (OLD/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:
                assert sha(f)==sha(S/f.relative_to(OLD)),f;same.append(f.relative_to(OLD).as_posix())
    evidence=S/'offline_evidence/campaign_20261030';evidence.mkdir(exist_ok=True)
    for p in (R/'evidence').glob('*'):
        if p.is_file():shutil.copy2(p,evidence/p.name)
    for p in R.glob('*.py'):shutil.copy2(p,evidence/p.name)
    # Windows-created test receipts may contain CRLF. Normalize only this new
    # evidence subtree; all inherited source/image bytes remain unchanged.
    for p in evidence.rglob('*'):
        if p.is_file() and p.suffix in ('.py','.json','.log','.md','.txt'):
            raw=p.read_bytes();p.write_bytes(raw.replace(b'\r\n',b'\n'))
    source=json.loads((S/'SOURCE_PROVENANCE.json').read_text());source['campaign_control_overlay']=dict(parent_package='v32_overlap_20261030',parent_manifest_sha256=sha(OLD/'SHA256SUMS_PACKAGE'),unchanged_source_members=same,all_four_image_bytes_unchanged=True,arithmetic_and_CPU_unchanged=True,new_protocol_sha256=sha(S/'STUDY_PROTOCOL.json'),new_board_results='PENDING');write(S/'SOURCE_PROVENANCE.json',source)
    write(S/'OFFLINE_VERIFICATION.json',dict(status='OFFLINE_RESEARCH_PROTOCOL_VERIFIED_NEW_BOARD_DATA_PENDING',new_firmware_compiled=False,all_four_physical_images_reused_byte_exact=True,host_arithmetic_changed=False,old_frozen_package_unchanged=True,checks=tests,native_checks=native,board_tested=False,board_performance='PENDING',crypto='PENDING_NEW_ACTUAL_BOARD_OUTPUTS',scope='Synthetic protocol/fault tests and unchanged native source checks are not hardware performance or a new decryption result.'))
    (S/'OFFLINE_FINDINGS.md').write_text('# 本輪範圍\n\n本版只新增三boot主機比較、兩個反序四格硬體區組、進度／所有權／雜湊控制與分階段收集。沿用前輪四份實際routed映像、CPU、host運算與排程數學來源，沒有新增硬體映像。\n\n離線證據見offline_evidence/campaign_20261030。原先offline_evidence的其餘內容是前輪歷史建置與模型證據，不是本輪新板測。新套件尚未上板，亦未驗證新輸出的解密續算。已驗收545.388ms只作歷史參考，沒有設成接受門檻。\n',encoding='utf-8',newline='\n')
    P.mkdir()
    for f in S.rglob('*'):
        rel=f.relative_to(S)
        if f.is_file() and '__pycache__' not in rel.parts:
            assert not f.is_symlink();q=P/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,q)
    # Preserve all reused bytes. New text is created with explicit LF.
    members=sorted([f.relative_to(P).as_posix() for f in P.rglob('*') if f.is_file()]+['PACKAGE_STATUS.json'])
    write(P/'PACKAGE_STATUS.json',dict(status='OFFLINE_VERIFIED_RESEARCH_CAMPAIGN_READY_FOR_BOARD',package=P.name,board_tested=False,board_performance='PENDING',contains_new_firmware=False,contains_four_reused_boot_images=True,hardware_programmed=False,expected_variants=json.loads((P/'VARIANTS.json').read_text()),base_package='v32_hs4_20261027',base_manifest_sha256='db3bcc84a5cd925868e476ba2e6a2a4feb56fd4806fd3344a5f9940aba999d3b',expected_manifest_members=members))
    (P/'SHA256SUMS_PACKAGE').write_text(''.join(sha(P/n)+'  '+n+'\n' for n in members),encoding='utf-8',newline='\n')
    facts=dict(status='SEALED_RESEARCH_CAMPAIGN',files=len(members)+1,manifest_sha256=sha(P/'SHA256SUMS_PACKAGE'),unchanged_source_members=len(same),new_board_performance='PENDING');write(R/'evidence/sealed.json',facts);print(json.dumps(facts,indent=2))
if __name__=='__main__':main()
