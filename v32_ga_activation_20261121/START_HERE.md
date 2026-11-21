# VEK280 卷積比較與 G5 啟動測試

本套件使用 `v32_ga_tuned_20261119` 的已驗證映像和原測資。四層依序獨立重播 `g_a.0` 的密文乘明文，以及 `g_a.3/.6/.9` 的密文乘加。每個輸出都與原始 SHA-256 比對。各層之間沿用各自擷取的真實輸入，四個重播時間可以加總描述這批工作。模型其他算子與前層輸出餵給後層的即時推論需要另外量測。

G5 是獨立的啟動測試。板端接受原始 `g_a.3` 輸出衍生的殘值，使用同一個 PL MAC 算平方、線性乘積、二次項乘積。三個運算分開送入，讓地端 OpenFHE 能依原始順序重線性化並對齊層級。內附的 pilot 涵蓋 16 支密文，每支密文、每個運算各用首尾 RNS／係數區段，合計 96 tiles、36,864 個回傳字。

## 第一次上板

從遠端 Windows 的 Git 工作目錄將整個 `v32_ga_activation_20261121` 資料夾傳到板子 `/root/114C75007/vek280/AIE/`。先確認前一輪的映像仍在使用。

```sh
cd /root/114C75007/vek280/AIE/v32_ga_activation_20261121
python3 -B run_board.py detect
```

當 `image=tuned`、`matching=true` 且 UUID 是 `6cc21e10b0805092bc88f9000f5a6d4f`，沿用這次開機。建置會同時檢查套件與相依檔的 SHA-256。板子需要原本的四套測資和 G3 pilot 快取。

```sh
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
sh build_board.sh tuned && python3 -B run_board.py suite smoke --input sd
```

四層短測出現 `PASS_GA_FOUR_LAYER_REPLAY` 後，執行 G5 的實際 PL 重播。請保留 `RESULTS=` 下的 `summary.json` 和 `actual.bin`，地端會用後者重建並核對 CKKS 輸出。預設 pilot 的其餘係數由本機原始參考補齊。

```sh
python3 -B ga5/replay.py replay
python3 -B run_board.py collect --ga5-latest
```

先比較短測設定，再跑選定設定的四層長測。短測保留相同預讀與完整輸出雜湊，兩組／三組的選項只切換 BO 及排程。每次 `compare-banks` 執行同一段的 2、3、3、2。頭、尾兩段的 RNS 長度不同，合併判讀前先看各段的結果。

```sh
python3 -B run_board.py compare-banks ga6
python3 -B run_board.py compare-banks ga6 --segment pilot-tail
python3 -B run_board.py compare-banks ga9
python3 -B run_board.py compare-banks ga9 --segment pilot-tail
python3 -B run_board.py study-ntt
```

每筆比較產生 `STUDY=` 檔案。有穩定優勢時才會提供 `candidate`。G0 的 `study-ntt` 量 512、1,024、2,048 係數分塊，各兩輪。1,024 是預設值。兩組 BO 或不同 NTT 分塊可先用單層正式測試確認。

```sh
python3 -B run_board.py run ga6 full --input sd --banks 2
python3 -B run_board.py run ga0 full --input sd --ntt-block 1024
```

四層正式測試的預設值維持前版三組 BO 與 pilot 快取，便於和 11/21 比較。可以為 G6、G9 指定同一個 `--banks`，或分別用單層的最優設定測試。

```sh
python3 -B run_board.py suite full --input sd && python3 -B run_board.py collect --latest
```

下載 `DOWNLOAD=` 指向的壓縮檔。`collect --latest` 會找本套件時間最新且四層全部成功的完整 campaign。若要取指定輪次，使用 `collect --campaign` 加上那輪實際的 `CAMPAIGN=` 路徑。G5 和短測可以分開收集，使用 `collect --ga5` 加上 G5 的 `RESULTS=` 路徑，或 `collect --study` 加上某筆 `STUDY=` 路徑。可以重複傳入 `--study`。

## 變更與判讀

| 層 | 本輪變更 | 排除輸入讀取的比較上限 | 11/20 四層同輪含讀取 request |
| --- | --- | ---: | ---: |
| G0 | NTT 每一塊趁資料還在快取時完成最後兩級和 canonical 化，保留逐片預讀與三組 BO | 37.817386 s | 443.117109 s |
| G3 | 增加有容量上限的快取準備以及獨立選用快取，保留既有三組 BO 與參數重用 | 31.366680 s | 1469.230160 s |
| G6 | 保留唯讀分片與分段雜湊路徑，兩組／三組分開比較，另量輸出填值及同步 | 15.346889 s | 842.040963 s |
| G9 | 同 G6，維持跨分片的 RNS 範圍驗證 | 10.570750 s | 644.673668 s |

`resident_seconds` 包含 BO 準備、同步、啟動 PL、取回結果及完整驗證。G0 的 ARM NTT 另列於 `arm_ntt_seconds`。若要把這一步算進排除 SD 的口徑，請看 G0 的 `preloaded_including_ntt_seconds`，11/20 同輪是 330.368596 秒。`request_seconds` 包含輸入供料、驗證及本層重播。讀檔、NTT、準備下一塊和執行上一塊可同時進行，請依 request 牆鐘計算總耗時。`execute_ms` 量的是主機發出啟動到觀察到完成的間隔。

全量報告的 `resident_limit_result` 和 `sd_request_limit_result` 各自逐層比較。主流程參考取先前已量得的較短時間，G9 含 11/20 關閉預讀的 10.570750 秒。SD request 參考固定採 11/20 四層同輪數值，另外保留相對 11/21 `overlap` 的兩種時間差。更換快取時，request 反映當次配置。網路測試只呈現實測時間。

## 選做：G3 擴充無損快取

預設先列出計畫，加入 `--prepare` 才會建立快取。保留原始測資與現有 pilot，預設維持 10 GiB 的剩餘空間。板上若還沒有舊版 `compact_tool`，按 `v32_ga3_splitbo_20261109` 的說明建置工具後再準備。完成後保留一次性準備時間，單獨跑 G3 長測。

```sh
cache=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_4g
python3 -B run_board.py ga3-cache --cache "$cache" --budget-gib 4
python3 -B run_board.py ga3-cache --cache "$cache" --budget-gib 4 --prepare
python3 -B run_board.py run ga3 full --input sd --ga3-cache "$cache"
```

## 選做：降低 SD 讀取量

G6/G9 新增可限定容量的無損分片快取。對每 32 KiB 內的八個位元組位置分別檢查，整欄固定值只存一份。建快取時驗證原件、寫入、同步、讀回並比對 SHA。執行時還原後再次比對原 SHA。每個測試過的輸出仍逐塊驗證。未快取的分片照常從原始檔讀。

先跑普通 SD 全量，再用以下指令在同一輪開機評估 G9。預設為 32 個分片；範例限定快取 1 GiB，另留 10 GiB 可用空間。建置用時記錄在快取目錄下的 `prepare_ga9_*.json`。

```sh
cache=/root/114C75007/vek280/AIE/ga_part_cache
python3 -B transport/part_cache.py ga9 --cache "$cache" --parts 32 --budget-gib 1
python3 -B run_board.py run ga9 full --input sd --part-cache "$cache"
```

G6 的指令將 `ga9` 換成 `ga6`。兩層共用同一容量上限，若兩層各準備 32 片，可將總上限改成 2 GiB。全套使用該快取時執行 `python3 -B run_board.py suite full --input sd --part-cache "$cache"`。比較 `input_stream_bytes`（實際輸入串流長度，包含已壓縮分片）、`part_read_bytes`（原始邏輯位元組）、`part_decode_ms` 和 `request_seconds`。核心頁面快取命中仍會計入讀取。若建快取花 P 秒，每次重播省 S 秒，S 大於零時至少要重播 ceil(P/S) 次才能攤平準備成本。G3 可沿用舊套件 `compact_cache.py` 的 bounded 模式，容量充足後再評估擴大。

## 選做：比較遠端 Windows 供料

在已連到板子的遠端 Windows 使用本套件 `transport/serve_windows.ps1`，指定遠端電腦的 `-BindIPv4`、板子 `-BoardIPv4` 和 `-Ga9Root`（必須含全套 GA9 分片）。在板端設定並 export 發送端顯示的 `V32_GA_INPUT_IP`、`V32_GA_INPUT_PORT`、`V32_GA_INPUT_KEY`。測第一輪普通 SD 和建立本機分片快取均可跳過網路設定。

```sh
python3 -B transport/probe_board.py ga9 --input compare --parts 32 --output io_compare_ga9.json
```

此探測用 SD、網路、網路、SD 的順序讀取並驗證相同位元組。若網路在兩次比較中都較快，再用 `run ga9 full --input net` 量真實 request。網路探測的速度只適用於這批輸入。每層完整測試的資料根目錄必須對應該層。
