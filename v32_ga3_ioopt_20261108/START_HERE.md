# g_a.3 讀取與完整輸出核對候選 — 2026-11-08

本包供下一輪板上篩選。**板上效能 PENDING**。沿用雙 AIE／原生純 PL 的既有映像、兩路、225 MHz 與完整 N=131072、L=53、K=16、64 組 raw MAC 資料，不需重新上傳 43 GiB 測資。

本輪上一包 archive 的 SHA256 為 `98bbfeccf738bcac7a9b8985966c72cae9596db522dd9bbf55a196f2d53c4f6f`。先前 cacheable 短測只改善約 2.15%，CPU 跨測試跨度約 8%，尚無正式穩定加速結論；載入中 pread 約占 97.6%。

## 三個 profile

三者都沿用已在板上成功配置的 cacheable BO、同一 ARM64 打包與兩份硬體，沒有增加管線或 AIE。

| profile | 輸入讀取 | 輸出核對 |
|---|---|---|
| `legacy` | 上一包 cacheable 的原讀取方式 | 讀 gold，完整逐字比對 |
| `sequential` | 顯式 header read、sequential hint、4 MiB read | 讀 gold，完整逐字比對 |
| `sha256` | 同 sequential，保留全部輸入／權重與範圍檢查 | 所有 canonical 輸出 bytes 以 SHA256 對照封存答案 digest，不讀 gold payload |

`legacy_source/common/` 保留上一輪被測 cacheable 來源位元組。三者保留相同逐檔 `POSIX_FADV_DONTNEED`，不因更換全域快取或系統設定製造差異。

SHA256 是另一種明確標示的完整輸出驗證協定，**不是逐字讀 gold 比對**。CPU 與硬體使用相同協定；輸出仍完整物化，包含 header、模數、所有三分量與每個 word，且每次 trial 都重新雜湊。摘要會檢查 digest 次數／bytes，不能用少驗證的結果冒充通過。

完整資料的 gold payload 約 9.94 GiB，占全部讀取 payload 約 23.08%。省讀取量不代表已達相同百分比的加速，也沒有改變乘加核心執行週期。短版 16 視窗的省讀比例約 11.11%。

## 上傳

只上傳這個小資料夾 `v32_ga3_ioopt_20261108`。資料預設讀取：

`/root/114C75007/vek280/AIE/v32_ga3_20261104_data`

保留舊套件與結果。新版不會改開機檔、原測資、CPU 時脈、全域快取或自動重開機。

## 板子 Linux：每行分開執行

```sh
cd /root/114C75007/vek280/AIE/v32_ga3_ioopt_20261108
sh check_package.sh
sh build_board.sh
python3 ga3_board.py detect
sh run_screen.sh
python3 collect_results.py
```

目前若偵測到 `v32_core_2_pipe` 就直接測雙 AIE，不需切換映像。純 PL 也使用同一套件；後續仍要相同 profile／順序與 AIE→PL→AIE 回測。

`build_board.sh` 會做記憶體自測，編譯三種 profile × 兩個後端並執行 `--crypto-check`。SHA256 使用板上既有 OpenSSL 的公開 EVP API，不需安裝開發標頭或額外 library。若顯示 `UNSUPPORTED_SHA256_CANDIDATE`，screen 明確略過 SHA256，仍測 legacy／sequential，不偷偷改用其他驗證方式。

## 短版 screen 做什麼

1. 三種可用 profile 的首尾 smoke。
2. `legacy → sequential → sha256 → legacy` 的同一組 16 視窗 **pilot**。SHA256 不支援則略過該候選。
3. 每個 pilot 視窗一次硬體執行、完整輸出核對；請求時間包含讀檔與驗證，無 CPU 錨點和額外暖機。這用來篩選讀取／驗證成本，不宣稱 CPU 加速比。
4. 16 視窗涵蓋四批 RNS、首尾係數與輸出 0／15，共 20,840,448 個 word。**不是完整係數覆蓋或完整 g_a.3 延遲。**

下載最後列出的 **`collected_ga3_ioopt_*.tar.gz`**。先回傳短測，再決定是否值得跑完整版本。

需要 CPU 前後錨點的補測仍可用：

```sh
sh run_board.sh probe sequential ascending
sh run_board.sh probe sha256 ascending
```

這兩行不是第一輪 screen 的必要指令。Probe 含 CPU／硬體／CPU、各暖機 1 次及正式 3 次，其 campaign 時間是整個測試活動的時間。

## 確認候選後的完整測試

以 SHA256 為例，待確認板上支援與短版結果後：

```sh
sh run_round.sh sha256
python3 collect_results.py
```

完整 round 包含 smoke、windows 降序／升序、stream 與 export。全部正式覆蓋仍是 1024 視窗、4096 作業、1,333,788,672 個輸出 word。

Export 重用同次完整輸出核對後的 digest，仍保留每個作業的 digest 與首尾 8 份實際輸出。收集器會再核對這些 bytes，後續原上下文驗證仍需回傳後進行。

## 結果判讀

- `campaign_wall_ms`：pilot／stream 是包含載入與完整驗證的單次請求；windows／probe 含 CPU 對照及重複試驗，不當作整層單次延遲。
- `resident_window_median_sum_hardware_ms`：不含 admission；包含打包、同步、硬體啟動等待、合併及該 profile 的驗證工作。
- `verification_protocol`：`FULL_CANONICAL_WORD_COMPARE` 或 `FULL_CANONICAL_SHA256`。兩者的成本要分開解釋。
- `admission.csv`：逐視窗載入時間；`admission_profile.json`：read 次數、payload bytes、範圍／身分檢查與 hash 覆蓋。
- 未確認 hash capability 的失敗在硬體啟動前發生；真正執行中失敗則保留 `RECOVERY_REQUIRED.json`，依提示重開機，不自行清除標記。

這仍是原 g_a.3 的 raw MAC 重播。Rotation、im2col、relinearization、activation 和完整即時 v32 傳輸仍在原後端；不能與歷史 CUDA 約 25.66 秒直接相除作為正式效能比較。

官方依據：

- https://man7.org/linux/man-pages/man2/pread.2.html
- https://man7.org/linux/man-pages/man2/posix_fadvise.2.html
- https://docs.openssl.org/3.0/man3/EVP_DigestInit/
- https://xilinx.github.io/XRT/2024.1/html/xrt_native_apis.html

