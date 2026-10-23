# 2026/10/23 同板CPU與四架構比較

## 已完成與待執行

- 單／雙路流水線的16份保存輸出，已重跑OpenFHE 1.5.1 EXACT解密與密文平方續算，全部PASS；摘要見PIPELINE_DECRYPTION.json。
- CPU程式新增1／2計算執行緒，完整保留原本U128累加後取模的算術方法。
- 離線功能及記憶體檢查見OFFLINE_VERIFICATION.json；PC／WSL的時間不當作ARM CPU結果。
- 本包尚未在VEK280執行新的CPU／硬體效能實驗。歷史18.52 ms與15.46 ms不冒充本輪同條件結果。

## 四種映像

| 版本 | AIE | reducer |
| --- | --- | --- |
| baseline_1 | 1 | 原版 |
| raw_1_pipe | 1 | 流水線 |
| raw_2_full | 2 | 原版，兩條完整管線 |
| raw_2_pipe | 2 | 流水線，兩條完整管線 |

四個既有映像、common host及開機檢查保留原始位元組，不重建FPGA。舊manifest的OFFLINE_VALIDATED_NOT_BOARD_TESTED是原封裝時狀態；10/19及10/21板測證據保留在既有報告，本輪另產生新紀錄。

## 工作量與CPU方法

固定同一批N8192、L3、K1／16及相同q、輸入、輸出。每輪比較全部73,728個整數，最後輸出另與golden逐byte核對。
CPU每個係數先用unsigned __int128累加K組四種分量乘積，最後對三個總和各取模。q小於2^60、K最多16，最大總和小於2^125。
1執行緒由主執行緒直接計算；2執行緒用預先建立並持續重用的兩個worker，按N各半分工，各自保留完整K及L。主執行緒只負責派工與等待。
本輪是單／雙執行緒CPU參考實作，不宣稱為最佳化CPU上限，也不是OpenFHE完整操作的速度。

## 計時範圍

| 指標 | 包含內容 |
| --- | --- |
| CPU compute_ms | 整數乘加與取模；2執行緒包含派工與完成等待 |
| CPU verified_call_ms | 輸出填毒、compute、完整整數驗證 |
| 硬體 execution_ms | XRT啟動、PL／AIE資料流與完成等待 |
| 硬體 transaction_ms | 每輪上傳（transfer）、填毒、execution、狀態、讀回、合併及完整驗證 |

CPU與硬體皆排除檔案解析／存檔、一次性配置及初始化。CPU worker pool與XRT資源均在迭代前建立。
CPU輸入已在ARM記憶體，不為了模仿DMA而額外加入不必要的輸入拷貝；硬體resident和transfer各自列出。
比較compute對execution時，兩者包含不同控制成本，不能稱為純運算核心cycle比較。verified_call對transaction才回答兩種raw呼叫實際耗時。
原應用匯出／回填、relin／rescale、解密及完整推論仍不在以上範圍內。

## 每次run的順序與正式樣本

run_fair_board.sh VARIANT REPS SESSION會執行12個案例：

1. CPU前測：K1／K16，各1／2執行緒，4個案例。
2. 硬體：K1／K16，各resident／transfer，4個案例。
3. CPU後測：同前測，4個案例。

每案例3次暖機加REPS次正式測試。REPS=30時，硬體每模式30筆；CPU每K／執行緒有前30及後30共60筆。分析同時保留前後差異，不刪除慢樣本。
編譯皆用同板g++及-std=c++17 -O3 -Wall -Wextra -pthread；硬體host另連結XRT。程式保存來源／binary SHA、編譯器、旗標及相同fixture雜湊。
效能測試關閉profiling／trace。頻率、governor、affinity、溫度、kernel與boot_id在每案例前後記錄；是快照，不是全程監控。
不自動更動CPU頻率、governor、網路或電源。若前後頻率不同或CPU耗時飄動，先保留結果並重測；不直接把差異歸給硬體版本。

## 同日對照與跨開機重現

先在同一天完成四個版本的round1，盡量保留相同編譯器、輸入、CPU頻率與負載條件。當前匹配版本可先跑，減少多餘切換。
再各於另一個開機session完成round2，建議反向版本順序。即使相同版本，也要於另一個boot_id重測，才算跨開機驗證。
本流程需要分別開機載入四個硬體版本，不是同一次開機隨意更換metadata；也不是逐樣本隨機交錯的A/B。
有部分資料可以先分析。彙整工具會標記尚缺的版本、正式次數或不同boot_id，不把部分覆蓋寫成全部完成。

## 彙整結果

在具有本包來源及fixtures的電腦，指定已下載的完整結果資料夾；輸出目錄必須尚未存在：

```sh
python3 summarize_results.py results_fair_raw_1_pipe_round1_XXXXXXXX --output-dir comparison_round1
```

可同時列出多個結果資料夾。產生comparison.csv、comparison.json與比較摘要.md。
工具重新核對逐輪序號、暖機、phase加總、中位數／P95、完整輸出、來源、編譯器與環境覆蓋。
速度比為CPU時間÷硬體時間；大於1表示該邊界下硬體較快。單／雙執行緒、resident／transfer分開報告。

## 套件與版本切換

check_package.sh核對全部列出的來源、映像及fixture SHA；build_fair_board.sh建立新的CPU與四個既有XRT host。
detect只讀取目前UUID及環境，不切換硬體。run遇到不匹配UUID會在CPU／硬體開始前停止。
switch_fair_board.sh VARIANT check為唯讀預檢；arm沿用既有受保護slot1備份與切換／一次性SRST流程；重開機仍由使用者另行執行。
若要取消預約：sh prepare_variant_srst.sh --cancel。
所有新測試建立獨立results_fair_*資料夾，不覆蓋既有結果。共用parser及XRT舊來源可能出現unused／deprecated等warning；以編譯exit code及最後PASS記錄判定成功。
