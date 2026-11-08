# g_a.3 無損輸入快取：減少含 I/O 的總請求時間

這是新候選套件；**板上時間尚未測得**。兩個硬體映像、算術、參數、CPU 對照和完整 canonical SHA256 輸出驗證都沿用上一版。這次不增加 AIE，也不更換 FPGA 韌體。

上一輪 16 視窗短測的 SHA256 路徑約 57.93 秒，其中約 55.59 秒是資料載入。因此先減少輸入讀取量，而不是只縮短約 2.33 秒的常駐運算。

## 這次改什麼

- 原始 residue 是 uint64，但每個模數只需要 45、46 或 51 個有效位元；依各模數的實際位數做**無損**位元封裝，讀取後還原原本 uint64。
- 完整輸入 payload 原為 35,567,697,920 bytes（33.125 GiB），新快取含標頭為 25,564,935,680 bytes（約 23.81 GiB）。輸入資料量約少 28.12%；**不能直接當成時間降幅**。
- 建立快取時讀完整原始輸入、核對封存 SHA256、編碼、寫入、fsync，再從實際新檔讀回、解碼、核對原始 canonical SHA256。原資料完全保留。
- 可先建立約 1 GiB 以下的短測快取；可選完整快取或 8 GiB 的混合快取。混合模式未列入快取的輸入明確走原路徑；已列入的快取若遺失或變動，會失敗，不能偷偷退回原始檔案。
- 快取可中斷續建。已完成檔案身份改變時拒絕直接使用，需重新驗證。
- 比較 SHA256 原始路徑和 packed 路徑，兩者都驗證全部輸出，不讀預期輸出 payload。相同 BO、相同輸入退休提示，沒有全域清快取或調時脈。

## 上傳內容

只上傳 `v32_ga3_compactio_20261108` 程式資料夾到板子既有 AIE 目錄，不必重傳 43 GiB 測資。既有 `v32_ga3_20261104_data` 必須保留。快取由板子建立，不放進 Git。

## 先做短測

每行分開執行：

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_compactio_20261108
sh check_package.sh
sh build_board.sh
python3 ga3_board.py detect
python3 compact_cache.py plan pilot
python3 compact_cache.py prepare pilot
sh run_screen.sh
python3 collect_results.py
```

`detect` 應識別 `v32_core_2_pipe` 或 `v32_native_pl_2_pipe`。若原本已是其中之一，不需重開機。本套件不會自動切換或重開機。

`prepare pilot` 只操作 CPU 和新快取檔案，**不啟動 PL/AIE**。會逐檔顯示 `CACHE_VERIFIED`，完成後顯示 `PASS_CACHE_READY`。如果中斷，重跑相同命令即可續建；不要在硬體運算中按 Ctrl+C。

`run_screen.sh` 先對原始／壓縮路徑做 smoke，再按「原始降序 → 壓縮降序 → 壓縮升序 → 原始升序」測 16 個視窗。這是短測，不是整層延遲；含 I/O 的時間才是本輪主要指標。兩個壓縮短測共用同一份快取。

請把 `collect_results.py` 指定的壓縮檔給我；先看總時間、解碼成本、原始前後漂移與損益平衡，再決定完整比較。

## 完整快取與完整 MAC 工作量

短測結果合理後，板上需至少約 26 GiB 可用空間（含 2 GiB 保留）。目前你提供的 53 GB 可用空間足夠。原始資料夾仍保留。

```sh
python3 compact_cache.py plan full
python3 compact_cache.py prepare full
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_full
python3 compact_cache.py check
sh run_board.sh stream sha256 descending
sh run_board.sh stream packed descending
sh run_board.sh stream packed ascending
sh run_board.sh stream sha256 ascending
python3 summarize_compact.py
python3 collect_results.py
```

這四次是 1024 視窗的完整 raw MAC 請求，會比較久，因為完整讀取仍有數十 GiB。相同硬體、相同工作量、前後原版對照；之後再依 `switch_board.sh` 的 check／arm 流程換另一個硬體，重用同一快取，不能同時跑兩個硬體實驗。

若只有 17 GB 空間，可改 `python3 compact_cache.py prepare bounded --budget-gib 8`，然後設定 `V32_GA3_CACHE=.../v32_ga3_compact_cache_bounded`。它仍可跑完整工作量，但只有部分輸入壓縮，需明確報告混合覆蓋率。

## 時間怎麼看

- `campaign_wall_ms`：資料載入、解碼、打包、同步、運算、完整驗證及該次結果紀錄的應用請求時間。
- `setup_ms + campaign_wall_ms`：再加上 XRT／BO 等初始化。
- `runner_wall_ms`：再納入控制器檢查、資料身份檢查和結果處理；不包含啟動 Python／import 的時間。本輪短測以這個數字做主要比較。
- `preparation_work_ms`：另外記錄的**一次性快取建立／驗證成本**，含原始讀取、編碼、新檔寫入、fsync、讀回、解碼和雜湊。中斷過的已記錄工作也累加。
- **首次使用總成本 = 建立快取成本 + 壓縮路徑 runner 時間**。可能比直接執行慢；只有重複使用才能攤提。報告會列損益平衡的重複次數，不能把準備時間藏起來。
- `bytes`／`read_payload_bytes` 是實際向 pread 請求的 payload bytes，**不是實體磁碟讀取量**；`logical_input_bytes` 是解開後大小。OS page cache 和裝置內部行為仍可能影響結果。
- `range_ms` 含 packed 路徑解碼及 canonical 範圍檢查；`decode_ms` 是該段的另列值，不應與 `range_ms` 重複加總。其他流水線階段也可能重疊，不能把階段和稱為請求時間或裝置 cycles。

## 驗證與範圍

離線測試結果以 `OFFLINE_VERIFICATION.json` 為準。軟體模型與 ARM64 QEMU 只證明軟體正確性，不代表 FPGA 效能。原始資料、私鑰與原 v32 程式皆不修改。

這仍是從真實 g_a.3 擷取的 raw MAC 工作量。旋轉、im2col、relinearization、activation 與 live v32 傳輸不在板上測量範圍；不能直接與原 CUDA 整層 26 秒相比。新套件的完整原上下文回填驗證須待板上輸出回收後完成。

官方 API 參考：[pread](https://man7.org/linux/man-pages/man2/pread.2.html)、[posix_fadvise](https://man7.org/linux/man-pages/man2/posix_fadvise.2.html)、[OpenSSL EVP](https://docs.openssl.org/3.0/man3/EVP_DigestInit/)。位元封裝是本套件自己的可逆儲存格式，已用獨立位元參考實作、sanitizer 與 ARM64 測試驗證，沒有把壓縮當成密文算術優化。
