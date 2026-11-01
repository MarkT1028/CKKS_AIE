這輪只優化 h_s.4(mean)

範圍固定：N=131072、L=14、6組K16、每組16個chunk；沿用已驗收雙AIE映像。原v32、私鑰、解密與完整層回填仍留在本機。遠端Windows只使用Git/MobaXterm傳檔並操作板子，不需Python、OpenFHE或原v32。不新增cheby_y、decoder或整個影像專案。

改動

1. 唯讀映射同一份既有compact資料；直接按chunk打包至2-bank BO，取消938MiB整組展開輸入cache及中間大陣列copy。映射的file RSS仍可能很大，不能把heap減少當總RAM減少。
2. 同一完整六組request的baby資料只檢查一次，其檢查時間仍算在request wall。六組餵給FPGA時仍須讀取並打包B值，不宣稱底層實體讀取量已減少多少。
3. 保存pack/檢查、shared validation、同步、執行、回讀、驗證與process IO/RSS/缺頁紀錄；trace格式化移至主要request計時之外。CPU沿用原2-thread數學核心，使用相同映射來源及完整驗證。
4. raw結果寫檔改成bulk，輸出bytes維持原格式。setup與獨立export另列；不把重疊work總和稱為wall或純device cycles。

已做本機內測；板上效能與實際輸出回填仍待這輪實驗。

傳送與目錄

只傳新版程式資料夾v32_stream_20261101，既有3GB測資不用再傳。板子保持：

```text
AIE/
  v32_hs4_20261027/                 跨套件同一把.board.lock
  v32_full_hs4_20261031_data/       既有測資，保持原檔不修改
  v32_full_hs4_20261101/            上輪套件，保留
  v32_stream_20261101/             這輪新版
```

既有測資須維持不可變；測試期間不要替換、截短或修改檔案。程式做SHA/metadata檢查並記錄檔案變動，mmap仍需要不可變資料的合約。

板上依序執行

```sh
cd /root/114C75007/vek280/AIE/v32_stream_20261101
sh check_package.sh
sh build_board.sh
python3 stream_board.py detect
sh run_board.sh smoke
```

預期UUID：050ea5cc23fb5038bad0aca23cbd240b，matching_variant=v32_core_2_pipe。不需換映像或重開機。本套件不寫boot區、不自動重設系統，也不開啟之前有resource conflict的profiling counters。

smoke跑新CPU前測、串流雙AIE（另有一次輸出匯出）、新CPU後測。每輪都驗證六組33,030,144個raw words，保存96個輸出。每個階段有進度；若FAIL保留整個資料夾，停止後續測試。

smoke通過再依序：

```sh
sh run_board.sh formal
sh run_board.sh formal --reverse
python3 collect_results.py
```

formal每個phase1次warmup、3次量測，hardware另1次export。全部樣本都保存，不挑最快，CPU前後request或compute漂移超過5%標review。

為取得同次開機的舊路徑對照，可選擇加跑（較久）：

```sh
sh run_baseline_board.sh smoke
```

需要驗證同一組XRT資源跨兩個六組request重用時，可選擇：

```sh
sh run_service_test.sh
```

這只重複同一層、同一份fixture，兩種順序，由同一process/graph/CU/BO/worker處理；不是遠端執行原v32，也不是新影像的live推論。選跑後再執行collect_results.py即可一起收集。

結果解讀

- 新主要欄位request_wall_ms：包含每輪shared validation、mapped read faults/pack、執行與全量驗證，排除一次setup及獨立export。不可直接拿它當舊版不含載入的3.28秒resident欄位算加速。
- 新CPU/HW使用同一個protocol，可比較request wall；與舊路徑比較時，只比較各自都包含載入的完整六組wall，並保留setup/export與cache差異。
- group_wall_ms內的pack可能與另一bank的執行重疊，pack/execute/verify WORK不能相加當總延遲。
- read_bytes反映block-backed儲存層請求；rchar不含一般記憶體存取，不能代表mmap所有讀取量。VmHWM是process生命期高水位，RssFile可能包含大部分映射資料；需一起看RssAnon與CMA。
- 最終下載collect列出的collected_stream_....tar.gz；會包含stream、可選service、可選baseline以及失敗/中斷紀錄，重新逐成員驗證SHA。不包含測資或私鑰。
- 實際板上速度、原context回填與解密驗收完成前，不把本機software model時間寫成硬體效能，也不把完整h_s.4層驗證說成整個影像專案完成。

參考OFFICIAL_SOURCES.md，原始舊版入口保存在run_baseline_board.sh及host/full_host.cpp。
