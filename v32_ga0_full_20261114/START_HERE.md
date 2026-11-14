# g_a.0 純 PL 全量密文乘明文板測

使用同一張 `input_64x64.png`、原始模型權重與 OpenFHE CKKS 參數。
涵蓋 16 個輸出、每個輸出 4 組 K=16、N=131072 的全部係數和 57 個 RNS 模數。
全量共 15,360 塊，驗證 1,434,451,968 個輸出字。

套件沿用 `v32_native_splitbo_2_pipe` 的兩條純 PL 乘加管線，
開機 UUID 為 `9bee253b8f345f39bd9c18d612897ce3`。
把此目錄和 `v32_ga3_splitbo_20261109`、`v32_ga3_finishopt_20261110`、
`v32_ga_live_20261111`、`v32_ga_resident_20261114` 放在同一層。

## 搬資料

`fixture` 約 8.13 GiB。它包含每組加密權重（由 16 個輸出共用）、
編碼明文的單份整數係數、RNS 模數與根，以及完整輸出雜湊。
每組的明文係數讀入 RAM 一次，再依批次重建各個 RNS 模數。
MobaXterm 可直接上傳 `fixture` 裡的資料，不需另在板上保留壓縮檔再解壓。
成果資料夾另需少量空間。既有韌體及其他層的測資可留在板上。
若資料放在別處，測試時用 `--data /path/to/fixture`。
如果透過 Git 傳到遠端 Windows，使用小批次逐次提交和推送，待所有批次完成後再 pull。

## 執行

```sh
cd /root/114C75007/vek280/AIE/v32_ga0_full_20261114
sh build_board.sh && python3 -B run_board.py smoke
```

看到 `PASS_GA0_CTPT_SMOKE` 再執行全量。

```sh
python3 -B run_board.py full
```

成功後請傳回 `results_ga0_full_*`，包含 `summary.json`、`tiles.csv` 及前後環境資訊。
也可把 `RESULTS=` 後的路徑代入 `python3 -B run_board.py collect --result`，
下載它輸出的單一 `.tar.gz` 檔案。
全量會逐組、逐批輸出進度。若需中斷且留下未完成的 PL 執行標記，保留結果並重新開機再跑。
第一個 RNS 批次須先重建明文，所以進度行可能隔一段時間才出現。

## 計時欄位

- `resident_seconds` 包含已備妥分塊的 BO 上傳、PL 運算、輸出取回和完整 SHA256。
- `read_seconds` 記錄實際程式讀檔呼叫耗時，包含可能的 Linux 快取命中。
- `ntt_ms` 是板上 ARM 將明文重建到各 RNS 模數的時間，`slice_ms` 是拆分與補零時間。
- `preloaded_including_ntt_and_slice_seconds` 包含載入後的明文重建與執行。
- `request_seconds` 包含讀檔、輸入驗證、明文重建與所有密文乘加。

板測的驗證範圍是首層 64 組的完整密文乘加。完整卷積的旋轉、聚合、加偏置及
解密驗證在本機 OpenFHE 做，與原影像的空間域卷積核對。
