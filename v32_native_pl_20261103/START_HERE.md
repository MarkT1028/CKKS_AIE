# 上板比較：原生整數純 PL 與雙 AIE

本輪目標是0顆AIE的純PL，在同一份h_s.4(mean)六組工作下與雙AIE比較。新候選為`v32_native_pl_2_pipe`，保留舊雙AIE `v32_core_2_pipe`及舊7對角純PL `v32_pure_pl_2_pipe`作控制。新候選的板上速度與實際輸出解密仍待測，不能把C模擬或HLS週期當成板上成果。

資料仍是N131072、L14、K16、六組、每組16塊，共33030144個輸出字。計時範圍仍為六組raw MAC的request，包含來源檢查、打包、同步、執行、合併與全量驗證；setup及獨立重算export另列。不是完整即時h_s.4或影像模型延遲。遠端Windows不需安裝OpenFHE。

## 傳哪個資料夾

把完整`v32_native_pl_20261103`新增到板子：

```text
/root/114C75007/vek280/AIE/v32_native_pl_20261103
```

保留同一AIE上層目錄的`v32_hs4_20261027`與已解開的`v32_full_hs4_20261031_data`，不用重傳3.3GiB資料。若實際位置不同，設定`V32_BASE_PACKAGE`與`V32_HS4_DATA`為正確絕對路徑。

## 1 檢查與編譯

板子Linux終端機逐行執行，前一行成功後才做下一行：

```sh
cd /root/114C75007/vek280/AIE/v32_native_pl_20261103
sh check_package.sh
sh build_board.sh
python3 window_board.py detect
```

編譯包含AIE、舊純PL、新直接乘法純PL三個不同host。它只做自測與資料打包核對，不會執行硬體或寫開機檔。請勿用舊套件的host執行新映像；新reader的N/L/K參數編號已變更，套件內已處理。

## 2 先取得雙 AIE 前測

如果detect已是`v32_core_2_pipe`，直接測試。若目前是舊純PL或新純PL，先手動切到雙AIE：

```sh
sh switch_board.sh v32_core_2_pipe check
sh switch_board.sh v32_core_2_pipe arm
```

看到`ARMED_ONLY`且沒有錯誤後，再由你手動執行：

```sh
sync && reboot
```

重開機後需要恢復IP時，可在序列終端機逐行執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

回到套件目錄，detect必須顯示`v32_core_2_pipe`。依序測試：

```sh
python3 window_board.py detect
sh run_hs4_compare.sh smoke
sh run_hs4_compare.sh formal
```

formal會依序跑正向與反向chunk/export_bounded。每種順序暖機1次、正式3次；CPU before、硬體measure-only、CPU after完成後，才另外啟動export重算並保存96檔。不要同時執行其他硬體測試。

## 3 切換新原生純 PL

```sh
sh switch_board.sh v32_native_pl_2_pipe check
sh switch_board.sh v32_native_pl_2_pipe arm
```

確認`ARMED_ONLY`後再手動`sync && reboot`。回到套件目錄後，必須detect為`v32_native_pl_2_pipe`且`AIE_compute_tiles`為0：

```sh
python3 window_board.py detect
sh run_hs4_compare.sh smoke
sh run_hs4_compare.sh formal
```

切換只處理已備份且校驗的slot1及一次性開機請求，不改stock BOOT.BIN、boot0002.bin、Image與boot.scr。若arm後決定暫不重開，可用`sh prepare_variant_srst.sh --cancel`取消一次性請求；取消不會還原已staged的slot1。

## 4 切回雙 AIE 回測

使用第2步相同check、arm、手動重開機流程切回`v32_core_2_pipe`，detect核對後再跑smoke及formal。AIE前測／新純PL／AIE回測三個boot全部保留，避免只用歷史最快數字當基準。

最後執行：

```sh
python3 compare_native_campaign.py
python3 collect_results.py
```

下載`download_this_file`指出的單一壓縮檔給我即可。全部成功、失敗、原始CSV、build與boot身份及實際輸出均保留。相同輸出只做傳輸去重，不刪除板上結果。

舊7對角純PL仍可用相同check／arm／detect／測試程序另作控制，但不能與新native混為同一版。

## 判讀與驗收

- 主指標是相同順序、同capture、同計時協定的完整request中位數；不同boot與順序分開呈現。
- 比較工具會列出新純PL是否數值上快於每個匹配AIE cohort；只有AIE前後兩個boot、相同資料與測試條件，以及CPU穩定性通過，才允許正式跨boot結論。未完成或漂移仍標記review。
- 本輪初始目標為同條件快過雙AIE，不能直接引用歷史3.50秒當本輪實測分母。純PL可能增加DSP、LUT及BRAM，資源另見`RESOURCE_COMPARISON.md`。
- CPU前後request或compute漂移超過5%，CPU速度比保持null。不能刪慢樣本、清全系統cache或修改sysctl製造有利比例。
- export是額外完整重算及buffered存檔，不是純寫檔時間；沒有fsync耐久性保證。
- 新候選實際板上輸出需下載後再做原上下文解密、平方及mean回填。離線96塊全部比對通過不取代此步。

## 本次硬體改動

1. 將reader改為512-bit載入，一拍讀取兩個係數的a0/a1/b0/b1。
2. 使用4-lane精確60×60→120-bit乘法，480-bit內部串流直接送完整乘積。
3. 移除15-bit limb、7組對角和與重建步驟，沿用精確Barrett約減與三個密文component累加公式。
4. 維持兩條管線、PL225MHz、同一DDR0、同一主機輸入格式與全量驗證。full-input BO同步範圍保持相同，沒有宣稱磁碟讀取或同步量下降。

這是整體純PL架構優化，包含讀取寬度與內部資料格式改動，不能把可能的加速只歸因於乘法器。沒有新增AIE或以CPU代跑。
