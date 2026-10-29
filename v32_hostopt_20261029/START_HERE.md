# 真實 v32：主機資料快取與拆路優化，2026-10-29

此版只調整主機程式。兩顆 AIE、PL reducer、7 組對角和、數學運算與硬體映像皆沿用上一版。**已完成離線功能測試，候選速度尚未上板確認。**

## 上傳哪個資料夾

把 `v32_hostopt_20261029` 整個資料夾放到既有 `v32_hs4_20261027` 旁邊：

```text
/root/114C75007/vek280/AIE/
  v32_hs4_20261027/       # 保留原本的資料、映像，不必重新上傳
  v32_hostopt_20261029/   # 本次的新資料夾
```

這是小型增補套件，不含近 1 GB 的輸入，也不含新韌體。舊套件須完整，凍結清單 SHA256 為 `db3bcc84a5cd925868e476ba2e6a2a4feb56fd4806fd3344a5f9940aba999d3b`。若舊套件不在旁邊，可先設定 `export V32_BASE_PACKAGE=/完整路徑/v32_hs4_20261027`；後續每次執行都須保留設定。

## 在板上依序執行

```sh
cd /root/114C75007/vek280/AIE/v32_hostopt_20261029
sh check_package.sh
sh build_board.sh
python3 board_runner.py detect
```

偵測結果應為 `v32_diag_2_pipe`，UUID `6719127d5f785a7fa4fab0a9869d6ccd`。如果板子仍是上次真實 v32 測試的映像，這次直接測試即可。本套件不會寫入開機槽位，也沒有切換或重開機功能。

```sh
sh run_board.sh smoke
sh run_board.sh formal
sh run_board.sh formal --reverse
python3 collect_results.py
```

一次跑完前一行成功後才跑下一行；不要平行執行。`smoke` 每組一次，確認正確性；兩輪 `formal` 以正序、反序各比較三組，降低固定測試順序的影響。正式測試每組硬體為 1 次暖機＋5 次量測，前後各有 CPU 雙執行緒的 1 次暖機＋3 次量測。輸出最後顯示的 `collected_hostopt_*.tar.xz` 給我分析即可。

## 三組差異

| 模式 | 輸入與 golden | 拆路 | CPU 對照 |
|---|---|---|---|
| `stream_scalar` | 每輪逐 chunk 重讀、解析 | 原逐筆 push_back | 原逐 chunk 讀取 |
| `resident_scalar` | 一次載入，固定重用主機 buffer | 原逐筆 push_back | 同樣一次載入 |
| `resident_block` | 與快取版相同 | 每對密文、每個 tower 以連續區塊複製 | 同樣一次載入 |

第一組是實際測過的原版主機／CPU 原始碼快照。第二組比較快取與固定 buffer；第三組只改拆路，因此可單獨量出區塊複製的效果。

## 如何解讀時間

- `setup.json`：快取版本的一次性資料讀取、解析、canonical 檢查與配置。約 896 MiB 輸入＋42 MiB golden 留在一般主機 RAM，沒有把整份資料放入 CMA。板上 4 GB RAM 的既有環境足以進行單一程序測試。
- `transaction_ms`：每個 chunk 的拆路、上傳與輸出 poison、硬體主流程、讀回合併、完整整數驗證。快取版不再於每輪重讀固定輸入；串流版仍含逐輪載入。
- `execution_ms`：原有 PL／AIE 執行區段；硬體沒改，不預先宣稱這項會變快。
- `full_replay_ms`：完整 16 個 chunk 的該輪時間，最後一輪仍包含原先的輸出存檔。保留這一筆，不刪除存檔較慢樣本。
- `*.command.json`：整個子程序耗時，包含一次設定、全部暖機與量測、最後輸出存檔；不能把不同重複次數的 CPU 與硬體整個程序時間直接相除。
- `comparison.json`／`comparison.txt`：從 CSV 重算的各模式結果、前後 CPU 漂移與兩項修改的分別比較。相位的中位數相加不等於整體中位數。

快取版適用於相同輸入持續重播的常駐比較；真實服務每換一批輸入，仍須付出那一批資料的接收與準備成本。這次沒有加入雙緩衝、傳輸／運算重疊，也沒有加速最後輸出寫檔。CPU 運算維持原本 U128 累加後取模的同一份程式與兩個工作執行緒，不代表最佳化 CPU 的效能上限。

## 正確性與內測範圍

`OFFLINE_VERIFICATION.json` 與 `offline_evidence/` 記錄實際執行的測試。包含完整真實輸入的新舊拆路相等、完整 CPU 輸出逐位元相等、單／雙執行緒、重複 buffer 使用、異常輸入拒絕、ASan／UBSan、官方 XRT 標頭語法檢查及 Git／ZIP 傳輸檢查。這些是本機功能驗證，並非板上加速成績。

每次板上計算仍會檢查全部 5,505,024 個輸出 residue；每組保留最後 16 個原始輸出檔，後續可用原始 OpenFHE context 再做回灌、解密與續算驗證。上板前尚無這個候選的硬體回傳檔，故不能將本機 CPU 的正確結果當作新版本已解密驗證。

支援目前 `N=131072, L=14, K=16`、16 個一致參數的 chunk。快取解析器另測過較小尺寸，但這份套件沒有擴充多組 tower grid、不同工作批次或即時 v32 RPC。
