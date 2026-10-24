# CPU 綁核比較與雙 AIE 流水線 profiling

整個 `fair_profile_20261024` 資料夾上傳到板子。沿用四個已驗證映像，沒有新 FPGA bitstream，與舊套件分開保存。

## 1. 檢查、編譯、辨識目前版本

```sh
cd /root/114C75007/vek280/AIE/fair_profile_20261024
sh check_package.sh
sh build_controlled_board.sh
python3 controlled_board.py detect
```

確認 `matching_variants`。以下假設目前是 `raw_2_pipe`；若不同，先貼回輸出或依 README 切換。BOOT 不匹配時程式停止。

## 2. CPU／硬體短測與正式比較

```sh
sh run_controlled_board.sh raw_2_pipe 1 smoke forward
sh run_controlled_board.sh raw_2_pipe 30 round1 forward
```

1／30是每案例正式樣本數，另有3次暖機。每命令24案例：CPU前10、硬體4、CPU後10。CPU比較未綁核1／2執行緒、單執行緒固定第一／第二核心、雙worker各固定一核心。前後案例順序相反；每輪完整核對，不刪慢樣本。結果為 `results_controlled_...`。

## 3. 雙路 profiling

先完成正式比較，再跑診斷。只有 `raw_2_pipe` 可執行：

```sh
sh run_profile_board.sh heat_map 20 smoke
sh run_profile_board.sh all 200 profile1
```

all依序收 baseline、heat_map、stalls、execution、輸入DMA channel0、輸入channel1、輸出channel0、baseline_after，共8組，各3暖機加200輪。輸出channel1未被使用，只保留可選的 `dma_out1` 控制組，不列入all。

結果為 `results_profile_...`。若 `ANSWERS_PASS_COVERAGE_PARTIAL`，表示答案正確但部分計數器未確認，仍請回傳完整資料。host失敗會停止並保存部分結果，不自動重試或重置。

## 4. 補齊四架構與第二次開機

round1建議依 `raw_2_pipe → raw_2_full → raw_1_pipe → baseline_1`；round2反向，測試參數改用 `30 round2 reverse`。**同一版本的round2也要在另一個boot執行**；換session名稱不算跨開機。

每次切換範例（保留序列埠）：

```sh
sh switch_controlled_board.sh raw_2_full check
sh switch_controlled_board.sh raw_2_full arm
```

成功後，另行執行：

```sh
sync && reboot
```

重開機後回本資料夾，先detect，再用目前版本名稱跑短測／正式測試。腳本不自動重開機。同一映像要換boot，也要先對該版本重新arm，再reboot。

## 5. 回傳資料

完整下載所有 `results_controlled_...`、`results_profile_...`、`switch_logs` 和板上 `bin`，可一起壓7z。保留CSV、JSON、xrt.run_summary、host.log、build及ldd紀錄，不要只給summary。bin不用git add。

網路恢復（沿用你的原設定）：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

計時定義、彙整與診斷限制見 `README_測試說明.md`。
