# VEK280：最多2顆AIE的效能對照

本包是新硬體的獨立候選，保留既有正式專案與正常開機版本。`PACKAGE_STATUS.json` 會列出實際封裝完成和仍未完成的版本；沒有出現在ready清單的版本不能執行。離線通過不代表板上已通過，也沒有預填任何加速倍數。

K=16仍然是16對密文的乘加工作量；AIE核心數最多2顆。

每個候選附`metadata_verification.json`，列出實際AIE kernel位置。CR(17,0)／CR(18,0)是座標；平台metadata中的38個column範圍也不是啟動38顆運算kernel。雙核心版本實際只有兩個kernel。

| 版本 | 用途 |
| --- | --- |
| baseline_1 | 和新版本相同介面設定的一核心基準，reader／reducer沿用原實作 |
| sink_1 | 快速接收原始partials、計數及指紋檢查；診斷用，不計算CKKS MAC |
| raw_1_pipe | 一顆AIE，reducer改成重建／模數／累加三階段DATAFLOW |
| raw_2_shared | 兩顆AIE，交錯產品frame，共用原始reducer和一條最終partials路徑 |
| raw_2_full | 兩顆AIE、兩個原始reader及兩個原始reducer |
| raw_2_pipe | 兩條完整管線，各搭配流水線reducer |
| diag_1_pipe | 一顆AIE，16份limb部分乘積合成7條精確對角和，搭配流水線reducer |
| diag_2_pipe | 兩條完整的對角和管線 |

兩條完整管線依係數區段分工：每顆處理N/2，但各自仍處理完整K。主機依tower把兩半結果合併；不是直接把原始輸入檔對切，也不是把K拆成兩半後忽略模數加總。

原始每批K=16的partials合計96 MiB；對角和格式合計42 MiB，減少56.25%。這是中間資料量的改變，不是宣稱執行時間一定減少56.25%。對角和的保守上界為4,294,705,156，超過signed int32但仍可放入uint32；AIE內部用64-bit accumulator計算。

## 開始前

把整包傳到板上的新目錄，例如`/root/114C75007/vek280/AIE/perf2_20261017/perf2_board`，保留`variants/`和`fixtures/`結構。每個`variants/版本/`有匹配的`boot0001.bin`、`ckks_hw_boot.xclbin`、manifest和專用主機設定。解壓、傳輸、編譯和`--check`均不更換SD開機檔。只有明確執行下述stage命令才備份並更換slot 1；prepare命令只預約一次切換，最後仍由你執行`reboot`。

硬體版本必須先用經核對的測試開機方式啟動。只有複製xclbin或重編主機程式，不會把既有reducer換成新硬體。`run_perf_board.sh`和C++ host都會檢查UUID；不符時拒絕啟動kernel，請勿刪除這個檢查。

2026-10-17使用者提供的板上盤點已確認：root是`/dev/mmcblk0p2`，SD boot是`/dev/mmcblk0p1`掛在`/run/media/mmcblk0p1`。BOOT.BIN／boot0002.bin均為原始e73f7a48…映像；boot0001.bin為原正常CKKS c12b4f6c…映像；Image與boot.scr也吻合原始SHA。切換腳本會在每次操作前重驗上述不變檔案及當前slot 1，不只依賴這次貼回的文字。

原`prepare_altboot_srst.sh`固定舊候選SHA；新包提供匹配每個候選的腳本，沿用原專案已使用的systemd關機末段PMC SRST流程。新腳本只經離線mock檔案測試和靜態檢查，尚未在板上執行。先用baseline_1逐步確認，再測其他候選。

## 1. 驗證傳輸與編譯

在板上進入解壓後的`perf2_board`資料夾：

```sh
sha256sum -c SHA256SUMS_PACKAGE
sh build_perf_board.sh baseline_1
```

編譯時使用板上自己的XRT headers和libxrt_coreutil，沒有關閉ABI檢查。`read_register`的deprecated warning是目前保留的ap_return檢查；是否編譯成功看最後的`HOST_BUILD_READY`及exit code。

其他版本同樣執行`sh build_perf_board.sh 版本名`。編譯本身不啟動硬體，可以先全部編好。若前面雜湊檢查失敗，先修正傳輸／換行，不能略過。

## 2. 先切換到新的baseline_1硬體

先保持原本可用的板子序列主控台開啟。以下命令在板上的`perf2_board`目錄內依序執行，每行是一個命令。

先看只讀檢查結果：

```sh
sh inspect_board.sh > board_before_switch.txt
sh stage_variant_board.sh baseline_1 --check
```

應出現`STAGING_PLAN`與`CHECK_ONLY`。如果任何一步FAIL，保留輸出並停止，不略過雜湊或板型檢查。

接著備份並放入候選，再核對切換條件：

```sh
sh stage_variant_board.sh baseline_1
sh prepare_variant_srst.sh baseline_1 --check
```

stage會先在SD建立並驗證`ckks_saved_SLOT1_c12b4f6cc3de7af2.bin`舊CKKS備份，再以同分割區暫存檔替換`boot0001.bin`。BOOT.BIN、boot0002.bin、Image、boot.scr不會被改寫。成功應有`STAGED_ONLY`，此時板上正在運作的仍是舊硬體。這種替換不能保證斷電時FAT目錄完全不受影響，因此切換過程保持供電，保留原始映像與備份。

只在前述檢查成功後，預約下一次重開機選slot 1：

```sh
sh prepare_variant_srst.sh baseline_1
```

應出現`ARMED_ONLY`；這一步本身不重開機。新hook只在RAM的一次性旗標存在且正常reboot的關機末段，確認root只讀、mmc分割區皆不可寫後，選slot 1並要求PMC SRST。它不覆蓋原專案的舊hook。若要取消本次預約，重開機前執行`sh prepare_variant_srst.sh --cancel`；取消只移除預約，已stage的檔案仍在slot 1。

最後執行：

```sh
sync && reboot
```

SSH會中斷，從原本的板子序列主控台觀察重新開機。登入後重新進入同一個`perf2_board`目錄。若啟動失敗，保留序列開機訊息，採原本可用的原始映像回復流程；不要反覆猜測或直接寫重置寄存器。

## 3. 在匹配的開機版本跑完整測試

先用每組1輪正式＋3輪暖機做短測；腳本會核對boot marker，UUID不符時不啟動kernel：

```sh
sh run_perf_board.sh baseline_1 1
```

四組均PASS後再執行正式測試：

```sh
sh run_perf_board.sh baseline_1 30
```

同一命令會跑K=1／K=16、resident／transfer四組，每組3輪暖機＋30輪正式。初始化、buffer配置和輸入切分每組只做一次。每輪都poison輸出，並完整比對73,728個word；只有mismatch時才建立錯誤字串。輸出合併時間另列為merge_ms。

第一組完成後，建議順序是`sink_1`、`raw_1_pipe`、`raw_2_shared`、`raw_2_full`、`raw_2_pipe`、`diag_1_pipe`、`diag_2_pipe`。每個版本都要重新stage、prepare及reboot，然後短測、正式測試。例如切換到兩條原始完整管線：

```sh
sh build_perf_board.sh raw_2_full
sh stage_variant_board.sh raw_2_full --check
sh stage_variant_board.sh raw_2_full
sh prepare_variant_srst.sh raw_2_full --check
sh prepare_variant_srst.sh raw_2_full
sync && reboot
```

重新登入並回到同一資料夾後：

```sh
sh run_perf_board.sh raw_2_full 1
sh run_perf_board.sh raw_2_full 30
```

其餘版本同理。一次只測目前實際開機的版本，不能直接在舊映像下依序跑全部版本。

`sink_1`只比較10個計數／指紋word，並且不輸出偽裝成密文的output_last.bin。指紋不是逐個partials word的完整存檔或密碼學證明；它配合已逐樣本驗證的AIE kernel，用來診斷接收端限制。sink時間不得當成完整CKKS加速比。

任何timeout、非零kernel狀態或結果不符，腳本會停止整個suite。保留結果與錯誤，不在未完成交易後繼續同一session。

## 4. 效能穩定後，另跑profile

主要比較使用profile關閉的結果；profile另開目錄，勿混算中位數：

```sh
PERF_PROFILE=out0 sh run_perf_board.sh raw_2_full 20
PERF_PROFILE=out1 sh run_perf_board.sh raw_2_full 20
PERF_PROFILE=in0 sh run_perf_board.sh raw_2_full 20
PERF_PROFILE=in1 sh run_perf_board.sh raw_2_full 20
PERF_PROFILE=heat_map sh run_perf_board.sh raw_2_full 20
PERF_PROFILE=stalls sh run_perf_board.sh raw_2_full 20
```

使用本地AIE DMA counter，native PLIO API保持未使用，不申請先前失敗的shim counter。新版雙核心的第一組輸入在MG(16,0)分用channel 0和1；兩個輸出則在MG(17,1) ch0和MG(18,0) ch0。因此要分別量channel 0／1，不能沿用舊版「channel 1都沒用」的結論。分析時對照每個版本附帶的DMA_report.txt、事件與傳送量，不能只看PROFILE檔存在就宣布覆蓋完整。20輪和2 ms取樣可降低碰到XRT大量資料寫檔門檻的機會，不是保證零干擾。

heat_map／stalls另外量核心運轉與停頓，檢查改善後lock stall是否下降；一次只選一種指標。這些仍需板上確認counter覆蓋與回捲，不能把資料列數當活動比例。host/session.txt與逐輪session相對時間供後續對齊；profile時鐘與主機時鐘仍須實際校正，不能直接視為同一時鐘。

## 5. 結果保存與比較

每次命令都建立新的`results_版本_指標_隨機字尾/`。請保留整個資料夾，包括iterations.csv、summary.csv、output_last.bin／sink指紋、host.log、環境、manifest、xrt.ini及所有profile產物。

把各版本結果下載到同一台電腦後，可執行：

```sh
python3 compare_results.py 結果根目錄 --fixtures 解壓後的perf2_board/fixtures --output comparison.csv
```

程式會用實際逐輪資料重算中位數；沒有實測檔案時直接拒絕輸出加速比。只有相同K、相同resident／transfer模式、profile關閉，且存在唯一匹配baseline_1的完整MAC結果，才計算相對加速。sink及profile開啟的資料不混入該加速比。

判讀順序：先確認正確性，再看execution中位數與P95，接著看transaction、merge、validation和資源。兩顆核心的execution是同時啟動後到全部完成的牆鐘時間，不是把兩顆各自耗時加總。

若sink顯著快於baseline，支持原reducer的消費／排程造成重要限制；若兩顆共用後端幾乎不變、兩條完整管線才下降，支持共享後端／路徑限制。即使如此，仍應結合反壓資料，不由單一數字斷定唯一根因。

## 6. 還原先前正常的CKKS版本

在Linux仍可正常操作時，可從第一次stage建立的備份還原slot 1。先取消本包尚未執行的預約，再依序執行：

```sh
sh prepare_variant_srst.sh --cancel
sh stage_variant_board.sh legacy --check
sh stage_variant_board.sh legacy
sh prepare_variant_srst.sh legacy --check
sh prepare_variant_srst.sh legacy
sync && reboot
```

還原後的舊CKKS UUID為`1b664c9b428c5972904d75ffc08ea5df`，使用原本diag／perf測試目錄執行舊程式。這個legacy操作恢復舊CKKS slot 1；原始BOOT.BIN與slot 2自始保留。新包的run_perf_board腳本會拒絕在舊UUID下啟動新kernel，這是預期行為。

切換紀錄在`switch_logs/`，舊CKKS及各候選的slot備份在SD根目錄。保留這些檔案到比較完成。
