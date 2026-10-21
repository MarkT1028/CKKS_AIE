# 單 AIE＋流水線 reducer：上板測試

本包補齊研究矩陣中的「單 AIE＋流水線 reducer」。兩個版本都是一個 reader、一顆 AIE、一個 reducer，完整處理 N=8192、L=3、K=1／16；不把輸入縮成雙路版的一半。

| 版本 | AIE | reducer | 用途 |
| --- | ---: | --- | --- |
| raw_1_pipe | 1 | 重建／取模／累加三階段 DATAFLOW | 本輪候選，尚未板測 |
| baseline_1 | 1 | 原版 | 原單路對照，可重新上板測量 |

硬體映像沿用已完成 link／route／離線驗證的候選；本輪整理測試包與入口，沒有重新建置硬體。兩版共用的 C++ 運算、計時、輸出驗證來源，與先前雙路測試相同。本包不執行 CPU benchmark，也不預填候選效能。

## 1. 上傳哪個資料夾

將整個 single_pipe_test_20261021 上傳到：

```text
/root/114C75007/vek280/AIE/single_pipe_test_20261021
```

也可上傳 tar.gz 到 AIE 目錄，再執行 tar -xzf single_pipe_test_20261021.tar.gz。保留 fixtures、variants、reference_results_20261019 等全部內容；不用覆蓋舊測試包。

## 2. 檢查、編譯與切換前確認

在 VEK280 Linux 終端機逐行執行：

```sh
cd /root/114C75007/vek280/AIE/single_pipe_test_20261021
sh check_package.sh
sh build_single_pipe_board.sh
sh switch_single_pipe_board.sh raw_1_pipe check
```

依序確認 PACKAGE_READY、HOST_BUILD_READY、STAGING_PLAN、CHECK_ONLY。遇到 FAIL 先保留完整輸出，不進到下一步。編譯使用板上 g++／XRT；不需在板上安裝 Vitis。

## 3. 預約載入單路流水線硬體，然後重開機

保持 COM4 序列主控台與供電。執行：

```sh
sh switch_single_pipe_board.sh raw_1_pipe arm
```

這會驗證原開機檔、備份 slot 1、放入本候選，並預約下一次重開機使用它；本命令不直接重開機。看到 ARMED_ONLY 後，再另外執行：

```sh
sync && reboot
```

重開機是為了切換 PL／AIE 硬體。BOOT.BIN、slot 2、Image、boot.scr 保留原有檔案及雜湊檢查。若重開機前要取消預約：sh prepare_variant_srst.sh --cancel；取消不會自動將已 stage 的 slot 1 換回。

## 4. 重開機後先短測，再正式測試

```sh
cd /root/114C75007/vek280/AIE/single_pipe_test_20261021
sh run_single_pipe_board.sh 1
sh run_single_pipe_board.sh 30
```

先確認短測四組全部 PASS，再執行第二條。每次包含 K=1／16 × resident／transfer 四組，各先暖機 3 次；30 是「每組正式 30 次」。每輪仍完整核對 73,728 個輸出整數。

執行紀錄應出現 variant=raw_1_pipe、cores=1。若執行中的硬體 UUID 不符，腳本會在啟動 kernel 前拒絕執行。raw_1_pipe 的預期 UUID：e5e148622540515eb6d0e2c896c903ba。

如果重開機後要恢復先前使用的暫時 IP，可先從 COM4 查詢：

```sh
ip addr show end0
```

只有確認遠端現場仍採原本 192.168.10.0/24 網段、192.168.10.98 沒被其他設備占用時，再依原環境設定該地址；本包不修改網路設定。

## 5. 要下載哪些結果

短測與正式測試各產生一個新的 results_raw_1_pipe_none_隨機字尾 資料夾。把兩個資料夾完整下載並壓縮給分析者，保留全部子資料夾、summary.csv、iterations.csv、host.log、output_last.bin、session.txt、xrt.ini、硬體身份及環境紀錄。

LAST_RESULTS_raw_1_pipe.txt 記錄最近一次結果路徑。不要只下載 summary.csv 或截圖；兩個結果資料夾都要保留。

## 6. 建議補做同日原單路對照

本包已有原單路 baseline_1，方便在相近條件下比較，不只依賴 10/19 的歷史數字。先執行：

```sh
sh build_single_pipe_board.sh baseline_1
sh switch_single_pipe_board.sh baseline_1 check
sh switch_single_pipe_board.sh baseline_1 arm
```

看到 ARMED_ONLY，再另外執行 sync && reboot。登入並回到本包後：

```sh
sh run_single_pipe_board.sh 1 baseline_1
sh run_single_pipe_board.sh 30 baseline_1
```

再下載兩個 results_baseline_1_none_隨機字尾 資料夾。這四個結果資料夾可比較同日原單路與流水線單路；若要確認跨重開機穩定性，另做獨立 session，並交錯安排版本順序。

## 7. 比較工具（可在下載後執行）

以正式 30 次的資料夾為輸入；下列 XXXXXXXX 必須換成實際字尾。只指定候選時，預設使用本包 10/19 原單路正式結果，會明確標示為歷史比較：

```sh
python3 compare_single_pipe_results.py results_raw_1_pipe_none_XXXXXXXX --output comparison_single_pipe.csv
```

有本輪原單路正式結果時，使用 --reference：

```sh
python3 compare_single_pipe_results.py results_raw_1_pipe_none_XXXXXXXX --reference results_baseline_1_none_XXXXXXXX --output comparison_single_pipe_same_day.csv
```

工具核對四組完整測試、至少 30 次正式樣本、3 次暖機、profiling 關閉、相同測資／共同 host 來源／編譯器、單核心配置、硬體 UUID、保存輸出及重新計算的統計。短測不能拿來當正式效能結論；不覆蓋已存在的比較檔。

## 8. 這輪回答什麼

- 對 baseline_1：相同一顆 AIE，reducer 的整組流水線改造帶來多少效果。
- 對先前 raw_2_pipe：後續結合兩輪資料，觀察同樣流水線 reducer 下，單／雙完整管線的差異；跨日期比較仍另標。
- 原始 K16 partials 仍為 96 MiB；這不是七對角和格式，也沒有縮小 N／L／K。
- 資源歷史 routed 統計：baseline_1 LUT 12,753、DSP 55；raw_1_pipe LUT 17,618、DSP 167。兩者 BRAM 均 12.5 tiles。
- raw_1_pipe 既有 setup slack 0.825 ns、hold slack 0.008 ns、DRC errors 0；這些是離線報告，不是板測速度。
- metadata_verification.json 中 max_aie_cores=2 是原整組實驗的顆數上限；actual_core_tiles 只有 [17,0]，本版實際使用 1 顆。
- 這輪沒有新的 CPU、功耗或 OpenFHE 解密成績；候選效能需收到板測檔案後才分析。
