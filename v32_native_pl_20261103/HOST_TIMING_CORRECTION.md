# v2：匯出移至 CPU 後測完成後

2026-11-02 使用者回傳的第一輪雙 AIE smoke：CPU before 7321.043452ms、硬體請求7888.611315ms、額外匯出4951.394399ms、CPU after166165.90056ms。運算各輪完整比對33030144字，96個輸出與192個 trace 工作檢查通過；CPU request漂移2169.70%，因此不是有效的加速結論。

CPU after的read_bytes為3526164480，CPU before為4096；純compute為4785.895006→4518.677072ms，並沒有跟著request增加到166秒。前版export_bounded額外匯出會逐檔madvise/fadvise，硬體進程file RSS由約3.48GB降到約7MB；這與後測重新讀入大批來源資料一致。166秒的精確分項仍須原始資料與系統I/O紀錄確認，不能只由這份log斷言所有時間都來自同一機制。

前版順序：CPU before → 硬體測量及額外匯出 → CPU after。匯出造成的來源快取改變與寫入，夾在了測量比較中間。這是本輪主機測試排程的問題；正確性PASS不等於效能比較有效。

v2改為：

1. CPU before（正式模式先暖機1次、測量3次）。
2. 硬體 measure-only（相同暖機／測量次數，沒有額外匯出）。
3. CPU after（相同暖機／測量次數）。
4. 另一個硬體 export-only 程序：完整重算六組、逐檔退休建議及保存96個輸出。

保存 `phase_events.json` 的單調時鐘起訖，驗證各程序依序完成且export沒有插進CPU比較。匯出輸出在 `hardware_export/outputs/`；測量程序的 `hardware/outputs/` 不得包含輸出檔。匯出程序的XRT setup另記，不能加進正式request或假裝省掉準備成本。匯出時間是獨立程序的重算與緩衝寫入，與前版同程序匯出條件不同，不可直接宣稱等條件速度改善。

保留逐檔快取策略研究；v2不強制清除全域cache、不預讀假裝無成本、不改CPU計算、不改FPGA映像。`bounded`策略本身若用於一般測量，對CPU和硬體都適用；預設export_bounded只在最後匯出輪次生效。OS cache並未因此完全相同，CPU漂移仍保留。

smoke或CPU漂移超過5%的結果只列診斷比值，正式speedup欄為null；不能使用這輪21.06倍作為FPGA加速成果。候選是否快於前版仍待同協定正式測試。

本修正不需要切換boot或重開機。保留舊資料夾及smoke結果，另外上傳v2完整套件、重新執行check/build/detect/smoke。既有3.3GiB資料與兩個硬體UUID均沿用。
