# 2026/10/26 完成項目與驗收界線

本套件是前三項實驗的上板準備，沿用raw_2_pipe與diag_2_pipe既有映像。沒有新增AIE、修改FPGA或取得新一輪板上效能。

| 項目 | 已完成 | 下一輪板測要確認 |
|---|---|---|
| A2／B2正式重測 | 保留原E8套件全部來源、旗標、測資與計時方式；新增不同boot_id檢查與reverse案例順序入口 | 兩次重新開機後各做30正式、3暖機，與原A1／B1交叉比較 |
| 解密與平方續算 | 原diag保存的8份硬體輸出已實際用OpenFHE1.5.1全數驗證 | 四組新密文，各raw／diag、resident／transfer輸出，下載後再實際解密與平方 |
| 對角和效能診斷 | 核對diag實際核心、DMA座標與通道；建立CPU同程序／同worker／同buffer A/A控制 | 實際diag counter、API trace、完成觀測與CPU漂移資料 |

上次diag硬體輸出的最大MAC誤差為1.679600903e-12，平方續算誤差為3.619587269e-13。驗證替換全部73,728個殘值，解碼4,096個slot，再做relinearize、rescale及一次密文平方；不是只檢查部分slot，也不代表已完成下一層卷積或完整v32推論。

新密文共有兩種明文模式×K=1／16，涵蓋全部4,096個slot，包括正負值與零。已完成實際OpenFHE加密、軟體golden、解密與平方。四組軟體驗證最大MAC誤差2.092659379e-11、平方誤差3.538858095e-11。門檻分別為1e-7及1e-6。**四組新輸入尚未經板子運算。**這些測資延用現有N=8192、L=3與模數設定，屬運算整合驗證，沒有改變既有參數。

秘密金鑰、context、eval key與密文template留在開發電腦私有測資目錄，沒有放進本套件。回傳檢查工具也已準備好，會核對fixture、映像、host來源、完整輸出，再呼叫本機固定版本的OpenFHE verifier。

CPU A/A保留原CPU運算實作，增加buffer與暖機控制，沒有把診斷時間混進正式CPU比較。固定虛擬地址不能證明實體頁面與cache完全相同；重新配置同時也會影響複製及快取，因此結果只能配合其他控制分析，不能單獨認定漂移原因。

profiling使用目前映像的AIE核心與local DMA counter，另存host API trace及完成觀測。沒有新增PL硬體計數器，host觀測到完成的時間是上界，不能當成reducer本體精確週期。coverage不足會保留結果並停止後續profiling。

comparison內的狀態文件是10/24原套件的凍結歷史快照，為保持E8身分而未改字。10/25板測及10/26解密驗證的目前狀態，以本文件、references/a1_b1_identity.json與offline_evidence/OpenFHE_verification.json為準。

請依START_HERE.md順序執行。正式時間、正確性新測資與診斷資料分開收集，最後collect_results.py會產生一個可回傳的壓縮檔。
