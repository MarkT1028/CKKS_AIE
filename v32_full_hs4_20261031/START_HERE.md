# 完整 h_s.4(mean) 六組板測

本套件的功能目標是：真實 h_s.4(mean)96輸出通道、4×4位置，6組各16對密文乘加，板上算完全部96個密文乘積與6個精確加總，下載後以原v32執行完整層回填驗收。

原v32目前只使用h_s.4的mean半部（原192通道中的96通道），scales半部沒有用於後續流程。此套件沿用這個需求，不擴大成原192通道或整個模型即時加速。

## 上傳兩份內容

1. 程式目錄 `v32_full_hs4_20261031`：可透過Git傳送。
2. 真實測資 `v32_full_hs4_20261031_data.tar.gz`：請直接用SFTP傳到板子，不加進Git。解壓後目錄名為 `v32_full_hs4_20261031_data`。

兩個目錄都放在既有 `v32_hs4_20261027` 的同一層。保持以下結構：

```text
AIE/
  v32_hs4_20261027/                 原有套件，提供跨套件裝置鎖
  v32_full_hs4_20261031/            本輪程式
  v32_full_hs4_20261031_data/       本輪六組真實raw資料
```

測資輸入的baby rotations六組共用一份，減少重複傳送；板上每次只保留一組展開快取，約938MiB。XRT、graph、kernels、兩組BO及準備worker跨六組重用。金鑰、context、OpenFHE物件和旋轉金鑰不在上板測資中。

在AIE目錄解壓：

```sh
tar -xzf v32_full_hs4_20261031_data.tar.gz
cd v32_full_hs4_20261031
sh check_package.sh
sh build_board.sh
python3 full_board.py detect
```

測資有約3.31GiB的未壓縮raw資料。checksum會讀取全部檔案，程式會顯示CHECK_DATA進度；這段時間在效能量測之外。每個單獨資料檔小於50MiB，但整份資料仍很大，請使用分開的測資壓縮檔。

若放在不同位置，可先設定：

```sh
export V32_HS4_DATA=/完整路徑/v32_full_hs4_20261031_data
export V32_BASE_PACKAGE=/完整路徑/v32_hs4_20261027
```

## 確認映像

本輪沿用已驗證的雙AIE核心映像，預期boot UUID為：

```text
050ea5cc23fb5038bad0aca23cbd240b
```

detect顯示 `matching_variant=v32_core_2_pipe` 即可繼續，不需重新開機。如果目前是其他消融映像，先用之前 `v32_campaign_20261030` 套件的既有切換流程回到 `v32_core_2_pipe`。本輪腳本不寫SD、不設定重開機、也不強制runtime載入PDI。

## 依序執行

```sh
sh run_board.sh smoke
```

smoke會依序跑相同六組資料的CPU前測、雙AIE、CPU後測。雙AIE另做一次完整export回合，保存全部6×16＝96個輸出檔。每次都做全量係數比對。

smoke通過後再依序跑：

```sh
sh run_board.sh formal
sh run_board.sh formal --reverse
python3 collect_results.py
```

正式每次有3筆量測與1次warmup，每一筆都完整跑六組；第二個命令把六組順序反過來。不可平行執行不同測試。沿用原套件 `.board.lock`，整個CPU前測／硬體／CPU後測期間都持有同一把鎖。

collect會列出 `download_this_file`，只下載那個 `collected_full_hs4_....tar.gz` 給分析。使用gzip level1、顯示索引與壓縮進度，並在完成後重新核對每個成員。會保留失敗與中斷的資料夾，不挑最快一筆。

## 如何解讀結果

- `full_six_streamed_wall_ms`：板上六組raw MAC的實際wall，包含每組資料載入／展開及完整結果驗證，排除一次setup與獨立export。
- `resident_verified_wall_ms`：各組已載入後的原完整驗證wall；不要與六組含載入wall混用。
- `host_execute_envelope_sum_ms`：主機start至wait返回的包絡，不能當純AIE、DMA或device cycles。
- `CPU_before/after`：相同六組、相同compact loader、兩個持續worker及完整驗證；原u128運算核心沿用，不是最佳CPU或OpenFHE整層對照。
- CPU前後compute、六組含載入wall或resident wall任一漂移超過5%會標review，保留所有樣本與OS page cache影響，不代表密文算錯。
- `PASS_FULL_SIX...`只表示板上六組raw MAC通過。完整h_s.4仍需用下載的實際輸出做原context回填、relinearization、旋轉合併、聚合、bias及解密驗收。

不將六組raw MAC的時間命名為完整h_s.4端到端時間。原CPU資料準備與後處理、跨機傳輸和後續模型另列。

## 已避免的舊問題

保持boot UUID與flat metadata配對；不用runtime強制載入PDI。板上預設關閉profiling，不占用先前衝突的shim counters。status在下一次graph啟動前讀取，bank通過驗證及必要export才重用。全量資料、scalar結果、metadata與原context都有獨立驗收，不以單組重播或平方測試取代整層輸出。

檔案雜湊須通過，`.log`與`.rpt`證據也納入Git傳輸測試。保留歷史套件、原v32程式與舊報告；這輪新增檔案及套件。

第三顆AIE的模擬證據另存evidence，板上正式套件維持已驗證的兩顆。三路4096係數分割131072個係數會有32個有效shard與1個補零shard，不可直接把8192除以3丟掉尾端。三AIE尚無完整PL實作／boot映像與板上速度，等待整層量測再決定是否進入該候選。
