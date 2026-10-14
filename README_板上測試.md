# CKKS 板上連續運算與資料流診斷

日期：2026-10-13。適用於已成功跑過 K=1、K=16 的 VEK280 開機硬體。

這次要回答兩個問題：重用 XRT 資源後每批要多久？原來約 45.26 ms 的 K=16 流程，是運算忙碌，還是在等資料或等下游？

測試範圍仍是本專案的 raw NTT/RNS MAC：輸入已在 NTT/RNS 表示，K=16 是 16 對輸入做乘法累加，輸出一組三分量結果。本測試不把 NTT 轉換、OpenFHE relinearization／rescale／decrypt 算進硬體時間。

## 1. 要上傳哪些檔案

將此資料夾的全部內容（包含 `configs` 子資料夾與隱藏的 `.gitattributes`）上傳到板子：

```text
/root/114C75007/vek280/AIE/diag_20261013/
```

使用 MobaXterm 左側 SFTP。Windows 端先解壓 ZIP，再上傳解壓後的內容，不要只傳 ZIP。

板上原本的以下五個檔案留在上一層 `AIE`，新程式直接讀它們，無須再複製：

```text
ckks_hw_boot.xclbin
inputs.bin
expected_raw.bin
inputs_k16.bin
expected_k16_raw.bin
```

新的測試包沿用 UUID `1b664c9b428c5972904d75ffc08ea5df`。它只註冊 boot-only xclbin 的中介資料，沿用開機時已載入的 PL/AIE 設計。

## 2. 在哪裡輸入指令

以下指令全部在**板子的 Linux 終端機**輸入：MobaXterm 的 COM4 或 `192.168.10.98` SSH 分頁均可。COM4 在網路斷線時仍方便觀察。

先登入 root，建立資料夾：

```sh
cd /root/114C75007/vek280/AIE
mkdir -p diag_20261013
```

上傳後確認檔案，並編譯：

```sh
cd /root/114C75007/vek280/AIE/diag_20261013
ls -l
ls -l configs
sh build_diag_board.sh
```

成功會看到 `DIAG_BUILD_READY`。這一步只編譯程式。

若 `.gitattributes: FAILED open or read`，請補傳隱藏檔。若校驗失敗，請重新傳原檔，不要在 Windows 編輯後改成 CRLF。不要跳過校驗。

## 3. 先做連續運算測試

```sh
sh run_persistent_board.sh 30
```

腳本會先檢查新包校驗值、原版測資校驗值與格式。每個 K 先跑同板 CPU 基準，再跑以下四個硬體案例：

| 案例 | 每輪輸入是否重新傳輸 | XRT 資源建立次數 |
|---|---|---|
| K=1，resident | 第一次傳輸後重用 | 此案例一次 |
| K=1，transfer | 每輪重傳 | 此案例一次 |
| K=16，resident | 第一次傳輸後重用 | 此案例一次 |
| K=16，transfer | 每輪重傳 | 此案例一次 |

每個案例在**同一個程序**內先暖機 3 次，再量測 30 次。同一案例持續重用 device、kernel、graph、三個 BO，以及 reader/reducer run 物件。每輪仍啟動 reader、graph、reducer，等三者完成，再讀回與驗證。這是資源重用測試；不同輪之間尚未做雙緩衝或運算／傳輸重疊。

`resident` 是輸入已留在板子 DDR，並非所有資料都留在 AIE 本地記憶體。reader 每輪仍由 DDR 讀取輸入，PL/AIE 的內部串流量也仍存在。

程式會在每輪開始前，以不合法的 residue 值填滿輸出 BO，再同步到板子，防止拿上一輪留在 DDR 的答案誤判成功。此額外驗證動作記為 `poison_ms`；不計入 `execution_ms`，但計入 `transaction_ms`。

每輪逐字比對完整 73,728 個輸出 word，最後另存完整 `output_last.bin` 並與原版期望檔逐 byte 比對。任何錯誤或超時都會停止案例，保留已取得的資料。

成功會看到：

```text
PASS PERSISTENT SUITE: four cases verified
```

結果在新建的 `persistent_results_XXXXXXXX` 資料夾。再次執行會建新的資料夾。

### 3.1 如何看結果

打開最外層 `summary.csv`，先看四行資料的以下欄位：

| 欄位 | 白話意思 |
|---|---|
| `init_ms` | 一次性的中介資料註冊及 XRT kernel/graph 建立時間 |
| `allocate_ms` | 一次性的參數整理、向量與 BO 配置時間 |
| `initial_upload_ms` | 第一次把輸入、參數同步到板子 |
| `setup_ms` | 一次性的 kernel 參數設定及 graph reset |
| `execution_median_ms` | 多輪整條 PL/AIE 流程完成時間的中位數 |
| `execution_p95_ms` | 95% 樣本不超過的執行時間，使用 nearest-rank 定義 |
| `transaction_median_ms` | 每輪從傳輸／輸出填值，經運算、讀回到答案比對完成的時間 |
| `measured_loop_wall_ms` | 30 次正式測試整段牆鐘時間，包含逐輪 CSV 與少量終端機輸出 |

`execution_ms` 的起點在 reducer 啟動前，終點在 reader、reducer 與 graph 都被確認完成後；包括 CPU 發出啟動與等待指令、PL 讀 DDR、AIE 計算、串流等待與 reducer 寫回。它沿用原測試的計時範圍，**不是純 AIE 算式時間**。

`transaction_ms` 也包含完整正確性驗證與防止舊答案的輸出填值，因此是本診斷程式的每輪成本，不是已完成生產流程最佳化後的吞吐量。

先判斷：

1. 如果 `init_ms` 仍約數十 ms，但每輪 `transaction_ms` 明顯縮短：表示重用資源消除了重複初始化成本。
2. 如果 K=16 的 `execution_median_ms` 仍約 45 ms：表示初始化改善了主機流程，PL/AIE 內部瓶頸仍存在。
3. 比較相同 K 的 resident/transfer：每輪 `upload_ms` 呈現重傳輸入的成本；執行時間的差异也可能受快取、負載與量測波動影響，不應全部歸因於傳輸。

各案例的 `iterations.csv` 保留所有暖機與正式樣本。`reader_observed_done_ms`、`reducer_observed_done_ms`、`graph_observed_done_ms` 是從同一起點到 CPU **觀察到完成**的累計時間；因等待順序與管線重疊，不可相減後宣稱各元件獨立耗時，也不能只看誰最後完成就判斷瓶頸。另記錄 `execution_start/end_session_ms`（相對此案例初始化起點）與 `execution_start/end_unix_us`（Unix 時間微秒），方便核對運算區段。對照 XRT profile 前仍須確認該檔案的時間基準，不能直接把不同時間欄位當成同一時鐘。

舊資料供比較：K=1 execution 中位數 3.664590 ms；K=16 為 45.264311 ms。舊樣本每個程序重新建立 XRT 資源；此次要用實測結果判斷改善量。

## 4. 再做 AIE 計數器分析

確認第 3 節四個案例都 PASS 後，先執行：

```sh
sh run_aie_profile_board.sh heat_map 200
```

這會在同一程序連續跑 K=16，暖機 3 次、正式 200 次，開啟 AIE `heat_map` 與記憶體 `conflicts`。採樣間隔設為 1,000 µs，實際間隔仍受主機調度影響。此設定用來收集忙碌、停等與記憶體衝突線索。

如果出現 `PROFILE_FILES_PRESENT`，再執行：

```sh
sh run_aie_profile_board.sh stalls 200
```

第二次獨立執行會細分 stall 類型。不同 metric 各自執行，避免有限的 performance counter 互相搶資源。需要更細的指令或接口資訊時，再選用：

```sh
sh run_aie_profile_board.sh execution 200
sh run_aie_profile_board.sh input_stalls 200
sh run_aie_profile_board.sh output_stalls 200
```

profile 程式仍逐輪驗證答案。**profile 的時間不能拿來取代第 3 節的基準時間**，因為採樣執行緒會增加主機與驅動開銷。

`PROFILE_FILES_PRESENT` 只表示找到候選 CSV，還要確認內有有效的 tile、event 與樣本。如果看到 `PROFILE_UNAVAILABLE`，表示板上 XRT plugin、boot-only 中介資料或 counter 路徑尚未產出可用資料；答案 PASS 並不表示 profiling 成功。保留結果與錯誤訊息即可，先不要改 BOOT 或反覆 reset。

這次使用 runtime performance counter profiling，設定 `aie_trace=false`。更完整的事件 trace 與 PL `TVALID/TREADY` 逐周期分析，可能需要新增 trace／監測硬體後重新建置；本次先用現有設計取得可用證據。

### 4.1 現有硬體對應

```text
DDR 輸入
  ↓
ct_reader_1
  ├─ ckks_graph.left  ─┐
  └─ ckks_graph.right ─┤
                      ↓
                 AIE limb_mul.mul
                      ↓
              ckks_graph.partials
                      ↓
              ct_reduce_accum_1
                      ↓
                   DDR 輸出
```

現有編譯中介資料是一個 AIE kernel，graph 名稱 `ckks_graph`，core column=17、相對 row=0；PLIO 在 shim column=17。設定以 graph 名稱選取，避免手動猜測相對 row 與實體 row 的差異。

### 4.2 要找什麼現象

| 量測線索 | 優先檢查的位置 | 仍需釐清 |
|---|---|---|
| AIE 活躍時間中輸入缺料，輸入端吞吐低 | reader、DDR 讀取、封包供料及輸入 DMA | 也可能是下游反壓傳回輸入端 |
| 有輸出可送卻長時間送不出去 | 輸出通道、reducer 的接收與後續運算 | 應排除通道／buffer 鎖設定問題 |
| 有效運算期間 instruction/vector 活動多、stall 少 | AIE limb multiply 本身 | 需核對事件定義，不把指令數直接當耗時比例 |
| memory conflict／lock stall 多 | AIE buffer、DMA、記憶體 bank 與上下游同步 | 本專案使用 buffer；lock 等待不等同 core stream stall |

計數器也會看到兩輪之間的輸出填值、讀回與主機驗證空檔。**不能把整個程序的總 stall 比例直接當成 45 ms 內的 stall 比例**；應檢查時間序列中有資料傳輸的區段，交叉比較不同 metric。若計數器無法明確分離供料不足與反壓，只能先縮小疑點，尚不能斷言單一瓶頸。

K=16 每批 AIE→PL 的中間結果為 100,663,296 bytes，最終 residue payload 為 589,824 bytes。大量中間結果也要通過輸出通道與 reducer，因此增加 AIE 核心前，必須確認下游能消化更多資料。

## 5. 可選：單一 PLIO 的傳輸周期計數器

`build_diag_board.sh` 會顯示 `PLIO_COUNTER_API=1` 或 `0`。若為 1，可依序各跑一次：

```sh
sh run_plio_counter_board.sh left
sh run_plio_counter_board.sh right
sh run_plio_counter_board.sh partials
```

每次只用一個 port，以避免 counter 資源衝突。程式使用 XRT AIE profiling API，量測從該端口第一個有效傳輸，到指定整批 byte 數傳輸完成的周期數。left/right 各為 12,582,912 bytes；partials 為 100,663,296 bytes。記錄在 `counter_cycles`、`counter_bytes`。

若 API 或底層 counter 不支援，腳本會清楚停止並保留資料；仍可使用第 3 節的基準測試。周期數先保留原值，不用編譯中介資料的頻率直接換算 ms；必須先確認該 counter 的實際時脈域與當時頻率。端口資料傳完也不等於整批 graph/reducer 已完成。

## 6. 下載與提供哪些結果

請從 SFTP **整個下載**：

```text
persistent_results_XXXXXXXX/
aie_heat_map_results_XXXXXXXX/
aie_stalls_results_XXXXXXXX/
```

若有做 optional 測試，其他 `aie_*` 與 `plio_*` 資料夾也一起下載。不要只保留畫面截圖。

裡面包含主機 log、`iterations.csv`、`summary.csv`、最終輸出、`board_env.txt`、實際使用的 `xrt.ini`，及 XRT 產生的 profile CSV/JSON/run summary。profile 結果資料夾會帶一份板端已編譯的診斷程式，讓程式位置與工作目錄一致，方便收集 XRT 產物；原版大測資仍直接沿用上一層的檔案。保留整個資料夾，才能核對採樣事件、時間序列與正確性。

可先貼最外層 `summary.csv` 的四行資料與 profiling 結尾訊息。若成功產生 `xrt.run_summary`，後續可在電腦端 Vitis 的分析功能開啟；本階段板端不用啟動 Vivado。

如果原版測資放在另一個位置，可指定而不複製：

```sh
CKKS_BASE=/root/114C75007/vek280/AIE sh run_persistent_board.sh 30
```

## 7. 完成條件與目前驗證範圍

第一項完成條件：四個資源重用案例全部 PASS，得到每輪與汇總時間；每輪答案比對成功，末輪完整檔案比對成功。

第二項完成條件：取得有正確事件、有效 counter 與樣本的 AIE profile，能以時間序列與接口活動判斷忙碌或等待；若底層不支援，先用生成的環境與 log 確認缺少什麼，再决定下一個量測方式。

本包在電腦端可檢查 C++ 語法、shell 語法、原版 xclbin／K=1／K=16 測資，以及錯誤測資拒絕行為。**板上 ARM 連結、重複啟動 graph/kernel 與 profiling counter 能否工作，仍須本次上板實測確認**。

## 8. 依據

- XRT 資源與 run 重用：[XRT Native APIs](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html)。
- 配置檔指定方式：[XRT runtime configuration](https://xilinx.github.io/XRT/master/html/xrt_ini.html)，使用 `XRT_INI_PATH` 指向各測試設定。
- 分次使用 heat_map、conflicts、stalls 與 execution：[AMD UG1076 Metric Sets](https://docs.amd.com/r/en-US/ug1076-ai-engine-environment/Metric-Sets?contentId=rQSEoHPjB8TTcmv~GKzlwA)。
- 端口計數器定義：[XRT 2025.2 xrt_aie.h](https://github.com/Xilinx/XRT/blob/2025.2/src/runtime_src/core/include/xrt/xrt_aie.h)。
- 專案依據：既有 `arm_app/perf` 主機程式、boot-load／boot-k16 deploy 校驗清單及 `aie_control_config.json`。資料量與 kernel 名稱來自本專案設計，不是通用 CKKS 假設。
