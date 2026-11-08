# g_a.3 主機記憶體路徑優化 — 2026-11-08

這是新的候選套件。沿用既有 **雙 AIE／原生純 PL、兩路、PL 225 MHz** 映像，**不用重新產生或上傳 43 GiB 測資**。不會自動寫開機檔、改 CPU 時脈、清除全域快取或重開機。

目前只完成離線檢查；本輪上板效能 **PENDING**。不宣稱已超越原 CUDA g_a.3 約 25.66 秒。該數字來自原 Phantom GPU 的整層紀錄，與本套件 OpenFHE raw MAC 的上下文及計時範圍不同，不能直接當正式加速比。

## 實作內容

1. **區塊打包**：在 32 KiB 暫存區整理連續輸入，再成批複製到正常 BO，避免逐字交錯寫入映射記憶體。
2. **可快取 BO 候選**：依 AMD XRT 官方 API 對輸入／輸出申請 `xrt::bo::flags::cacheable`；ARM64 使用 NEON `LD2/ST4` 整理四欄輸入。仍保留每次必要的 TO_DEVICE／FROM_DEVICE 同步。
3. **單次合併並驗證**：把兩路輸出複製到完整 canonical 結果時立即比對對應的參考區段。每個 tower、每路、每個 word 都必須通過，結果仍完整留在合併緩衝區。輸出 BO 的未寫入哨兵與同步檢查保留。
4. **重用載入緩衝區**：baby、四組 weight 與參考答案沿用已配置容量，減少每個視窗重新配置／清零。仍完整 pread、逐值範圍檢查並核對檔案身分，不省略讀取或使用未覆寫的舊值。
5. **載入子階段計時**：另列 header、配置、pread、範圍檢查、檔案身分檢查及退快取；不把 32 分鐘全部先歸因於 SD 卡。

CPU 參考仍走原本的打包與算術程式；兩個硬體後端採相同候選記憶體路徑。資料格式、完整 N=131072、L=53、K=16、64 組 raw MAC、原層回填介面均維持相同。

## 三個可對照的 profile

| profile | BO | 打包 | 輸出處理 |
|---|---|---|---|
| `baseline` | 原正常 BO | 原逐字打包與 baby 重用 | 原合併後完整比對 |
| `burst` | 正常 BO | 32 KiB 區塊＋ARM64 NEON＋連續複製 | 合併與完整比對一起做 |
| `cacheable` | 可快取 BO | ARM64 NEON 直接寫入可快取映射 | 合併與完整比對一起做 |

`baseline_source/` 保留原始來源位元組。`cacheable` 保留原本同一視窗的 BO baby 重用，重用時只更新兩個 weight 欄位；`burst` 為了連續寫入會重寫完整交錯資料，可能增加部分寫入量。是否更快須實測。不存在靜默退回其他 BO profile 的機制，配置失敗會留下 FAIL；請回傳紀錄。

## 傳到遠端與板子

將本資料夾 `v32_ga3_hostopt_20261108` 放入你原本的 Git，push 後，遠端 Windows `git pull origin main`。再把這個新資料夾 SFTP 到：

`/root/114C75007/vek280/AIE/v32_ga3_hostopt_20261108`

既有 `/root/114C75007/vek280/AIE/v32_ga3_20261104_data` 原封不動保留。新套件預設讀該資料夾，不讀已刪除的 h_s.4 舊檔，也不需要傳輸分片或重新解壓縮。

## 先做短版篩選

每行分開執行，全部在板子 Linux：

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_hostopt_20261108
sh check_package.sh
sh build_board.sh
python3 ga3_board.py detect
sh run_screen.sh
python3 collect_results.py
```

`check_package.sh` 永遠核對本套件程式與硬體 SHA256。如果既有 g_a.3 的完整資料校驗收據仍在，且全部 5378 個檔案的裝置、inode、大小與奈秒時間戳完全相同，就延續既有完整 SHA256 檢查，明確列出 `REUSED_PRIOR_FULL_DATA_CHECK`。若不匹配會重新完整掃描；強制重算可用 `V32_GA3_FORCE_FULL_HASH=1 sh check_package.sh`。

編譯會產生 **三種 profile × 兩種後端**，不執行硬體。套件沿用既有 XRT managed kernel 的狀態暫存器檢查，編譯時可能顯示已存在的 deprecated 警告；有 error／FAIL 則保留完整輸出。

`run_screen.sh` 在目前開機映像上依序執行：

- 三個 profile 各一次 smoke，包含首尾與 L=5 邊界。
- `baseline → burst → cacheable → baseline` 的相同 16 視窗 probe。
- 每個 probe 視窗都含 CPU 前／硬體／CPU 後，各暖機 1 次＋正式 3 次。
- 16 視窗涵蓋四批 RNS、首尾 NTT 索引，以及輸出 0／15；**不能當完整 g_a.3 延遲或完整係數板上覆蓋**。
- 保留前後 baseline、CPU 漂移與完整時間線；不自動挑一筆最快值冒充正式結果。

下載最後列出的 `collected_ga3_hostopt_*.tar.gz` 給我分析，先決定哪個候選值得做完整測試，避免一開始就為每個候選各跑數小時。請一次只執行一個測試。

## 確認候選後的完整測試

下面以 `cacheable` 為例，實際 profile 應依短版結果決定：

```sh
sh run_round.sh cacheable
python3 collect_results.py
```

這會依序執行 smoke、全部 windows 降序、全部 windows 升序、完整 stream、完整 export。全部正式係數覆蓋仍為 1024 視窗、4096 作業、1,333,788,672 words。

單獨執行語法是 `sh run_board.sh MODE PROFILE ORDER`，例如：

```sh
sh run_board.sh probe burst ascending
sh run_board.sh stream cacheable descending
sh run_board.sh export cacheable descending
```

profile 是新參數，請不要套用舊套件的 `run_board.sh windows descending` 語法。

## 雙 AIE 與純 PL 的比較

目前是 `v32_core_2_pipe` 或 `v32_native_pl_2_pipe`，都可直接先測這個主機新版，不必為了主機程式重開機。純 PL 的主機成本較明顯，可優先測該映像。

若後續要切換映像，仍需你明確依序執行 `sh switch_board.sh VARIANT check`、`sh switch_board.sh VARIANT arm`，檢查成功後自行 `sync && reboot`。本輪工具不會自行切換。完整架構結論仍需要相同 profile、相同輸入／順序及 AIE→PL→AIE 回測。

## 計時與尚未完成的項目

- `resident_window_median_sum_hardware_ms` 包含打包、同步、硬體啟動等待、標準輸出合併及全數比對。暖機排除，每視窗三次取中位數再加總。
- `campaign_wall_ms` 是實際測試牆鐘時間。windows 含 CPU 對照與重測；stream 是單次含 admission 的完整 raw MAC 重播。
- `admission_profile.json` 是載入子階段，不與可重疊的硬體工作 span 混加。
- export 另輪重算與雜湊／首尾實際輸出存檔，獨立保留；新硬體輸出仍待回傳後做原上下文解密與回填驗證。
- 本輪沒有更改 reader／reducer 協定或擴大硬體批次。跨視窗硬體批次、更多管線與完整即時 g_a.3 服務，需在本輪瓶頸結果出來後另做硬體版本。
- 原 v32、原 GPU 程式、金鑰與舊報告沒有改動，無新金鑰需要上傳。

官方依據：

- https://xilinx.github.io/XRT/2024.1/html/xrt_native_apis.html — edge 平台 cacheable BO 與同步。
- https://xilinx.github.io/XRT/master/html/xrt_native.main.html — `xrt::bo` flags、建構與 `sync()` API。

實際是否支援、結果是否正確及速度是否提升，以板上配置成功、完整輸出比對和正式量測為準。
