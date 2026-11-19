# VEK280 `g_a` 主流程效能對照

套件沿用四層原始測資和逐塊 SHA-256。`g_a.0` 的 `fast` 主機會在 ARM 做 NTT 時預讀加密權重，並用兩組 BO 將下一塊明文打包及同步、上一塊輸出回讀及驗證與 PL 執行重疊。`g_a.3` 於同批內重用各 BO 的模數參數。`g_a.6／.9` 保留尺寸相同的 XRT 執行參數。`g_a.3／.6／.9` 沿用直接 BO 與輸出雜湊排程，預讀可獨立開關。

| `detect` 的 `image` | 會跑的層 | PL 路徑 |
| --- | --- | --- |
| `ctpt` | `g_a.0` | 已上板的密文乘明文專用映像 |
| `splitbo` | `g_a.3／.6／.9` | 已上板的四乘積純 PL 映像 |
| `dual3` | 四層 | 11/18 已上板的共用三乘積映像，供同主機對照 |
| `tuned` | 四層 | 同一映像放入 CTPT 和四乘積 CTCT 的專用核心，每次使用對應的一對管線 |

`detect` 會依目前開機 UUID 選映像。可建置的映像以 `switch_board.py --help` 的列表為準。

## 傳到板子並先做短測

把 `v32_ga_tuned_20261119` 放到 `/root/114C75007/vek280/AIE/`，沿用同一目錄下已有的前置套件、原始測資和 `g_a.3` 快取。

```sh
cd /root/114C75007/vek280/AIE/v32_ga_tuned_20261119
python3 -B run_board.py check
python3 -B run_board.py detect
```

板上若仍是 11/18 的映像，先試新版主機可以直接建置 `dual3`。其他映像以同樣方式建置對應名稱。建置之後看到 `BUILD_READY_GA_TUNED` 才開始測試。

```sh
sh build_board.sh dual3
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
python3 -B run_board.py suite smoke --input sd
```

要切換映像，以下以 `ctpt` 為例。要測 `splitbo` 或 `tuned` 時換成對應名稱。

```sh
sh build_board.sh ctpt
python3 -B switch_board.py ctpt check
```

`CHECK_ONLY` 後執行 `python3 -B switch_board.py ctpt arm`。看到 `ARMED_ONLY` 後，保持序列埠終端開著，在板子執行 `sync && reboot`。回到同一資料夾後執行 `python3 -B run_board.py detect` 並確認映像名稱，再跑短測。重新連線時需要重新設定 `V32_GA3_CACHE`。

## 全量與單層測試

```sh
python3 -B run_board.py suite full --input sd
python3 -B run_board.py run ga9 full --input sd --no-prefetch
```

`suite` 會依序執行目前映像支援的所有層。`--no-prefetch` 只關閉輸入預讀，`fast` 的明文 NTT 和 BO 排程仍啟用。`--profile baseline` 關閉本輪的主機優化，分別使用各層原有的排程。`g_a.6／.9` 的短測預設使用少量分片，預讀開關的效能對照用 `full`。

| 層 | 完整 SHA-256 驗證的輸出字 | 前一版主流程上限（s） |
| --- | ---: | ---: |
| `g_a.0` | 1,434,451,968 | 54.258264759 |
| `g_a.3` | 1,333,788,672 | 31.366680443 |
| `g_a.6` | 616,562,688 | 15.346888682 |
| `g_a.9` | 424,673,280 | 10.585808570 |

`resident_seconds` 包含 BO 準備、同步、PL 開始到主機觀察完成、回讀及 SHA-256。`g_a.0` 的 NTT 另列。`request_seconds` 包含輸入讀取和驗證。重疊的工作以整個視窗的實際耗時為準。`meets_previous_resident_limit` 只在 `full` 回報。`suite full` 另列 `resident_limit_result` 和超時的層，輸出正確性由 `PASS_GA_FOUR_LAYER_REPLAY` 或 `PASS_GA_BOOT_REPLAY` 表示。

若要比較網路讀取，Windows 發送程式和說明位於既有 `v32_ga_all_20261117` 套件。可以先用 `transport/probe_board.py ga9 --input sd --parts 32` 和 `--input net --parts 32` 比較同一批資料。確認網路設定後，新套件的測試可用 `--input net`。量 PL 路徑的對照保留相同資料來源和主機設定。

## 收集結果

`PASS_GA_BOOT_REPLAY` 表示專用映像支援的層都完成。`PASS_GA_FOUR_LAYER_REPLAY` 表示四層都完成。可一次收集多個開機的紀錄。把範例替換成實際 `CAMPAIGN=` 路徑，再下載 `DOWNLOAD=` 指向的壓縮檔。

```sh
python3 -B run_board.py collect --campaign campaigns/第一個實際檔名.json --campaign campaigns/第二個實際檔名.json
```
