# 雙 AIE 流水線 reducer：本輪板測

本次先測raw_2_pipe，與已測過的raw_2_full比較。兩版都是兩顆AIE、兩條完整管線；主要硬體改動是reducer分成重建、取模、累加三階段流水線。

流水線硬體映像沿用先前已完成建置與離線驗證的候選，尚無板上效能成績。本輪新增的是獨立測試包、簡化入口、完整記錄與針對兩版的比較工具。C++運算、輸入切分、計時與完整驗證程式保持一致。這輪沒有CPU效能測試。

## 1. 上傳

將整個reducer_test_20261021資料夾放到板上，例如：

```text
/root/114C75007/vek280/AIE/reducer_test_20261021
```

也可把tar.gz放到AIE目錄後執行`tar -xzf reducer_test_20261021.tar.gz`。保留整個資料夾結構，包括fixtures、variants與reference_results_20261019。各版本manifest中的未板測欄位是當時建置狀態；目前狀態以根目錄PACKAGE_STATUS.json與實際結果為準。

## 2. 檢查與編譯（不切換硬體）

在板子的Linux終端機逐行執行：

```sh
cd /root/114C75007/vek280/AIE/reducer_test_20261021
sh check_package.sh
sh build_reducer_board.sh
sh switch_reducer_board.sh raw_2_pipe check
```

確認出現PACKAGE_READY、HOST_BUILD_READY、STAGING_PLAN與CHECK_ONLY。前面有FAIL就先保留輸出並停止。編譯使用板上XRT，保留ABI與硬體UUID檢查；read_register的deprecated warning與先前相同。

## 3. 切換成流水線硬體

保持COM4序列主控台與供電。這一步會備份目前slot 1、放入流水線候選，並預約下一次重開機；它本身不會重開機。

```sh
sh switch_reducer_board.sh raw_2_pipe arm
```

確認最後是ARMED_ONLY之後，再另外執行：

```sh
sync && reboot
```

重開機是為了載入另一份PL／AIE硬體；只換host或xclbin檔案不會改變現在執行中的reducer。本包沿用原本已使用的匹配開機、slot備份與systemd關機末段SRST流程，保留BOOT.BIN、slot 2、Image、boot.scr的原始雜湊檢查。

如果要在重開機前取消預約，執行`sh prepare_variant_srst.sh --cancel`。取消預約不會將已stage的slot 1檔案換回去。

## 4. 重開機後，先短測，再正式30次

登入後回到同一個資料夾：

```sh
cd /root/114C75007/vek280/AIE/reducer_test_20261021
sh run_reducer_board.sh 1
```

四組都PASS後再執行：

```sh
sh run_reducer_board.sh 30
```

每次命令包含K1／K16、resident／transfer四組，各有3次暖機。正式命令是每組30次，不是總共30次。每一輪仍poison並完整核對73,728個輸出整數。當前硬體UUID不符時會在啟動kernel之前拒絕執行。

輸出會自動保存在新的`results_raw_2_pipe_none_隨機字尾/`；短測與正式測試各一個資料夾，舊結果保留。根目錄LAST_RESULTS_raw_2_pipe.txt記錄最近一次的結果位置。

## 5. 給我哪些結果

將短測與正式30次的兩個results_raw_2_pipe_none資料夾完整下載並壓縮給我。保留summary.csv、各案例host.log、iterations.csv、output_last.bin、session.txt、環境與硬體識別；不要只傳截圖。

結果中的execution是PL／AIE主流程（含啟動與等待），transaction包含每輪搬移、讀回、合併與驗證。解密及完整應用後處理沒有算在這裡。

## 6. 自行查看與舊雙路版的差異（可選）

把以下例子的資料夾名稱換成正式30次實際產生的那一個：

```sh
python3 compare_reducer_results.py results_raw_2_pipe_none_XXXXXXXX --output comparison_reducer.csv
```

會輸出CSV與JSON，包含四組的主流程時間、P95、交易時間與相對raw_2_full的加速比。只有正確性通過、profiling關閉、每組至少30次且樣本數相同的結果才接受；1次短測、缺檔、錯誤輸出、不同測資、不同主機來源或錯誤硬體身份會拒絕比較。

預設參考是包內2026年10月19日的真實raw_2_full完整結果，K16 resident主流程22.755281 ms。這是歷史參考，沒有假裝成今天重跑或同日交錯A/B。若要做同輪對照，可再切回raw_2_full、重新測量，並以`--reference 新的raw_2_full結果資料夾`指定。比較工具可在板上Python3或下載後的開發電腦執行，不會自動跑CPU。

## 7. 切回原雙完整管線，或補做同輪對照

先編譯對照版本，再核對與預約切換：

```sh
sh build_reducer_board.sh raw_2_full
sh switch_reducer_board.sh raw_2_full check
sh switch_reducer_board.sh raw_2_full arm
```

看到ARMED_ONLY後再另外執行`sync && reboot`。登入並回到本目錄後，可執行：

```sh
sh run_reducer_board.sh 1 raw_2_full
sh run_reducer_board.sh 30 raw_2_full
```

## 8. 本輪狀態與代價

- raw_2_full已在10/19完成四組正式板測，最新保存輸出於10/20通過OpenFHE解密與密文平方續算。
- raw_2_pipe已建好匹配boot與metadata、通過離線驗證，仍需這次板測才能判斷速度。
- 兩版AIE數都為2，原始partials合計仍為96 MiB；這不是七對角和版本。
- 流水線版使用較多PL資源：LUT25,101→34,852，DSP110→334。要同時評估時間與代價，不預填加速倍數。
- design/保留本次兩種reducer來源供查閱；板上只需編譯host，不需要安裝Vitis或重新綜合HLS。
