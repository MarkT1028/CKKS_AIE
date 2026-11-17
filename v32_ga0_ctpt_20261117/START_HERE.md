# VEK280 `g_a.0` 純 PL 密文乘明文專用版

兩條 PL 管線，0 顆 AIE。明文 BO 只傳需要的分量，PL 只回傳兩個密文分量。主機在算 SHA-256 時補回第三個全零分量，沿用原始 15,360 塊的參考雜湊。

全量規格為 `N=131072`、`L=57`、`K=16`，16 個輸出各有 4 組乘加。重用板上 `v32_ga0_full_20261114/fixture`，套件包含程式與獨立 PL 啟動映像。原 `v32_ga_opt_20261117`、`v32_ga_resident_20261114`、`v32_ga_live_20261111`、`v32_ga3_finishopt_20261110` 和 `v32_ga3_splitbo_20261109` 應與這次套件放在同一層。

| 完整 `g_a.0` 的 BO 資料量 | Split BO | 專用版 |
| --- | ---: | ---: |
| 輸入同步 | 121.125 GiB | 64.125 GiB |
| 輸出回讀 | 10.6875 GiB | 7.125 GiB |

資料量按同步要求的位元組計算。`OFFLINE_VERIFICATION.json` 和 `RESOURCE_COMPARISON.json` 記錄離線驗證與配置繞線數據。

## 板上先建置與短測

把整個 `v32_ga0_ctpt_20261117` 傳到板上 AIE 目錄。先在 VEK280 終端執行以下命令。

```sh
cd /root/114C75007/vek280/AIE/v32_ga0_ctpt_20261117
sh build_board.sh
python3 -B switch_board.py ctpt check
```

看到 `BUILD_READY_GA0_CTPT_COMPACT` 和 `CHECK_ONLY` 後，準備啟動槽 1。若這次要做正式 A/B/A，先在目前的 Split BO 開機完成第一輪 `fast` 全量基準，指令見下方。

```sh
python3 -B switch_board.py ctpt arm
```

看到 `ARMED_ONLY` 後，保留序列埠連線並在板上執行 `sync && reboot`。重新登入後確認 `matching` 為 `true`，再進行短測。

```sh
cd /root/114C75007/vek280/AIE/v32_ga0_ctpt_20261117
python3 -B run_board.py detect
python3 -B run_board.py smoke
```

## 全量與基準回測

短測通過後執行 `python3 -B run_board.py full`。全量應顯示 `PASS_GA0_CTPT_FULL`、15,360 塊、1,434,451,968 個輸出字。即時輸出會給出 `RESULTS=`。以下範例的路徑請換成實際那一輪的結果資料夾。

```sh
python3 -B run_board.py collect --result /root/114C75007/vek280/AIE/v32_ga0_ctpt_20261117/results_ga0_full_ctpt_compact_時間戳
```

同一塊板的比較順序為 Split BO `fast` → 專用版 → Split BO `fast`。在切換前後的兩輪 Split BO 開機，於 `v32_ga_opt_20261117` 執行 `python3 -B run_board.py run ga0 full fast`。從專用版切回 Split BO 可在專用版目錄執行 `python3 -B switch_board.py splitbo check` 和 `python3 -B switch_board.py splitbo arm`，看到 `ARMED_ONLY` 後再執行 `sync && reboot`。

- 用 `packing_and_resident_seconds` 與上次 `fast` 的 65.75 秒比較。這個口徑涵蓋打包、BO 同步、PL 運算、輸出回讀與驗證，排除檔案讀取及 ARM NTT。
- 另記錄 `request_seconds`、`read_seconds` 與 `ntt_ms`。這三個欄位可用來評估整次重播及還有多少時間花在資料準備。
- 完整範圍指 `g_a.0` 的 64 組 raw MAC。層內後續聚合與 bias 由原驗證端處理。
