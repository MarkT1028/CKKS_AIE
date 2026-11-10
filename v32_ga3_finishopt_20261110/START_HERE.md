# g_a.3 輸出驗證與雙視窗優化：上板比較套件

本套件是 `v32_ga3_splitbo_20261109` 的小型主機程式增補。沿用目前純 PL 的兩條管線與 225 MHz 映像；AIE 為 0 顆。**新版速度尚待上板，不能把本機軟體模型時間當成 FPGA 成績。**

## 這次調整

1. **直接分段驗證輸出**：兩條 PL 管線各自輸出一半係數。按照原本的「每個 RNS 模數：左半、右半」順序，直接從輸出 BO 計算完整 canonical SHA256，省去先合併成另一份向量的複製。標頭與每一個輸出位元組都仍參與驗證，預期摘要不變。
2. **兩個視窗接續處理**：同一個 RNS／係數區塊內，兩個視窗共用四份唯讀權重，使用各自的 baby 輸入 BO。將原來每次 4 組工作接成 8 組，使前一視窗最後輸出的取回／驗證，可以與下一視窗的準備／執行重疊。每次只有一組雙路 kernel invocation 活躍；每個輸出 bank 驗證完成前不得重用。

不增加 PL 管線、不修改模數或密文數、不省略首次上傳、不省略完整 SHA256，不清除全域快取。原始資料和既有快取保留。

## 需要哪些既有檔案

這四個資料夾放在同一層：

```text
AIE/
  v32_ga3_splitbo_20261109/          # 必須保留的父套件（約30MB）
  v32_ga3_finishopt_20261110/        # 本次新增套件
  v32_ga3_20261104_data/            # 已解壓的原始完整測資，不用重傳
  v32_ga3_compact_cache_pilot/      # 已建立的48份輸入快取，不用重建
```

父套件 manifest SHA256 固定為 `9046e08779347d8b766f5341264ca71fa24914b0a50fb2cd988f59661b0fa2a7`。父套件不得自行修改或重新產生 manifest。若改了路徑，可設 `V32_GA3_SPLITBO_BASE`、`V32_GA3_DATA`、`V32_GA3_CACHE`，但內容必須一致。來源身分與既有完整雜湊收據仍會檢查；資料變更或缺失會停止。

## 第一步：檢查與編譯

在板子的 Linux 終端機逐行執行：

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_finishopt_20261110
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
sh check_package.sh
sh build_board.sh
python3 finish_board.py detect
```

編譯包含完整 SHA 的本機自我測試與測資 metadata 檢查，不啟動 PL。detect 應顯示 `v32_native_splitbo_2_pipe`，UUID：`9bee253b8f345f39bd9c18d612897ce3`。若已是此映像，不用重新開機。若不同，先用父套件既有切換流程切到此映像，再回來 detect；本套件本身不寫入開機檔案。

BO 最大估計約 **198.02 MiB**（207634432 bytes，含頁面取整、不含驅動額外成本）。比父版多一份32MiB baby BO；資料與記憶體皆有上限。控制器保留可用 RAM 和 CMA 總容量檢查，但不把瞬間的低 CmaFree 當成配置失敗；實際 XRT 配置仍必須全部成功才會執行。

## 第二步：先跑短比較

```sh
sh run_screen.sh
python3 collect_results.py
```

`run_screen.sh` 依序執行：

| 步驟 | 設定 | 範圍／目的 |
|---|---|---|
| 1 | direct2 smoke | 首末各一個視窗，先確認基本正確性；此步本身不覆蓋雙視窗交接 |
| 2 | merge1 pilot | 16個視窗，原本先合併再驗證的控制組 |
| 3 | direct1 pilot | 相同16個視窗，僅改為直接分段 SHA |
| 4 | direct2 pilot | 相同16個視窗，再加入雙視窗接續 |
| 5 | merge1 pilot | 重跑控制組，觀察時間漂移 |

pilot 覆蓋四段 RNS（16／16／16／5）、首末係數視窗和第0／15個輸出密文，**共16個視窗，不是完整1024個視窗**。三種設定同映像、同測資、同順序、同快取，且每個程序從空的 BO 身分快取開始，首次必要上傳都計時。可能花數分鐘，主要仍取決於板上讀取速度；它不會自動接著跑數小時的正式比較。

將 `collect_results.py` 顯示的 **collected_ga3_finishopt_*.tar.gz** 傳回來分析。如果直接驗證／雙視窗沒有收益或控制組漂移明顯，就先看 stage trace，避免直接投入完整長測。

單獨重跑語法：

```sh
sh run_board.sh direct2 pilot descending
```

每次產生新結果資料夾，不覆寫舊結果。不要同時執行兩個硬體實驗。

## 確認有收益後：完整工作量與輸出驗證

```sh
sh run_board.sh merge1 full descending
sh run_board.sh direct2 full descending
sh run_board.sh merge1 full descending
sh run_board.sh direct2 export descending
python3 collect_results.py
```

這是選擇性的第二階段，短比較後再決定。每個 full／export 都覆蓋 **1024個視窗、全部53個 RNS 模數、全部係數、16個輸出密文的64組 MAC、1333788672個輸出 words、4096份完整 SHA256**。每個程序0次暖機、1次完整經過；控制組重跑提供相鄰參考，不能直接宣稱已取得多輪正式統計。

export 會另跑完整工作量，存下全部4096份摘要與首末視窗的8份實際完整輸出；其他輸出為摘要連結證據，**不等於下載了所有輸出位元組**。取回後仍需獨立摘要／原上下文回填驗證。若要保存所有實際輸出，可設定 `V32_GA3_EXPORT_ALL=1`，需至少12GiB可用空間；預設不啟用。export 包含另存的成本，不能當成不另存的 full 時間。

## 時間如何比較

- **`resident_batch_wall_sum_ms` 是本輪主指標**：從視窗 begin／batch configure，到首次必要的 BO 複製與同步、參數、輸出 poison、kernel 啟動等待、輸出同步及完整 SHA 驗證結束的各批實際 wall time 總和。雙視窗重疊時不虛構各自獨立的視窗延遲，也不把重疊 stage 相加當成 wall time。
- `admission_ms` 是 SD／檔案載入、必要的無損解碼與範圍檢查，獨立保留，不放進上述主指標。`setup_ms`、`request_wall_ms`、`runner_wall_ms` 也保留。
- 歷史的 **92.805956秒** 與最新父版 **36.033516秒** 都排除 SD 檔案載入；92.8秒是舊版逐視窗多輪中位數總和，36.03秒是較新單次完整 stream。新 merge1 是本框架控制組，並非把歷史36.03秒重新命名，板上數值可能不同。
- 完整 raw MAC 覆蓋，不代表完成 live `g_a.3` 整層。rotation、im2col、relinearization、activation 和原模型傳輸仍在原後端。也不能與使用者提到的 CUDA 26秒直接當成同計時範圍比較。

`windows.csv` 保存每個視窗四份完整輸出摘要與 BO 位元組統計；`batches.csv` 保存實際批次 wall；`traces.csv` 記錄每個 task 的 bank／slot、執行與驗證區段。控制器會重算覆蓋率、摘要、必要上傳和驗證 stage，拒絕軟體模型結果冒充板上證據。

若執行中斷或硬體驗證失敗，會保留結果並要求重新開機後才可再啟動硬體；不要刪除 recovery 記錄來繞過檢查。
