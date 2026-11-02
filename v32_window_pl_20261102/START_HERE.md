# 本輪上板：六組資料重用／輸出優化＋純 PL 對照

本套件是 `v32_window_pl_20261102`。沿用既有 `h_s.4(mean)` 六組真實資料：N＝131072、L＝14、K＝16，每組16塊，共96塊、33030144個輸出字。範圍是六組 raw MAC 重播及完整驗證；不是整個影像模型，也不是完整原 h_s.4 的即時端到端延遲。

兩個候選已完成離線檢查，**實際板上速度及新版板上輸出的解密／續算仍待測試**。遠端 Windows 不需要安裝原 v32、Python 或 OpenFHE。

## 先上傳哪個資料夾

只需新增這個完整資料夾至板上：

```text
/root/114C75007/vek280/AIE/v32_window_pl_20261102
```

既有 `v32_hs4_20261027` 與已解開的 `v32_full_hs4_20261031_data` 保留在同一個 AIE 上層目錄；本輪不用重傳約3.3GiB測資。若原測資在別處，先設定實際絕對路徑：

```sh
export V32_HS4_DATA=/實際位置/v32_full_hs4_20261031_data
export V32_BASE_PACKAGE=/實際位置/v32_hs4_20261027
```

Git只用來傳新套件。上板透過原本 SFTP 傳完整資料夾即可；不要在板上覆蓋舊套件。參考 `GIT_COMMANDS_CMD.txt` 的 Windows CMD 指令。

## 第一步：先測目前雙 AIE 映像

板子 Linux 終端機依序執行，每個成功後再下一個：

```sh
cd /root/114C75007/vek280/AIE/v32_window_pl_20261102
sh check_package.sh
sh build_board.sh
python3 window_board.py detect
```

`check_package.sh` 會重算既有全部測資 SHA，顯示 CHECK_DATA 進度。`build_board.sh` 會建立原基準、新 CPU、AIE host、純 PL host；執行 CPU 與資料打包自測，**不會執行硬體或切換映像**。read_register deprecation warning 已保留，warning 不等於 build 失敗。

若 detect 的 `matching_variant` 是 `v32_core_2_pipe`（UUID `050ea5cc23fb5038bad0aca23cbd240b`），可以直接測，不需重開機：

```sh
sh run_board.sh smoke
```

成功後執行完整同開機比較：

```sh
sh run_compare_layouts.sh formal
```

它會**依序**執行四個實驗，每個都有 CPU before → 硬體 → CPU after：group/retain、chunk/retain、chunk/export_bounded、反序 chunk/export_bounded。每個正式實驗先暖機1次、測量3次；硬體另外重算並保存完整96個輸出。請勿同時開另一個硬體測試。每次都產生新的 `results_window_*`，失敗也保留。

## 第二步：切換純 PL，再測完全相同流程

先確認，以下 check 不會改板子開機檔：

```sh
sh switch_board.sh v32_pure_pl_2_pipe check
```

確認全部成功後，手動執行 arm：

```sh
sh switch_board.sh v32_pure_pl_2_pipe arm
```

這會備份並替換 SD 的 `boot0001.bin`，掛上一次性 RAM 開機請求；保留 stock `BOOT.BIN`、`boot0002.bin`、Image、boot.scr。看到 `ARMED_ONLY` 且沒有錯誤後，才由你手動重開機：

```sh
sync && reboot
```

如果決定先不重開機，可取消請求：`sh prepare_variant_srst.sh --cancel`。取消只移除一次性請求，不還原已 staged 的 slot1；原映像仍可透過下方切回流程恢復。

重開機後若需要恢復你先前使用的網路位址，在序列終端機執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

重新連線並回到新套件：

```sh
cd /root/114C75007/vek280/AIE/v32_window_pl_20261102
python3 window_board.py detect
```

必須看到 `matching_variant` 是 `v32_pure_pl_2_pipe`、`AIE_compute_tiles` 是0。再依序執行：

```sh
sh run_board.sh smoke
sh run_compare_layouts.sh formal
python3 summarize_window_campaign.py
python3 collect_results.py
```

`collect_results.py` 會顯示 INDEX／COMPRESS／VERIFY 進度。把最後 `download_this_file` 指向的 **`collected_window_pl_*.tar.gz` 一個檔案**下載給我即可。它包含成功／失敗紀錄、編譯身份、CPU環境、原始CSV、routed資源與每次實際輸出的身份索引；相同輸出內容只傳一份，原板上檔案不刪除。這是可驗證的傳輸去重，不是刪掉實驗。

若要切回雙 AIE：

```sh
sh switch_board.sh v32_core_2_pipe check
sh switch_board.sh v32_core_2_pipe arm
```

確認 arm 成功後，再手動 `sync && reboot`。回測可使用同樣 formal 指令，新資料夾不會覆蓋前一次。

## 如何判讀

優先比較同一 boot 下的 `request_wall_ms`，它包含來源檢查、baby快取拷貝、打包、同步、計算、合併、完整驗證，以及該模式的逐檔快取釋放建議。CPU使用相同布局、驗證與快取策略，保留既有雙執行緒 u128 數學核心。

`setup_ms` 是一次性準備；`export_full_recompute_ms` 是**額外重算六組再寫出252MiB**，不等於單純寫檔時間。timeline 的 `output_save` 可單獨檢查。輸出是一般緩衝寫入，沒有 fsync 的掉電耐久性保證。重疊階段加總不是 wall time；host execute 是包絡，不是 device cycles。

CPU 前後 request 或 compute 漂移超過5%會標記 review_required，不能刪掉較慢樣本。OS頁面快取狀態沒有強制統一；不要把結果稱作冷快取實驗。不要自行清除全域 cache 或更改 sysctl。

## 這次改了什麼

1. 改成同一區塊先處理六組，共用 baby資料的28MiB工作窗：每輪 baby來源載入由96次降到16次；雙bank、雙lane的baby寫入由192次降到64次。**完整輸入 BO 同步仍保留，沒有宣稱 DDR 傳輸量同步減少。**多了28MiB匿名快取，不能沿用舊版4MiB匿名記憶體宣稱。
2. 把既有雙緩衝／finish-overlap 延伸到全部96個工作；保留一個硬體 invocation、先讀 status 再啟動下一個、完整驗證後才重用bank。
3. `export_bounded` 只在額外輸出輪次，對已用完的唯讀來源檔執行 madvise/fadvise，減少無用映射的壓力。這是建議，不是硬性RAM上限或加速保證。`bounded` 可選擇在一般輪次也執行；正式矩陣保留 retain 控制組。
4. 純 PL 版本以兩個 HLS 精確7對角和核心替換兩顆 AIE，reader/reducer XO與現有AIE版完全相同，兩條管線、DDR0、PL225MHz。沒有 libadf、AIE metadata、graph物件建構或graph.run；不是CPU代跑，也不是省略乘法。資源見 `RESOURCE_COMPARISON.md`。

新 group/retain 控制組仍使用新的全96工作 scheduler，不能直接當作舊版 stream 的同協定測量。若要保留原協定基準，僅在雙 AIE boot 下另執行 `sh run_original_stream_board.sh formal`；舊 stream 結果會放 `results_stream_*`，請另用 `python3 collect_stream_results.py` 收集。

內測清單與限制見 `OFFLINE_VERIFICATION.json`。完整原 v32／OpenFHE 回填只在本機驗證；新板上輸出回傳後還要再驗收。本輪不是遠端電腦執行完整影像模型。
