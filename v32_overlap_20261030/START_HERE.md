# 真實 v32：輸出收尾重疊與 AIE／reducer 獨立對照

這是新一輪候選套件，**實際速度及本輪輸出的解密續算仍待上板回傳驗收**。上一輪的 624.600 ms 是既有 `v32_core_2_pipe` 加原 `map_pingpong` 排程的結果，不先替新排程填入速度。

## 本輪做了什麼

1. 加入 `map_finish_overlap`：區塊 i 的 graph、reader、reducer 全部完成且讀回狀態後，先啟動 i+1，再合併與完整驗證 i 的輸出。i 驗證／匯出結束才把同一個 bank 交給 i+2 的準備工作。任何時刻只有一個 graph 在執行，不增加 AIE。
2. 保留 `map_pingpong` 原排程，兩版都保留輸入／輸出 sync、poison、完整合併、5,505,024 個係數逐字驗證，以及另一次完整輸出匯出。可在同一次開機正反序比較，不用為這項主機修改換韌體。
3. 補齊只改 AIE、只改 reducer 的兩份映像，與原版和兩者皆改版形成四格對照。這四版必須固定 `map_pingpong` 比較，避免把主機排程的收益混入硬體貢獻。
4. 加入同程序 CPU A/A 診斷與跨 boot 分組統計。CPU 算術來源、兩個執行緒及編譯選項沿用原參考。診斷取樣另跑，不代替正式的相鄰 CPU 前後測；不改 governor、時脈、核心上下線或全域快取設定。

## 上傳哪個資料夾

只上傳 `v32_overlap_20261030`，放在板上 `v32_hs4_20261027` 旁邊：

```text
/root/114C75007/vek280/AIE/
  v32_hs4_20261027/        # 必須保留，重用原896MiB輸入和42MiB golden
  v32_coreopt_20261029/    # 舊套件保留
  v32_overlap_20261030/    # 本輪上傳資料夾
```

本套件沒有重複附加 938 MiB 測資，沒有任何私鑰；不需要把前版測試結果刪掉。

## 第一階段：先測主機排程，不換韌體

```sh
cd /root/114C75007/vek280/AIE/v32_overlap_20261030
sh check_package.sh
sh build_board.sh
python3 board_runner.py detect
```

若 detect 是 `v32_core_2_pipe`，UUID 應為 `050ea5cc23fb5038bad0aca23cbd240b`，直接執行：

```sh
sh run_round.sh v32_core_2_pipe host
```

此指令依序執行兩排程 smoke、正式正序、正式反序、CPU A/A 診斷及 campaign 摘要。每項 PASS 才進入下一項，沒有背景並行執行多個板測命令。formal 每個排程為 1 次暖機、5 次正式硬體，以及硬體前後各 1 次暖機加 3 次 CPU。每個排程另外運算並保存一次完整輸出，匯出不納入正式中位數。正反序合計每排程 10 筆正式硬體樣本。

若要拆開執行而非一次 round：

```sh
sh run_board.sh smoke v32_core_2_pipe
sh run_board.sh formal v32_core_2_pipe
sh run_board.sh formal v32_core_2_pipe --reverse
python3 cpu_diagnostics.py
python3 summarize_campaign.py
```

兩種入口選一種使用即可；重複執行不覆寫舊結果，會建立新資料夾。請不要同時執行兩個入口。

## 跨開機重現

先完成並保存第一輪。再於你方便時重新開機，保持同一核心映像，回到此資料夾重新 `detect`，再跑同一個 `run_round.sh`。建議累積至少三個新版 boot。摘要以 Linux boot_id 分組，同一次開機重跑不算新的 boot。

一般同映像重新開機前：

```sh
sync && reboot
```

如果重開後 detect 不是 `v32_core_2_pipe`，依下面受保護切換流程回到目標，再開始該輪。腳本沒有自行重啟板子。

重開後若需恢復既有 IP，在序列埠終端機執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

## 第二階段：分開比較 AIE 和 reducer

| variant | AIE | reducer | 上板要使用的排程 |
| --- | --- | --- | --- |
| v32_diag_2_pipe | 原版 | 原版 | map_pingpong |
| v32_aie_only_2_pipe | 新版 | 原版 | map_pingpong |
| v32_reducer_only_2_pipe | 原版 | 新版 | map_pingpong |
| v32_core_2_pipe | 新版 | 新版 | map_pingpong |

先在目前核心版執行：

```sh
sh run_round.sh v32_core_2_pipe ablation
```

接著依序切換另外三種 variant。以下以「只改 AIE」示範，每次只換 variant 名稱：

```sh
sh switch_fair_board.sh v32_aie_only_2_pipe check
sh switch_fair_board.sh v32_aie_only_2_pipe arm
```

確認成功印出 `ARMED_ONLY` 後，親自執行：

```sh
sync && reboot
```

重開、恢復 IP、回到套件後：

```sh
python3 board_runner.py detect
sh run_round.sh v32_aie_only_2_pipe ablation
```

對 `v32_reducer_only_2_pipe`、`v32_diag_2_pipe` 重複同樣流程，最後建議回到 `v32_core_2_pipe` 再測，保留時間與開機差異的回測證據。不同映像和 boot 不會直接合併成一個中位數。硬體兩個修改可能互相影響，各自收益不一定可以相加。

切換 `check` 只檢查；`arm` 備份並替換 slot 1、準備一次切換，不立即重啟。BOOT.BIN、Image、boot.scr、slot 2 保持原檔。重開前取消：

```sh
sh prepare_variant_srst.sh --cancel
```

## CPU 診斷與判讀

`cpu_diagnostics.py` 使用相同 cached_cpu，在同一程序固定資料及 worker 做 2 次暖機、12 次量測，保留每次結果與各執行緒的 `/proc` ticks、page faults、last_cpu、記憶體和回報時脈。last_cpu 不是 migration 次數；scaling_cur_freq 也不保證是實際硬體時脈。診斷程序有額外取樣成本，所以只用於穩定性觀察。

板子已有可用 `perf` 時，可另外跑：

```sh
python3 cpu_diagnostics.py --perf
```

若 PMU 不支援或權限不足，會保存失敗原因，不改系統設定，不當成零 cache misses。一般正式結果仍保留。CPU 漂移超過 5% 會標示待檢查，不刪除該輪。

選用的 perf 統計涵蓋另一次完整 CPU 程序，包含讀入、設定與驗證，不代表只有算術核心的計數。

## 結果與下載

做完目前規劃的輪次後執行：

```sh
python3 summarize_campaign.py
python3 collect_results.py
```

下載最後印出的 **`collected_overlap_*.tar.gz` 一個檔案**即可。收集顯示索引、壓縮和 SHA 驗證進度，包含所有成功／失敗結果、CPU 診斷、環境、各模式完整輸出及切換紀錄，不包含896MiB輸入或私鑰。保留每一組輸出，回傳後再做原上下文解密與 Python 續算驗收。

## 量測範圍

主要指標仍是第一塊準備開始到最後一塊合併和完整驗證結束的實際常駐 wall；包含排程等待，不扣掉驗證。一次設定、計時 CSV 寫入、獨立 export replay、網路和完整模型另列。

新排程會把前一塊讀回工作安排在下一塊 `start` 與 `wait` 回傳之間，所以 `execute_sum_ms` 是 **主機 start-to-wait-return 區間**，可能包含控制執行緒處理前塊的時間。它不是獨立 AIE／PL 純運算時間，不能與前版約526ms直接等同解讀；請以本輪同 boot、同量測框架的完整 wall 比較。`finish_during_other_execute_ms` 也只代表主機區間交集，不是 DMA／AIE 硬體事件證明。

這輪仍是同一組固定真實 h_s.4 輸入；新增的零值／最大值／隨機邊界測試屬離線功能測試，並非另一組獨立真實推論。更多 workload／level、reader 供料 profiling、即時跨機 v32 與能耗仍待後續驗收。

`RESOURCE_MATRIX.json`另列四份實際routed設計的LUT／FF／DSP／BRAM與時序，方便回傳後一起比較。

參考：[XRT Native APIs](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html)、[Linux CPUFreq](https://docs.kernel.org/admin-guide/pm/cpufreq.html)。
