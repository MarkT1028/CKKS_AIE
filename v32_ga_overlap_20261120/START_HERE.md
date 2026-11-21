# VEK280 四層純 PL 重播

本套件使用 `v32_ga_tuned_20261119` 的已驗證映像和原測資。四層依序獨立重播 `g_a.0` 的密文乘明文，以及 `g_a.3/.6/.9` 的密文乘加。每個輸出都與原始 SHA-256 比對。各層之間沿用各自擷取的真實輸入，四個重播時間可以加總描述這批工作。模型其他算子與前層輸出餵給後層的即時推論需要另外量測。

## 第一次上板

從遠端 Windows 的 Git 工作目錄將整個 `v32_ga_overlap_20261120` 資料夾傳到板子 `/root/114C75007/vek280/AIE/`。先確認前一輪的映像仍在使用。

```sh
cd /root/114C75007/vek280/AIE/v32_ga_overlap_20261120
python3 -B run_board.py detect
```

當 `image=tuned`、`matching=true` 且 UUID 是 `6cc21e10b0805092bc88f9000f5a6d4f`，沿用這次開機。建置會同時檢查套件與相依檔的 SHA-256。板子需要原本的四套測資和 G3 pilot 快取。

```sh
export V32_GA3_CACHE=/root/114C75007/vek280/AIE/v32_ga3_compact_cache_pilot
sh build_board.sh tuned && python3 -B run_board.py suite smoke --input sd
```

四層短測出現 `PASS_GA_FOUR_LAYER_REPLAY` 後，第一次長測使用跟 11/20 相同的 SD、pilot 快取、fast 與預讀設定。

```sh
python3 -B run_board.py suite full --input sd && python3 -B run_board.py collect --latest
```

下載 `DOWNLOAD=` 指向的壓縮檔。`collect --latest` 會找本套件時間最新且四層全部成功的完整 campaign。若要取指定輪次，使用 `collect --campaign` 加上那輪實際的 `CAMPAIGN=` 路徑。

## 變更與判讀

| 層 | 本輪變更 | 排除輸入讀取的比較上限 | 11/20 四層同輪含讀取 request |
| --- | --- | ---: | ---: |
| G0 | 1,024 個係數為一塊處理短跨距 NTT，權重按切片讀取並驗證，逐片交給主流程。三組 BO 讓下一塊明文打包、目前 PL 工作、上一塊回讀及驗證可重疊 | 43.189360 s | 443.117109 s |
| G3 | 三組輸出 BO 與獨立參數，跨相同 RNS tower 的視窗重用參數與 XRT 綁定，保留原始兩路輸出雜湊 | 31.366680 s | 1469.230160 s |
| G6 | 三組輸出 BO。保留已驗證分片的唯讀區段並直接複製到映射的 BO，省去中間的大向量複製。SD 分段讀取時同步更新 SHA | 15.346889 s | 842.040963 s |
| G9 | 同 G6，逐一檢查橫跨分片的字與 RNS 範圍，保留預讀與可獨立重測的關閉開關 | 10.570750 s | 644.673668 s |

`resident_seconds` 包含 BO 準備、同步、啟動 PL、取回結果及完整驗證。G0 的 ARM NTT 另列於 `arm_ntt_seconds`。若要把這一步算進排除 SD 的口徑，請看 G0 的 `preloaded_including_ntt_seconds`，11/20 同輪是 330.368596 秒。`request_seconds` 包含輸入供料、驗證及本層重播。讀檔、NTT、準備下一塊和執行上一塊可同時進行，請依 request 牆鐘計算總耗時。`execute_ms` 量的是主機發出啟動到觀察到完成的間隔。

全量報告的 `resident_limit_result` 和 `sd_request_limit_result` 各自逐層比較；任一層超過參考時間就列在該欄。主流程參考取先前已量得的較短時間，G9 含 11/20 關閉預讀的 10.570750 秒。SD request 參考固定採 11/20 四層同輪數值。更換快取的 request 只反映新配置。網路測試只呈現實測時間，不套用 SD request 判定。微小差異可用舊、新、新、舊的順序重測有差異的層，再比較中位數。

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
