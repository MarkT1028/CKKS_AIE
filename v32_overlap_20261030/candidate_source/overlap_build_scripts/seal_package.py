from pathlib import Path
import datetime,hashlib,json,shutil
R=Path(__file__).resolve().parent;W=R.parents[1];S=R/'board_files';P=W/'board_packages/v32_overlap_20261030'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
def main():
    assert not P.exists(),'Use a fresh package directory'
    audit=json.loads((R/'evidence/offline_audit.json').read_text());assert audit['status']=='PASS_OVERLAP_OFFLINE_AUDIT'
    for n in ('offline_audit.json','tools_test.json','tools_test.log'):
        shutil.copy2(R/'evidence'/n,S/'offline_evidence'/n)
    for p in (R/'evidence').glob('*'):
        if p.name.startswith(('XRT_syntax_','full_partition_','parser_compile_')):shutil.copy2(p,S/'offline_evidence'/p.name)
    scripts=S/'candidate_source/overlap_build_scripts'
    for p in R.iterdir():
        if p.is_file() and p.suffix in ('.py','.sh'):shutil.copy2(p,scripts/p.name)
    notes='''# 本輪離線驗證與範圍

本套件新增主機輸出收尾與下一塊執行重疊，並補齊 AIE-only／reducer-only 的物理映像。四版仍為兩顆 AIE、225MHz PL、原 reader、相同資料及模數；硬體貢獻比較固定 map_pingpong，新主機效能比較則在同 boot 對照 map_pingpong 和 map_finish_overlap。

已完成：

- 全部16個真實區塊，以獨立非同步算術／裝置模型測新舊排程，各3輪；完整結果與保存payload逐字一致。此模型沒有 XRT，不是板上執行，也不提供性能預測。
- 單區塊零值、最大60-bit殘值、隨機值及多區塊重用檢查。8類故障於首／中／末位置注入，包含準備、啟動前、啟動後、等待、狀態、收尾、輸出破壞、匯出失敗；確認終止及工作執行緒清理。
- AddressSanitizer、UndefinedBehaviorSanitizer 及 ThreadSanitizer 通過。ThreadSanitizer 使用 setarch x86_64 -R 適配本機映射，僅影響該次測試程序，沒有變更全域設定。
- 兩個缺少的硬體組合，以實際 AIE 模擬輸出串接 reducer 的C及隨機停等RTL：每組兩核心各896frame、100352beats，共5376個端點係數符合golden，涵蓋14tower與16對密文。這是檔案串接驗證，不是完整PL/AIE同時模擬。
- 兩份新映像皆完成實際物理佈線、正setup／hold裕量、DRC0、route0與bus-skew檢查。實際使用的XO／libadf、clock config、boot image及flat metadata UUID和雜湊已綁定於SOURCE_MATRIX與SOURCE_PROVENANCE。
- 四份host通過官方XRT標頭的完整分支語法檢查、真實16區塊拆分合併與預期結果比較；正式ARM連結仍由板上的build_board.sh完成。
- 同boot正反序命令、CPU前後測、trace統計、模式／boot分組、錯誤資料拒絕、CPU診斷及壓縮檔索引測試通過。CPU算術來源、原排程、新v32主程式及前四個凍結套件均未改。

舊版核心、AIE週期與前輪驗收紀錄保留於offline_evidence；本輪兩個新物理映像在各variant命名的子資料夾，本輪host／工具測試檔以model、edge、asan、tsan、tools及diagnostics命名。

尚未完成本輪板測，不預填加速比。前輪624.600ms是原主機排程的歷史結果；本輪必須比較同boot相同框架的完整wall。新execute_sum_ms是start-to-wait-return主機區間，可能含前塊輸出收尾，不能直接當成純PL／AIE運算時間。setup、獨立export replay、網路、重建密文及全模型仍另列。新的板上輸出回傳後才能作本輪原context解密與續算驗收。

目前仍是一組固定真實h_s.4輸入；離線邊界資料不是新的真實推論組別。更多workload／level、reader事件profiling、即時跨機服務與能耗是後續項目。套件沒有私鑰，沒有修改板子或自動重新開機。
'''
    (S/'OFFLINE_FINDINGS.md').write_text(notes,encoding='utf-8',newline='\n')
    write(S/'OFFLINE_VERIFICATION.json',dict(status='OFFLINE_FUNCTIONAL_AND_ROUTED_VERIFIED_BOARD_SPEED_PENDING',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),board_tested=False,board_performance='PENDING',hardware_programmed=False,checks=audit,cryptographic_scope='All model residues equal the validated golden. New board outputs still require original-context decryption and continuation checks.',primary_metric='All-16-chunk actual resident replay wall including full materialized merge and verification; excludes one-time setup, trace writes and separate export replay.'))
    P.mkdir()
    for f in S.rglob('*'):
        rel=f.relative_to(S)
        if not f.is_file() or any(x in ('__pycache__','bin') for x in rel.parts):continue
        assert not f.is_symlink();dst=P/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
    for f in P.rglob('*'):
        if f.is_file() and (f.suffix in ('.py','.sh','.cpp','.hpp','.md','.json','.tsv','.txt','.rpt','.log','.cfg') or f.name in ('.gitattributes','.gitignore','ckks-perf2-srst','EXPECTED_BOOT_SHA256','EXPECTED_BOOT_UUID')):
            data=f.read_bytes();fixed=data.replace(b'\r\n',b'\n')
            assert not f.relative_to(P).as_posix().startswith('reference/') or data==fixed
            f.write_bytes(fixed)
    for n,h in json.loads((P/'SOURCE_PROVENANCE.json').read_text())['frozen_reference_files'].items():assert sha(P/n)==h
    members=sorted([f.relative_to(P).as_posix() for f in P.rglob('*') if f.is_file()]+['PACKAGE_STATUS.json'])
    write(P/'PACKAGE_STATUS.json',dict(status='OFFLINE_VERIFIED_READY_FOR_BOARD',package=P.name,board_tested=False,board_performance='PENDING',contains_new_firmware=True,hardware_programmed=False,expected_variants=json.loads((P/'VARIANTS.json').read_text()),base_package='v32_hs4_20261027',base_manifest_sha256='db3bcc84a5cd925868e476ba2e6a2a4feb56fd4806fd3344a5f9940aba999d3b',expected_manifest_members=members))
    (P/'SHA256SUMS_PACKAGE').write_text(''.join(sha(P/n)+'  '+n+'\n' for n in members),encoding='utf-8',newline='\n')
    print('SEALED_OVERLAP_PACKAGE',P,len(members),sha(P/'SHA256SUMS_PACKAGE'))
if __name__=='__main__':main()
