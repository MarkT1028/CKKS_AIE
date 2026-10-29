# 真實 v32：雙 AIE 核心優化比較

這輪候選尚未上板，不能先宣稱勝過 CPU。保持兩顆 AIE、相同真實輸入、相同雙核心 CPU、相同 mapped BO 雙緩衝主機流程。

## 修改內容

1. AIE 的七組精確對角和改成編譯時展開，移除原本每組的動態分支。保留 64-bit accumulator 與 uint32 輸出，包含超過 INT32_MAX 的值。
2. reducer 在收到最後一組對角和時，立即向模數約減管線送出重建結果，省去另外掃描輸出的階段。modulus/reciprocal、累加及輸出格式維持一致。
3. 板測同時提供原映像和候選映像。兩者都使用上一輪最佳 `map_pingpong`，CPU 程式不變，每次硬體前後各跑 CPU 作對照。

## 上傳

只上傳本套件 `v32_coreopt_20261029`，放在原本 `v32_hs4_20261027` 旁邊。沿用原套件約 938 MiB 的輸入與預期資料，不需再上傳。不需要任何私鑰。

在板子執行：

```sh
cd /root/114C75007/vek280/AIE/v32_coreopt_20261029
sh check_package.sh
sh build_board.sh
python3 board_runner.py detect
```

## 先測原映像

若 detect 是 `v32_diag_2_pipe`，直接跑：

```sh
sh run_board.sh smoke v32_diag_2_pipe
sh run_board.sh formal v32_diag_2_pipe
sh run_board.sh formal v32_diag_2_pipe
```

若不是，先用下面相同的切換步驟，目標改成 `v32_diag_2_pipe`。

## 切換候選

```sh
sh switch_fair_board.sh v32_core_2_pipe check
sh switch_fair_board.sh v32_core_2_pipe arm
```

確認成功出現 `ARMED_ONLY` 後，再親自執行：

```sh
sync && reboot
```

切換流程會檢查既有開機檔案，備份並替換 slot 1，保留 BOOT.BIN、Image、boot.scr、slot 2。`check` 不寫檔；`arm` 不會立即重啟。重啟前取消請用 `sh prepare_variant_srst.sh --cancel`。

重啟後如需恢復 IP，在序列埠終端機執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

回到套件資料夾，確認 detect 是 `v32_core_2_pipe`：

```sh
python3 board_runner.py detect
sh run_board.sh smoke v32_core_2_pipe
sh run_board.sh formal v32_core_2_pipe
sh run_board.sh formal v32_core_2_pipe
```

每個指令完成並 PASS 後才跑下一個。smoke 有 1 次硬體與各 1 次 CPU；formal 每次有 1 次暖機、5 次硬體、前後各 3 次 CPU。每次另存完整 16 區塊輸出，供回傳後解密與平方續算驗證，存檔時間另列。

## 回測與收集

建議再切回 `v32_diag_2_pipe`，以相同 formal 指令跑兩輪，形成原版→候選→原版，檢查跨重啟和時間漂移。切換方法和上面相同，只改目標名稱。

```sh
python3 summarize_campaign.py
python3 collect_results.py
```

下載最後印出的 `collected_core_*.tar.gz` 一個檔案即可，收集有進度顯示。發生錯誤也保留並回傳結果，不刪除不利樣本。

## 如何判定成功

主要指標是全部 16 區塊、包含準備／同步／合併／逐字檢查的實際常駐 replay wall。一次性載入、XRT 初始化及另一次輸出存檔 replay 分開列出。CPU 使用同一份常駐輸入及相同兩顆 ARM CPU。

摘要會同時判斷硬體完整 replay 是否小於「前後兩次 CPU 完整 replay」及更嚴格的「前後兩次 CPU 純計算」。CPU 漂移超過 5% 時保留數據並標示待檢查。AIE 模擬週期、HLS 週期與板上時間必須分開解讀。本實驗只驗證一組真實 h_s.4 密文乘加，不能據此宣稱完整 v32 推論已加速。
