# 真實 v32：mapped BO 與雙緩衝比較（待板測）

本套件 `v32_bo_20261029` 只修改主機資料路徑與測量方式，沿用目前的 `v32_diag_2_pipe` 雙 AIE 映像。**本機功能檢查已通過；新版板上速度尚未測量。** 這是一個已擷取的真實 v32 `h_s.4` 運算群組重播，並非整個模型的即時推論。

## 1. 要上傳什麼

將 **整個 `v32_bo_20261029` 資料夾** 上傳至：

```text
/root/114C75007/vek280/AIE/v32_bo_20261029
```

旁邊要保留先前的 `v32_hs4_20261027`，此處重用其真實輸入、預期輸出及 xclbin，不再複製約 896 MiB 輸入。毋須上傳本機開發目錄 `integration` 或其他舊實驗。

```text
AIE/
├── v32_hs4_20261027/       # 原封不動保留
│   ├── fixture/
│   └── variants/v32_diag_2_pipe/
└── v32_bo_20261029/       # 這次新增的完整小套件
```

若舊套件放在不同位置，請先設定絕對路徑：

```sh
export V32_BASE_PACKAGE=/root/114C75007/vek280/AIE/v32_hs4_20261027
```

## 2. 三組測試改了什麼

| 版本 | 資料路徑 | BO 組數 | 下一塊準備 |
|---|---|---:|---|
| `copy_serial` | 拆路 → 主機 lane buffer → BO.write；BO.read → 主機 buffer → 合併 | 1 | 前一塊完成後才開始 |
| `map_serial` | 直接拆路至 mapped input BO；同步後直接從 mapped output BO 合併 | 1 | 前一塊完成後才開始 |
| `map_pingpong` | 與 `map_serial` 相同 | 2 | 持續準備執行緒在另一組 BO 準備下一塊，與當前 XRT run/wait 重疊 |

直接 BO 版本移除每路的中介輸入／輸出向量及其 BO.write/BO.read 複製。**仍保留必要的 BO.sync、輸出填毒、參數更新、完整回讀與驗證。** 這不等同完全免搬移的 zero-copy。

雙緩衝只重疊「下一塊輸入拆路、參數與資料同步、輸出填毒」。每塊仍先等 reader、reducer 與 graph 全部完成，再回讀、合併、驗證，之後才啟動下一塊；不會同時啟動兩個 graph，也尚未把回讀與下一輪運算重疊。

```text
copy_serial / map_serial:
準備0 → 執行0 → 回讀驗證0 → 準備1 → 執行1 → 回讀驗證1 → …

map_pingpong（示意；實際是否重疊由板測判斷）:
主執行緒：準備0 → [執行0] → 回讀驗證0 → [執行1] → 回讀驗證1 → …
準備執行緒：       準備1（BO-B）           準備2（BO-A）         → …
```

BO-A 與 BO-B 各有兩路獨立 input/output/parameter BO，持續保留至相應 run 完成。只有回讀與完整驗證結束後才能重用同一組。單／雙組 BO 的有效資料約 58.625／117.25 MiB（另加少量參數與配置對齊）；普通主機快取約 938 MiB。執行前檢查 `MemAvailable >= 1600 MiB`、`CmaFree >= 160 MiB`，記憶體不足會先停止。

## 3. 依序執行（不要同時開兩個測試）

```sh
cd /root/114C75007/vek280/AIE/v32_bo_20261029
sh check_package.sh
sh build_board.sh
python3 board_runner.py detect
```

預期前兩步出現 `PASS_BO_OVERLAY` 與 `BUILD_READY`。建置會執行未改動 CPU 自測、小型合成資料的主機排程自測，以及完整 16 塊真實資料的新舊拆路／合併比對；這些都不執行 PL/AIE。

`detect` 應顯示：

```text
boot_uuid: 6719127d5f785a7fa4fab0a9869d6ccd
matching_variants: ["v32_diag_2_pipe"]
```

若符合，沿用目前映像，不需重新開機。若不符合，先回報 detect 結果；本套件不含韌體切換工具。

先完成 smoke，再分別執行兩次正式測試：

```sh
sh run_board.sh smoke
sh run_board.sh formal
sh run_board.sh formal --reverse
python3 collect_results.py
```

每個指令結束並顯示成功後，才執行下一個。任何 `FAIL` 都先停止後續測試，保留該資料夾回傳。

- smoke：每版 1 次測量、0 次暖機，另加 1 次輸出匯出重播；CPU 前／後各 1 次。
- formal：每版 1 次暖機、5 次測量，另加 1 次輸出匯出重播；CPU 前／後各 1 次暖機、3 次測量。
- `--reverse`：三版執行順序相反；保留獨立資料夾，不覆蓋第一次。
- 所有 CPU 使用同一份未改動的快取版、兩個持續工作執行緒；每版硬體前後各測一次，以觀察 CPU 漂移。

不會改 CPU governor、頻率、開機分割區或 BOOT.BIN。正常 runtime graph reset 與錯誤時 abort/reset 僅清理執行狀態。共用舊套件 `.board.lock`，避免與其他重播同時使用硬體。測試時請勿另開其他效能實驗。

`read_register` 若出現與之前相同的 deprecated 警告，僅代表原狀態檢查 API 的編譯警告；以編譯結束及 `BUILD_READY` 為準。新程式沿用原寄存器檢查，沒有更換 kernel ABI。

## 4. 如何判斷有沒有更快

**主要指標是 `replay_wall_ms`：第一塊準備開始，到第 16 塊合併與全量驗證完成的實際經過時間。** 三版皆含必要同步、填毒、回讀及所有 5,505,024 個 residue 的整數比較。

| 紀錄 | 意義 |
|---|---|
| `replay_wall_ms` | 同一輪實際經過時間；判斷優化效果的主要指標 |
| `execute_sum_ms` | 16 塊主機觀察到的 XRT run/wait 加總；不是純 AIE cycle |
| `*_sum_ms`、`stage_work_sum_ms` | 各階段工作耗時加總；雙緩衝會重疊，不能當整輪延遲相加 |
| `*_during_other_execute_ms` | 下一塊準備與別塊 run/wait 的主機時間區間交集；不證明硬體 DMA 真的並行 |
| `setup.json` | 普通主機資料載入、XRT 初始化、BO 與執行緒建置，另列、不藏入測量 |
| `export_only=1` | 獨立重播、完整驗證並保存 16 份硬體輸出；保留其所有時間但不列入穩態中位數 |
| `*.command.json` | 含程序啟動、setup、暖機、正式與輸出匯出的整個子程序時間 |

本次三版都不在測量輪中寫輸出檔，統一在獨立匯出輪存檔。CPU 也採快取、兩執行緒、每輪全量驗證、不存輸出；CPU 原程式仍有少量 CSV 記錄開銷，未宣稱最優 CPU 實作。

**`copy_serial` 是共用新版排程與計時的對照組，並非逐位元不變的舊版主程式。** 上一輪約 1304 ms 的交易加總與本次實際 replay wall、存檔方式不同，因此不能直接把跨版本數字相減當作本次加速。先比較本次三版，並同時看前後 CPU 漂移、兩次正式輪次及所有樣本。

自動分析會驗證每輪／每塊／每路 span 完整性、BO 交替與重用時機、時間加總、輸出一致性、匯出排除與 CPU 數量，產出 `comparison.json` 和 `comparison.txt`。不會因候選較慢而丟棄該版本。

## 5. 回傳哪個檔案

`collect_results.py` 會收集所有 `results_bo_*`、16 塊 × 3 版 × 各次測試的輸出、CSV、時間線、環境、二進位身分與套件依據，不包含龐大輸入或任何金鑰。

預設使用 **gzip level 1**，會顯示 `INDEX`、`PACK`、`VERIFY` 進度；完成後重新讀取壓縮檔，逐項核對 SHA-256。請下載並回傳最後顯示的：

```text
collected_bo_日期時間.tar.gz
```

若特別需要 xz，可用 `python3 collect_results.py --compression xz`（preset 1）；預設 gzip 主要為縮短板上打包等待，與加速器效能無關。

每版匯出檔均為完整 raw ciphertext records。收到後還需在原電腦上做原 context 回接、解密與續算確認；目前本機內測不等同候選硬體輸出已完成密碼學驗證。

## 6. 已完成的內測與限制

- 保留舊 host、CPU、快取與 parser 原始檔 SHA-256，兩個先前凍結套件保持不變。
- 完整真實 fixture：三種主機功能排程各 3 輪，48 份保存輸出逐位元符合 golden；運算由獨立主機模型完成，沒有執行 AIE。
- 原拆路與直接 BO 拆路、合併在全部真實 16 塊一致。
- ASan／UBSan：合成 N=128/256/16384、L=1/3、K=1/3，涵蓋跨 chunk 交替、保護區、長度／空指標／alias、錯誤傳遞、執行緒回收。
- 注入準備／等待失敗與錯誤輸出，必須停止並回收；不會帶錯誤繼續後續 chunk。
- 分析器與打包工具測試：缺少或重複時間區間、錯誤 BO、過早重用、錯誤加總、匯出混入、缺塊、不同輸出、危險路徑與 symlink 都會拒絕。
- XRT 使用封存官方標頭作語法檢查；最終仍由板上原環境編譯。PC 語法檢查專用 `DISABLE_ABI_CHECK` 不會帶入板上編譯旗標。
- 完成凍結套件的 ZIP 與隔離 Git 換行往返測試後才發佈。測試收據另存於開發目錄，不改凍結套件。

**尚待驗證：** 該板 XRT mapped BO 的實際快取／同步代價、另一執行緒的 BO.sync 能否與 PL/AIE 執行有效重疊、雙核心記憶體競爭是否抵銷收益。即使輸出正確，仍可能沒有更快；板測數據決定是否採用。
