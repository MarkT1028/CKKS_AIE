# 下一輪：雙 AIE 的 16 部分積與 7 對角和比較

本包只比較兩顆AIE、兩條完整流水線：

- `raw_2_pipe`：目前已驗證版本，每乘積輸出16個32-bit部分積。
- `diag_2_pipe`：既有離線候選，每乘積輸出7個**無號32-bit**對角和，PL使用匹配的重建／約減／累加流水線。

**候選尚未實際上板驗證，不預填任何效能結果。** 沿用先前已建置且有離線簽核的映像，本次沒有重新執行FPGA建置。候選只是改變中間表示，最終仍須逐word等於相同golden。

## 1. 上傳完整資料夾、檢查與編譯

```sh
cd /root/114C75007/vek280/AIE/compact_compare_20261024
sh check_package.sh
sh build_controlled_board.sh
python3 controlled_board.py detect
```

這些步驟不切換映像、不重開機。應先辨識為 `raw_2_pipe`。與fair_profile套件分開，不覆蓋舊資料。

## 2. 先跑當前版本 A1

```sh
sh run_controlled_board.sh raw_2_pipe 1 smoke_A forward
sh run_controlled_board.sh raw_2_pipe 30 A1 forward
```

每次仍24案例：CPU前10、硬體4、CPU後10；每案例3次暖機加1／30次正式樣本。CPU算法、fixture與綁核設定沿用前包。結果前綴為 `results_compact_`。

## 3. 準備候選切換 B1

先保留序列埠終端機，依序執行：

```sh
sh switch_controlled_board.sh diag_2_pipe check
sh switch_controlled_board.sh diag_2_pipe arm
```

只有兩步都成功，才另行執行：

```sh
sync && reboot
```

check只讀；arm沿用既有SHA、備份、stock BOOT.BIN／slot2／Image／boot.scr保護，設定一次性切換，不自動重開機。

## 4. 重新開機後先辨識，再短測候選

```sh
cd /root/114C75007/vek280/AIE/compact_compare_20261024
python3 controlled_board.py detect
```

必須顯示 `diag_2_pipe`，預期UUID為 `2b5c68811dc2575a91b0bb9d8f8e2f98`。匹配後：

```sh
sh run_controlled_board.sh diag_2_pipe 1 smoke_B forward
```

**短測出現FAIL就停止，下載整個結果資料夾。** 全部通過才做：

```sh
sh run_controlled_board.sh diag_2_pipe 30 B1 forward
```

可先回傳A1、B1、短測資料夾、bin、switch_logs，確認候選正確性與初步改善。

## 5. 完整研究比較：回測 A2，再測 B2

先依第3步把版本改回 `raw_2_pipe`，arm後另行重開機。detect匹配後：

```sh
sh run_controlled_board.sh raw_2_pipe 30 A2 reverse
```

再依相同步驟切至 `diag_2_pipe`，重開機、detect匹配後：

```sh
sh run_controlled_board.sh diag_2_pipe 30 B2 reverse
```

這樣每種格式各有兩個不同boot，並且包含正反案例順序。只在同一個boot改session名稱不算跨開機。

## 6. 結果與彙整

完整回傳所有 `results_compact_...`、板上 `bin` 及 `switch_logs`，包括失敗資料。可壓成7z。

```sh
python3 summarize_controlled.py results_compact_*
```

彙整JSON的 `hardware_format_comparisons` 直接列raw／diagonal主流程及完整交易速度比。CPU前後值分開，漂移未解決時不將pooled值寫成穩定CPU基準。分段與總時間不可重複相加。

本包沒有針對diagonal候選準備新的profiling配置；先確認全輸出正確與速度，再按其實際mapping量測。先前raw_2_pipe的profiling數據不當作候選的量測值。

重新開機後若需恢復原網段：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

## 為何選這個候選

10/24診斷核對每條raw管線K16輸出48MiB，兩路合計96MiB；diagonal改為每路21MiB、合計42MiB，中間資料量少56.25%。依128-bit、225MHz建置設定，純資料傳輸理想下限每路由13.981ms降至6.117ms。這是資料量與時脈推導，**不是候選板上時間或保證加速倍數**。

仍要量測AIE加總成本、reducer、主機開銷與精度。候選沒有用近似值或丟棄低位元，最大對角和4×32767²＝4,294,705,156，超過signed int32，因此必須保留uint32處理。
