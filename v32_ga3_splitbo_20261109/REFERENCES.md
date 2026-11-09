# 實作依據與計時限制

- Python 官方 os.stat：dir_fd、follow_symlinks、stat 欄位及平台差異。新路徑每次重新 stat，不把舊 stat 結果當新檢查。https://docs.python.org/3.12/library/os.html#os.stat
- Linux pread：指定 offset 的讀取不改共享檔案位置。預讀視窗另持有自己的檔案、解碼與輸出緩衝。https://man7.org/linux/man-pages/man2/pread.2.html
- Linux posix_fadvise：DONTNEED 是建議，不保證實體快取清除，因此記錄測試順序和實際 read_bytes，沒有使用全域 drop_caches。https://man7.org/linux/man-pages/man2/posix_fadvise.2.html
- AMD UG1399：要求 PIPELINE II=1 不代表實際一定達到；需檢查依賴、HLS 實際報表和 RTL，再做完整 routed 時序檢查。https://docs.amd.com/r/en-US/ug1399-vitis-hls/Automatic-Loop-Pipelining
- XRT 官方 BO API：sync 依平台可能是傳輸或 cache maintenance，host envelope 不能直接當 DMA cycle。https://github.com/Xilinx/XRT/blob/master/src/runtime_src/core/include/xrt/xrt_bo.h
- OpenSSL EVP digest：延續前版板上可用的 libcrypto SHA256，不導入新的核心雜湊介面。https://docs.openssl.org/3.0/man3/EVP_DigestInit/

精確延後約減是本專案的算術推導，並非照抄外部效能數字。對 canonical q<2^60、K<=16：c0/c2<16q²<2^124，c1<32q²<2^125，所以128-bit累加不溢位。mu=floor(2^128/q)，x<2^128 時估計商至多低1，因此一次條件減法即可得到 canonical residue。已用獨立整數除法 oracle、真實53模數資料及隨機停等 RTL 驗證；板上速度仍待測。

歷史 CUDA 數字只取自本機已封存 reference_results/v32_results_full_gpu.json；該原層與目前 raw MAC 工作量不同。CUDA_TARGET_ASSESSMENT.json 明確記錄參數、資料常駐與計時差異，不能宣稱公平 CUDA speedup。
# 本輪分離輸入介面的官方依據

- [AMD Vitis HLS 2025.2 — M_AXI Bundles](https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/M_AXI-Bundles)：A/B 各自指定不同 bundle；是否真的產生兩個 512-bit AXI master，以本輪 XO 的 XML 及完整連結結果核對。
- [AMD XRT Native APIs — Buffers](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html#buffers)：沿用板上已測過的 cacheable BO，依各 kernel argument 的 group_id 配置；寫入後明確 sync，並以單一唯讀 BO 供兩個讀取 CU 使用。

同檔保留先前套件的參考紀錄。本輪不依文件推定加速幅度，速度仍需實際上板比較。

