# AIE 本地 DMA 量測補充包｜2026-10-16

適用：目前 VEK280、K=16、N=8192、L=3、boot UUID `1b664c9b428c5972904d75ffc08ea5df`、XRT 2.20.0／2025.2，以及已通過測試的 `diag_20261014`。

## 為什麼換方法

原本 CKKS 普通連續運算仍通過。出錯的是 native PLIO 的 `io_stream_start_to_bytes_transferred_cycles`：核心紀錄先有 combo event 申請失敗，後有介面 performance counter 不足。目前懷疑該 runtime 路徑的資源配置／清理，尚未完成唯一根因證明。

本補充包不使用該 API，也不配置 shim 介面 counter。改用 XRT runtime profiling，量 AIE **本地記憶體 DMA** 的活動與等待；原有 host 程式、硬體、BOOT 和 checksum manifest 都保持原樣，不需重新編譯。

這是替代量測，不是已修好 native PLIO API。腳本已做離線語法、流程與 coverage 檢查；實際 counter 是否可在板上取得，需先跑下面的 20 輪確認。

## 放在哪裡

把整個 `dma_profile_20261016` 資料夾上傳到：

```text
/root/114C75007/vek280/AIE/diag_20261014/dma_profile_20261016/
```

裡面要有新腳本、本說明、`.gitattributes`、`SHA256SUMS_DMA`。不要覆寫原本 `run_aie_profile_board.sh` 或 `run_plio_counter_board.sh`。

## 第一步：先確認替代量測能取得資料

```sh
cd /root/114C75007/vek280/AIE/diag_20261014/dma_profile_20261016
sh run_memory_dma_profile_board.sh out0 20
```

`out0` 先看本地 DMA 輸出 channel 0；20 是正式量測輪數，另有 3 輪暖機。使用 K=16 resident，每輪仍完整比對 73,728 個答案。

成功應有：

```text
PASS PERSISTENT: every repetition matched the full expected payload
PROFILE_COUNTER_ROWS_PRESENT: out0...
MEMORY_DMA_COMPLETE: download the entire ... folder.
```

「有 counter 列」只代表觀測到要求的事件，還不是瓶頸已定位。若 channel 0 沒被使用，全為零也可能是有效的未使用通道觀測；還需 channel 1 對照。若缺 CSV、缺要求事件或 host 失敗，腳本會保留結果並停止，不會自動重試或重設板子。

## 第二步：第一步成功後，再完整測四組

```sh
sh run_memory_dma_profile_board.sh all 200
```

每一組是獨立 session，3 輪暖機＋200 輪正式量測，避免同一 module 的有限 counter 同時配置多種 metric。整組輸出集中在一個新的 `memory_dma_results_XXXXXXXX` 資料夾。

| 子資料夾 | 量測對象 | XRT metric | 主要觀測 |
| --- | --- | --- | --- |
| out0 | 本地 DMA MM2S channel 0 | mm2s_throughputs | 輸出 stream backpressure、memory starvation、端口 running／stalled |
| out1 | 本地 DMA MM2S channel 1 | mm2s_throughputs | 同上，檢查另一個 channel |
| in0 | 本地 DMA S2MM channel 0 | s2mm_throughputs | 輸入 DMA lock stall、memory backpressure、端口 running／stalled |
| in1 | 本地 DMA S2MM channel 1 | s2mm_throughputs | 同上，檢查另一個 channel |

方向是以 **AIE 本地記憶體** 為準：S2MM 是串流寫進本地 buffer；MM2S 是從本地 buffer 讀出並送到串流。不是 shim DDR DMA 的方向。實際哪個 channel／tile 對應 left、right、partials，需由活動與編譯 mapping 交叉確認，不先假設 channel 0 一定是 partials。

## 要下載哪些資料

下載整個 `memory_dma_results_XXXXXXXX`，可壓成 7z。每個 case 包含 host log、逐輪時間、最後答案、xrt.ini、profile CSV、run summary 與 counter coverage。root 包含環境快照與使用的 ELF 雜湊。

第一步失敗也保留整個資料夾；若成功後跑了完整四組，完整四組的資料夾最重要，20 輪那份也可一起保留。

## 能回答與不能回答的問題

若量到輸出 DMA 長時間 stream backpressure，會強化 AIE 下游接收路徑受限的判斷；仍要辨識 channel、buffer 與路由，不能只憑單個數字就宣告 reducer 算術是唯一原因。

若輸入端口活動少，需結合輸出反壓判讀；下游停住也可能把等待一路傳回輸入。此套 predefined metric 沒直接提供所有 S2MM stream-starvation 事件，不能宣稱已完整量到所有輸入等待類型。

所有 metric 名稱雖有 throughputs，對 AIE-ML 的 raw CSV 仍是硬體事件／cycle 計數。需確認時脈、監測端口、計數單位與運算時段，才可換算 MB/s 或 stall 比例。原始 32-bit counter 也需要處理回捲。

原有成功路徑的字串建立成本尚未修改，主機 validation 空檔仍存在；分析時仍須與硬體運算區段分開。

## 對上一份報告的補正

上一份對 shim `input_stalls`／`output_stalls` 的適用性說明不完整：XRT 2.20 的初始事件表雖列出 DMA 事件，後續 `modifyEvents()` 會在 subtype=PLIO 時換成 PORT_STALLED／PORT_IDLE。因此不能只根據初始事件表判斷它們不適用於 PLIO。

但目前 native PLIO 測試已實際出現介面資源申請失敗，所以這份補充包先避開整個 shim counter 資源池，改量本地 DMA。它不是用改名方式重跑同一個失敗 API。

事件核對使用與板端相同的 XRT commit `74dec3c9c4f6dd9bfb62ae11e71ec96bcc4859eb` 與 AIE-ML physical event 定義：

| case | memory physical events 加 offset 1000 |
| --- | --- |
| out0 | 1037：stream backpressure；1041：memory starvation |
| out1 | 1038：stream backpressure；1042：memory starvation |
| in0 | 1031：stalled lock；1039：memory backpressure |
| in1 | 1032：stalled lock；1040：memory backpressure |

core stream monitor 的物理 event 號會隨分配的 monitor ID 改變，腳本檢查有效 running／stalled event 範圍，不硬套成 monitor 0。

參考：[AMD 本地 memory module profiling](https://docs.amd.com/r/en-US/ug1076-ai-engine-environment/Profiling-for-Memory-Modules)、[對應版本 XRT metric／事件修改](https://github.com/Xilinx/XRT/blob/74dec3c9c4f6dd9bfb62ae11e71ec96bcc4859eb/src/runtime_src/xdp/profile/plugin/aie_profile/util/aie_profile_util.cpp)、[DMA 端口選擇流程](https://github.com/Xilinx/XRT/blob/74dec3c9c4f6dd9bfb62ae11e71ec96bcc4859eb/src/runtime_src/xdp/profile/plugin/aie_profile/util/aie_profile_config.cpp)。
