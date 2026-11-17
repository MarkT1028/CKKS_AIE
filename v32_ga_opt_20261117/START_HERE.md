# VEK280 的 g_a.0、g_a.3、g_a.6、g_a.9 主機優化板測

使用板上既有的 Split BO 純 PL 映像，UUID 為 `9bee253b8f345f39bd9c18d612897ce3`。把此資料夾放在既有 GA 套件旁。直接重用原封存測資、硬體映像與輸出參考。

## 建置與短測

在板子上執行以下命令。

```sh
cd /root/114C75007/vek280/AIE/v32_ga_opt_20261117
python3 -B run_board.py check
sh build_board.sh
python3 -B run_board.py run ga0 smoke fast
python3 -B run_board.py run ga3 smoke fast
python3 -B run_board.py run ga6 smoke fast
python3 -B run_board.py run ga9 smoke fast
```

`g_a.3` 沿用原 FinishOpt 的完整測資檢查收據和壓縮 pilot 快取。如果板子已將快取設在別處，照原套件設定 `V32_GA3_CACHE`。兩個 profile 使用同一份快取和映像。

若之後要評測另一個儲存裝置，可以加 `--data /掛載點/原封存測資`。g_a.3
的收據綁定路徑，改路徑後請先在舊 Split BO 套件以相同的 `V32_GA3_DATA`
執行 `sh check_package.sh`。同一組效能對照使用相同的路徑。

## 全量對照

短測通過後逐層執行。下列以 `ga0` 為例。將第一個參數換成 `ga3`、`ga6` 或 `ga9`，即可量測其他層。前後兩輪基準可用來檢查同次開機的漂移。

```sh
python3 -B run_board.py run ga0 full baseline
python3 -B run_board.py run ga0 full fast
python3 -B run_board.py run ga0 full baseline
```

每次成功都會顯示 `RESULTS=`。傳回 `summary.json`、逐塊紀錄與環境資訊，可直接打包。可在 `--result` 後放多個完整結果路徑。

```sh
python3 -B run_board.py collect --result /root/114C75007/vek280/AIE/v32_ga_opt_20261117/ga0/results_ga0_full_fast_時間戳
```

## 更改與計時

| 層 | fast profile | 比較欄位 |
|---|---|---|
| g_a.0 | RNS NTT 延後模約減、重用 twiddle 計畫、兩個 ARM 執行緒並行。切塊直接寫入 BO 並維持原始排布。 | `ntt_ms`、`packing_and_resident_seconds`、`request_seconds`。Fast 的 BO 切塊已包含在 resident，baseline 的切塊在 slice。 |
| g_a.3 | 在現有 direct1 完整輸出核對流程中，用一個額外視窗預讀下一個輸入。 | `resident_batch_wall_sum_ms`、`admission_wait_ms`、`request_wall_ms`。Admission 服務時間可以和 PL 執行重疊。 |
| g_a.6／g_a.9 | 各 BO 重用位元相同的 kernel 參數。全量模式進行單分檔預讀，前景消耗前完成該分檔的完整輸入雜湊。 | `resident_seconds`、`part_read_ms`、`part_prefetch_wait_ms`、`request_ms`。短測只取首尾，因此採用原本的定位讀取。 |

每層仍依原座標核對所有輸出雜湊，量測保留讀檔、常駐交易以及整次請求時間。此套件評測卷積乘加重播。BN 已在原模型權重中折疊，g_a.2／g_a.5／g_a.8 的 OpenFHE 多項式啟動仍沿用原模型。

NTT 實作使用 Harvey 的延後模約減，並在輸出時還原成原本模 (q) 的標準表示。BO 寫入後仍透過 XRT 同步給裝置。

[Faster arithmetic for number-theoretic transforms](https://arxiv.org/abs/1205.2926)

[AMD XRT 2025.2 Native APIs](https://xilinx.github.io/XRT/2025.2/html/xrt_native_apis.html)
