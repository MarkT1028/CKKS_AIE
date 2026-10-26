# 對角和版本：前三項驗收與診斷

本套件日期2026/10/26，涵蓋：A2／B2反序重測、新密文輸入驗證、diag profiling及CPU A/A漂移診斷。維持兩顆AIE與既有映像，沒有新FPGA建置。

你上次diag的8份硬體保存輸出，已在開發電腦用OpenFHE1.5.1實際完成解密與密文平方，全PASS。四組新密文也完成軟體驗證，但**新測資尚未上板**。秘密金鑰保留在開發電腦，沒有放進本資料夾。

## 1. 完整上傳、檢查、編譯與辨識

上傳整個`diag_validation_20261026`，包括隱藏檔與所有子目錄，不覆蓋先前套件或結果。

```sh
cd /root/114C75007/vek280/AIE/diag_validation_20261026
sh check_package.sh
sh build_validation_board.sh
python3 validation_board.py detect
```

檢查應為PASS_VALIDATION_PACKAGE。編譯會建置comparison內三個原正式程式，以及CPU A/A與diag診斷host；只跑CPU自我測試，不執行PL／AIE、不寫開機檔、不重開機。detect可能是raw_2_pipe或diag_2_pipe，以實際UUID為準。

`comparison/`是原套件的完整凍結副本，內部SHA仍為e8eb79f26795ada7523163e6a22efa51905cd0a1f61d01195c399cc1dbae27e9。A2／B2沿用同一份正式host、CPU算法、fixture及計時邊界，能與原A1／B1合併比較。**不要修改comparison內的任何來源或SHA清單。**

## 2. 切回raw，先完成A2

保留序列埠終端機，執行：

```sh
sh switch_validation_board.sh raw_2_pipe check
sh switch_validation_board.sh raw_2_pipe arm
```

兩步成功且最後為ARMED_ONLY、沒有FAIL，才另行執行：

```sh
sync && reboot
```

開機後回同一資料夾：

```sh
cd /root/114C75007/vek280/AIE/diag_validation_20261026
python3 validation_board.py detect
```

必須顯示raw_2_pipe，UUID為f265f4974d10586c99675916b10bdf7e。然後依序：

```sh
sh run_repeat_board.sh raw_2_pipe smoke
```

短測PASS_ALL_24_CASES才做正式與新輸入測試：

```sh
sh run_repeat_board.sh raw_2_pipe formal
sh run_fresh_board.sh raw_2_pipe fresh_A2
```

formal固定30正式、3暖機、reverse，標記A2。若boot_id仍等於已記錄的A1會拒絕，以免同一開機只改名字充作重測。新輸入為四組密文，各resident／transfer，共8個正確性案例，1暖機＋1正式；其時間不併入正式速度結果。

## 3. 切至diag，完成B2與新輸入

```sh
sh switch_validation_board.sh diag_2_pipe check
sh switch_validation_board.sh diag_2_pipe arm
```

成功ARMED_ONLY後另行`sync && reboot`。開機後：

```sh
cd /root/114C75007/vek280/AIE/diag_validation_20261026
python3 validation_board.py detect
```

必須顯示diag_2_pipe，UUID為2b5c68811dc2575a91b0bb9d8f8e2f98。再依序：

```sh
sh run_repeat_board.sh diag_2_pipe smoke
```

短測全PASS後：

```sh
sh run_repeat_board.sh diag_2_pipe formal
sh run_fresh_board.sh diag_2_pipe fresh_B2
```

formal為B2 reverse，拒絕沿用上次B1的boot_id。新密文板測輸出下載後，會在開發電腦用對應私有context／金鑰重新解密與平方；板子不解密。

## 4. 正式測試完成後，再做CPU A/A診斷

先短測：

```sh
sh run_cpu_aa_board.sh quick AA_smoke
```

PASS_CPU_AA_ALL_3_AFFINITY_CASES後再執行：

```sh
sh run_cpu_aa_board.sh full AA1
```

各計算設定在**同一程序、同一組worker**內，依序做reuse、copy、reuse、reallocate、reuse，再以較長暖機重複。reuse會恢復並核對原本的input／output虛擬buffer地址；reallocate期間保留原buffer，確保新配置確實不同。比較CPU0單執行緒、CPU1單執行緒、雙核心三設定。

full每phase三個block，每block20正式，短暖機3次／長暖機30次，共10phase。逐輪仍完整核對golden。這是診斷，和正式CPU／硬體時間分開。它沒有量實體頁面或唯一識別快取、DDR與排程成因；複製與配置也會影響快取，控制結果須一起分析。

## 5. diag profiling先短測，再完整收集

```sh
sh run_diag_profile_board.sh heat_map 20 smoke_profile
```

確認答案全PASS且coverage為COUNTER_ROWS_PRESENT，才做：

```sh
sh run_diag_profile_board.sh all 200 diag_profile1
```

all包括baseline、heat_map、stalls、execution、dma_in0、dma_in1、dma_out0、baseline_after，序列執行，每組200正式＋3暖機。沿用diag實際metadata／DMA report核對過的核心與通道，沒有呼叫先前失敗的native shim PLIO profiling API。

profiling會改變觀測成本，這些時間不替代A2／B2正式時間。wait_observations記錄host看見完成的上界，不能直接當reader／reducer純硬體週期。若沒有counter或coverage是PARTIAL，保留全部資料，停止後續profiling並回傳；不要刪掉失敗結果或無限重跑。

## 6. 回傳一個檔案

全部完成後，或任何步驟失敗需分析時，執行：

```sh
python3 collect_results.py
```

會列出download_this_file。下載該`collected_results_....tar.xz`給我即可；若板上沒有lzma則自動產生.tar.gz。內容包含新結果、bin編譯身分及switch_logs，不包含測資、開機映像或私有金鑰。打包含壓縮與SHA核對，可能需要一點時間。

A2／B2結果位於comparison/results_compact_...，診斷與新測資結果位於本層results_...。請保留舊compact_compare_20261024資料夾，原A1／B1仍用於合併比較。

## 7. 其他常用入口

重新開機後若需恢復IP，在序列埠執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

若尚未重新開機、要取消已arm請求：

```sh
sh comparison/prepare_variant_srst.sh --cancel
```

原A1／B1及新A2／B2若都在板子，可用同一個E8正式分析器：

```sh
python3 summarize_repeats.py ../compact_compare_20261024/results_compact_* comparison/results_compact_*
```

須有原四個結果資料夾；若路徑不同請改成實際路徑。即使覆蓋完整，CPU漂移超過5%仍會保留qualified狀態，這不是結果錯誤。後續新解密及counter結論須以回傳資料完成實際分析，不能預填。
