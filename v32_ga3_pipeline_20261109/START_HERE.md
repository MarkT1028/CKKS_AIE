# g_a.3：主機讀取流水線與新純 PL 核心候選

本套件準備六種主機設定，並增加一個純 PL 硬體候選。**板上速度待測，尚不能宣稱超越 CUDA。** 保留已測的雙 AIE、原 native PL 與完整輸出 SHA256 驗證，不改原始 v32、CKKS 參數或測資。

## 這次修改

1. 逐檔重新比對原本相同的五個身份欄位。利用固定目錄描述符減少重複路徑查詢，執行前後都檢查。
2. 預讀下一個 baby 視窗，與當前 CPU／FPGA 處理重疊；最多一個預讀視窗和一份暫存緩衝，運算中的資料保持獨立。
3. 測試 1、4、16 MiB 分塊讀取，保留不預讀對照。預讀可能爭用 ARM 核心或儲存頻寬，是否採用由總時間決定。
4. 新 `v32_native_lazy8_2_pipe` 純 PL：每拍 4 個完整乘積改成 8 個；先做精確 128-bit 累加再模數約減。K=16 時每係數由 64 次約減改成 3 次。外部輸入、kernel 引數、兩條管線與 PL 225 MHz 相同，兩端內部串流一併重建為 960-bit。

每次仍須完整 canonical 輸出 SHA256 相同。新硬體還需板上輸出及原上下文續算確認。原前版 C++ 放在 frozen_compactio，baseline 使用其原演算法；新映像的 baseline 僅覆寫匹配的 UUID／版本巨集。

## 上傳內容

只傳 `v32_ga3_pipeline_20261109` 程式資料夾，不必重傳 43 GiB 測資、快取或 Git 分片。保留板上 `v32_ga3_20261104_data`，重用既有 `v32_ga3_compact_cache_pilot`。

## 第一階段：目前雙 AIE 上測六種主機設定

每行分開執行：

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_pipeline_20261109
sh check_package.sh
sh build_board.sh
python3 ga3_board.py detect
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
python3 compact_cache.py check
sh run_screen.sh descending
sh run_screen.sh ascending
python3 collect_results.py
```

目前雙 AIE UUID 應為 `050ea5cc23fb5038bad0aca23cbd240b`。此階段不用換映像、重開機或重建快取。若快取尚未存在，先跑 `python3 compact_cache.py prepare pilot`；準備成本另外記錄。

check_package 可重用先前完整 SHA256 收據，但每次重新比對全部檔案身份。身份變動時重新完整核對，不能跳過失敗。完整核對數十 GiB 仍會耗時。

|設定|身份檢查|讀取塊|下一視窗預讀|
|---|---|---:|---|
|baseline|前版 pathlib|4 MiB|關|
|guard|固定目錄描述符、重新 stat|4 MiB|關|
|read1|同 guard|1 MiB|關|
|read16|同 guard|16 MiB|關|
|prefetch|同 guard|4 MiB|開|
|combined|同 guard|16 MiB|開|

run_screen 先做 baseline／combined smoke，再跑 baseline → guard → read1 → read16 → prefetch → combined → baseline 的 16 視窗短測。升序重跑同組設定，記錄快取與順序差異。結果在 pipeline_screen_summary.json，以同開機、同映像、同順序、同快取的前後 baseline 比較。

短測不是整層延遲；不預設 combined 最快。先回傳收集檔，依 runner_wall_ms、預讀等待、CPU 漂移與記憶體選正式設定。

## 第二階段：比較三個硬體映像

使用第一階段實測較好的主機設定，對雙 AIE、原 native PL、新 lazy8 PL 做相同工作量比較。先短測，再完整 stream。check 與 arm 分開執行，成功顯示 ARMED_ONLY 後才自行重開機：

```sh
sh switch_board.sh v32_native_lazy8_2_pipe check
sh switch_board.sh v32_native_lazy8_2_pipe arm
sync && reboot
```

重開機後回到本資料夾，重新 detect；新 UUID 見 variants/v32_native_lazy8_2_pipe/EXPECTED_BOOT_UUID。若 IP 消失，在序列終端機執行 `ip addr replace 192.168.10.98/24 dev end0`，再 `ip link set end0 up`。

先以 combined 為例：

```sh
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
sh run_board.sh smoke combined descending
sh run_board.sh probe guard descending
sh run_board.sh probe guard ascending
python3 collect_results.py
```

probe 每視窗 3 次正式、1 次暖機，含前後 CPU 對照，仍只涵蓋 16 視窗。CPU 常駐比較使用 guard，避免預讀執行緒干擾 CPU 對照；預讀的總請求收益另用 pilot／stream 比較。若刻意在 CPU 對照中開啟預讀，摘要會標記 review_required。

用相同 switch 流程可回到 v32_native_pl_2_pipe 或 v32_core_2_pipe。映像切換先備份 slot1，保留 stock BOOT.BIN、slot2、Image、boot.scr。程式不會自動重開機。

若中斷或硬體錯誤，保留失敗結果；RECOVERY_REQUIRED 會阻止同次開機再執行，重開機並 detect 後再試。不要同時跑兩個硬體實驗。

## 第三階段：完整 raw MAC 與輸出回填

完整 packed 快取約 23.81 GiB，加保留空間需約 26 GiB 可用。準備時間另外計入首次使用成本；已有完整快取可直接 check，不必重建。

```sh
python3 compact_cache.py plan full
python3 compact_cache.py prepare full
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_full
python3 compact_cache.py check
sh run_board.sh stream baseline descending
sh run_board.sh stream combined descending
sh run_board.sh stream baseline descending
python3 summarize_pipeline.py
sh run_board.sh export combined descending
python3 collect_results.py
```

請將 combined 換成短測勝出的設定。其他映像使用同一快取、設定與順序做 A／B／A 比較。完整 stream 涵蓋 1024 視窗、64 組 raw MAC、N=131072、L=53、K=16，全部輸出驗證。pilot 快取也能跑完整工作量，但未快取輸入仍讀原始資料，不能和完整快取結果混比。

export 是另一次完整重算與輸出見證，不能混成純核心延遲。每個輸出保留 SHA256，預設下載首尾實際樣本，其餘依與 sealed reference 相同的雜湊重建原上下文驗證；不能宣稱全部輸出實體檔都已下載。回傳 collect_results 指定檔案後，再做原上下文驗證。

## 時間定義與 CUDA 目標

- runner_wall_ms 是主指標：控制器檢查、setup、讀取／解碼、pack、sync、run/wait、全部輸出驗證及結果記錄。Python 啟動和一次性快取準備另外列出。
- campaign_wall_ms 是主程式請求；stream 含資料載入，windows/probe 還含 CPU 對照與重複測試。
- admission_ms 是主執行緒載入與等待。啟用預讀後，部分讀取已在其他工作期間完成，不能代表全部讀取工作。
- prefetch_work_ms、pread_ms 是可能重疊的工作量時間，不能相加當總時間或硬體 cycles。
- resident_window_median_sum 是各視窗常駐時間加總，不能標成完整層延遲。

上一版 packed pilot 含控制器約 52.49 秒，約 75% 為讀檔工作，另約 19% 在主程式外。本輪優先檢查這兩部分。

歷史 CUDA g_a.3=25.6566秒 是 Phantom 原層，與此處 OpenFHE raw MAC 的參數、操作及載入狀態不同。不能用 pilot、常駐加總或本機模型時間宣稱超過 CUDA。本機沒有可用 NVIDIA GPU，無法重跑匹配的 CUDA 基準。

完整 packed 輸入約 23.81 GiB；以先前板上約 23 MiB/s 讀取，僅輸入就需約千秒。預讀能重疊等待，無法消除必須讀取的資料量。含載入的總時間若要達到約 26 秒，還需要更快資料來源或縮減真正必須傳入的資料。依歷史吞吐估算的限制見 CUDA_TARGET_ASSESSMENT.json，這是條件估算，並非新板上結果。

旋轉、im2col、relinearization、activation、即時 v32 傳輸仍在原後端。本套件衡量 declared raw MAC，沒有聲稱完成整個即時 g_a.3 或全模型。
