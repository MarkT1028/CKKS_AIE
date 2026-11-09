# g_a.3：分離 A/B 輸入 BO，先短測比較

這次改的是 FPGA 的輸入介面與板端資料準備。沿用原始完整 g_a.3 資料與既有無損壓縮 cache，不需再次傳送 43 GiB 測資。目標是減少 ARM 交錯排列與重複 BO 同步，實際效能仍待板測。

## 改了什麼

- 原本 ARM 將 A0、A1、B0、B1 排成每條管線的交錯輸入；新版直接複製原標準排列到分開的 A/B BO，由 reader 自己取對應係數。
- 四組權重各保留一個唯讀 BO；相同權重在不同輸出密文之間可重用。
- 每個視窗的 baby/input B 只上傳一次，四組 MAC 與兩條管線共用；兩條管線分別處理不同半部係數。
- 沿用 lazy8 精確寬累加與最後模數約減；密碼參數、數值精度及完整 canonical SHA256 驗證不變。
- 初次複製、sync 都在硬體路徑計時內。暖機與正式樣本都保留上傳 bytes，不能把暖機後無複製的 resident 當成第一次使用的總時間。
- 原本 CPU 已有的 weight vector 重用並不是這次新增的優化；這次新增的是裝置 BO 層級重用。原始檔案讀取量並未因此變成零。

## 先做這些，不要先跑一小時的完整測試

從遠端電腦把整個 `v32_ga3_splitbo_20261109` 資料夾放到板子原本 AIE 目錄，與舊套件並列。

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_splitbo_20261109
sh check_package.sh
sh build_board.sh
python3 ga3_board.py detect
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
python3 compact_cache.py check
```

check 會在原資料檔案身分完全相同時，重用既有完整 SHA256 檢查收據；每次執行仍做新鮮的前後身分快照。實際 BO 分配必須成功，失敗會停止，不會清除系統快取或修改 CMA 設定。

## A：先在目前的 lazy8 映像做基準

若 detect 顯示 `v32_native_lazy8_2_pipe`，直接執行：

```sh
sh run_short.sh
```

這會做 smoke，再做 descending／ascending 各一次 16 視窗 pilot。含初次上傳、資料 admission、完整輸出驗證；不是完整 1024 視窗。pilot 沒有 CPU 前後對照，適合先比較相同含載入請求是否值得繼續。

如果目前是其他映像，先貼回 detect 輸出，或使用既有手動 check／arm 流程切到 lazy8；不要使用不匹配映像的 host。

## B：切換新分離輸入映像

```sh
sh switch_board.sh v32_native_splitbo_2_pipe check
sh switch_board.sh v32_native_splitbo_2_pipe arm
```

確認最後是 `ARMED_ONLY` 且前面沒有 FAIL，才執行：

```sh
sync && reboot
```

這次 reader 的外部介面有變，必須使用新映像與新 host。原 BOOT.BIN、第二啟動槽與 rollback 檢查沿用原流程。

重開後：

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_splitbo_20261109
python3 ga3_board.py detect
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
sh run_short.sh
python3 summarize_split.py
python3 collect_results.py
```

detect 必須顯示 `v32_native_splitbo_2_pipe`。下載 collect 指定的 `collected_ga3_splitbo_*.tar.gz`，先檢查短測再決定長測。舊 lazy8、舊 native PL 與雙 AIE 映像均保留，可以用同一套件比較與回復。

## 若短測有改善，再增加這兩項

```sh
sh run_board.sh pilot refresh descending
sh run_probe.sh
python3 summarize_split.py
python3 collect_results.py
```

- refresh：相同新硬體，每個硬體 trial 都重新上傳 4 組權重與 1 組 baby，用來分辨「介面不必交錯排列」與「BO 重用」各自的影響。
- probe：每視窗 1 次暖機、3 次正式，含 CPU before／after，兩個順序。要比較舊映像的 probe，必須在舊映像也跑相同 run_probe.sh；不要混比 pilot 與 probe。
- 正式結論仍需 A→B→A 跨開機回測，及最後完整 1024 視窗與 export／原上下文驗證。初期先不跑這些長測。

## 要看哪些數字

- `runner_wall_ms`：控制器、setup、檔案 admission、全部測試與驗證的總時間。
- `campaign_wall_ms`：主程式請求時間，probe 也包含 CPU 與重複試驗。
- `resident_window_median_sum_hardware_ms`：每視窗正式樣本中位數再加總；排除 admission，包含當次需要的 BO 準備與完整驗證，非純 kernel cycles。
- `split_input_cache.first_trial_window_wall_sum_ms`：每視窗第一次硬體 trial 的 wall 加總，保留該視窗的新 baby／變更權重上傳。
- samples.csv 的 `device_input_copied_bytes`、`device_input_synced_bytes`、`device_input_cache_hits`：每次 trial 的實際 BO 準備帳務。
- `warmup_copied_bytes` 與 `formal_copied_bytes` 必須一起看。不能只用上傳已在暖機完成的正式 resident 來宣稱 first-use 加速。

本輪仍是 g_a.3 raw MAC 比較，不等於包含 rotation、im2col、relinearization、activation 的 live 整層延遲，也沒有建立同工作量的 CUDA 加速結論。

## 遠端 Windows CMD 的 Git

只需推新的程式／硬體套件，原始測資與 cache 不在這包中重複傳送。Git 指令見交付時的對話。遠端 Windows `git pull origin main` 後，把這個新資料夾複製到板子即可。

若重開板子後要恢復原網路位址：

```sh
ip addr replace 192.168.10.98/24 dev end0
ip link set end0 up
```
