# g_a.6 與 g_a.9 純 PL 上板測試

使用 `v32_native_splitbo_2_pipe` 的兩條純 PL 管線，啟動 UUID 為
`9bee253b8f345f39bd9c18d612897ce3`。這個套件使用板上既有的 xclbin 與測資，
無需再次傳輸兩層的分片。把此資料夾放到板上 `/root/114C75007/vek280/AIE/`，
和以下資料夾同層。

- `v32_ga3_splitbo_20261109` 提供硬體設定、XRT host 介面和板端鎖。
- `v32_ga3_finishopt_20261110` 提供已使用過的 OpenSSL SHA256 介面。
- `v32_ga_live_20261111` 提供既有分片使用的資料格式。
- `v32_ga6_offline_full_20261112` 和 `v32_ga9_offline_full_20261112` 提供原始分片與驗證資料。

## 編譯與短測

```sh
cd /root/114C75007/vek280/AIE/v32_ga_resident_20261114
sh build_board.sh
python3 -B run_board.py run ga6 smoke && python3 -B run_board.py run ga9 smoke
```

兩層都應出現 `PASS_GA_RESIDENT_SMOKE`。短測各取第一與最後一個係數／RNS 區塊，
保留所選區塊內的全部輸出與乘加組。g_a.6 會驗證 64 塊，g_a.9 會驗證 48 塊。
如果 UUID 不符，請先用既有的 Split BO 套件切換至上述映像。測試程式會顯示目前的 UUID。

## 完整測試

```sh
python3 -B run_board.py run ga6 full && python3 -B run_board.py run ga9 full
```

g_a.6 全量應驗證 2,048 塊、616,562,688 個 64 位元輸出值。
g_a.9 全量應驗證 1,152 塊、424,673,280 個 64 位元輸出值。
兩層執行期間每完成 32 個視窗會顯示進度。SD 分片讀取仍需要時間，
先前離線全量每層約 11 至 13 分鐘。

每輪輸出一個 `results_*` 資料夾。請傳回兩層完整測試的整個資料夾，
包括 `summary.json`、`tiles.csv`、`windows.csv` 與前後環境資訊。

## 怎麼看時間

- `resident_seconds` 是各視窗載入後的實測時間加總，涵蓋首次 BO 複製與同步、PL 啟動與等待、輸出同步，以及原始輸出格式的完整 SHA256。用它對照 g_a.3 的 31.366680443 秒。
- `admission_ms` 是輸入載入時間加總，其中 `part_read_ms` 和 `input_sha256_ms` 提供細項。
- 每份分片讀完後會建議 Linux 回收該檔案的快取頁面，並記錄建議失敗的次數。
- `request_ms` 涵蓋這次重播中載入、執行與結果紀錄的總時間。板端程式的啟動和緩衝區配置另外記為 `setup_ms`。
- `stage_work_ms` 是各步驟的累計工作時間。雙輸出緩衝區使部分步驟重疊。

預設 `direct` 依序對每個 RNS 模數的左右輸出緩衝區計算 SHA256。
如要確認省去合併複製本身的效益，可加上 `merge` 取得相同排程和驗證範圍的對照。
每次都使用新結果目錄。

```sh
python3 -B run_board.py run ga6 full merge
python3 -B run_board.py run ga9 full merge
```

比較範圍涵蓋原模型兩層的完整密文乘加工作量。完整推論的旋轉、重線性化和模型層之間的資料傳送由原程式處理。
