# VEK280 的四層 `g_a` 純 PL 板測

這個映像以兩條純 PL 管線執行 `g_a.0` 的密文乘明文，以及 `g_a.3／.6／.9` 的密文乘密文。後三層的核心用三個整數乘積重建原來的三個輸出分量。`g_a.0` 的 `fast` 會在 ARM 做明文 NTT 時預讀同一批 RNS 模數的加密權重，並合併 NTT 首尾幾輪的記憶體讀寫。四層重用原始測資、輸出順序與逐塊 SHA-256。

| 層 | 乘加組數 | 全量驗證輸出字 |
| --- | ---: | ---: |
| `g_a.0` | 64 | 1,434,451,968 |
| `g_a.3` | 64 | 1,333,788,672 |
| `g_a.6` | 32 | 616,562,688 |
| `g_a.9` | 24 | 424,673,280 |

`suite` 依序重播這四層的完整 raw MAC 工作量，四層的時間各自記錄。旋轉、啟動函數、重線性化與原模型層間交接的時間在其他流程量測。

## 傳上板子並啟動

將整個套件放到 `/root/114C75007/vek280/AIE/v32_ga_all_20261117`。`DEPENDENCY_MANIFESTS` 列出同層已部署的版本。初次建置會核對套件及依賴的 SHA-256。

```sh
cd /root/114C75007/vek280/AIE/v32_ga_all_20261117
sh build_board.sh
python3 -B switch_board.py all check
```

看到 `BUILD_READY_GA_ALL` 與 `CHECK_ONLY` 後執行 `python3 -B switch_board.py all arm`。看到 `ARMED_ONLY` 後保持序列埠連線，在板子執行 `sync && reboot`。重開機後回到同一目錄，執行 `python3 -B run_board.py detect`，確認 `matching` 為 `true`。

切回原 `g_a.0` 映像可用 `python3 -B switch_board.py ctpt check`、`python3 -B switch_board.py ctpt arm`。原共用 Split BO 映像使用 `splitbo`。切換前的檢查會核對現有槽 1 和候選映像，準備完成後由你手動重開機。

## 先用板上 SD 資料跑短測

```sh
python3 -B run_board.py suite smoke --input sd
```

四層將使用現有資料。`g_a.3` 的 SD 模式沿用原本的 `V32_GA3_CACHE` 壓縮快取與既有完整資料檢查收據。若快取位於自訂位置，使用原套件的設定。

## 遠端 Windows 串流讀取

在**能連到板子**的遠端 Windows 開啟 CMD，進入已 pull 的 `CKKS_AIE` 目錄。下例假設 PC 用 `192.168.10.95`，板子用 `192.168.10.98`。把 IP 和資料夾改成實際值。`-Ga9Root` 一個參數就能先試 `g_a.9`。四層一起跑時提供四個目錄。

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga_all_20261117\transport\serve_windows.ps1" ^
  -BindIPv4 192.168.10.95 -BoardIPv4 192.168.10.98 ^
  -Ga0Root ".\v32_ga0_full_20261114\fixture" ^
  -Ga3Root "..\v32_ga3_20261104_data" ^
  -Ga6Root ".\v32_ga6_offline_full_20261112" ^
  -Ga9Root ".\v32_ga9_offline_full_20261112"
```

`g_a.3` 若在 Windows 只有已還原的 `.tar.gz`，先在 Windows 把它解成 `v32_ga3_20261104_data` 目錄。Windows 端只提供測資檔案，PL 和驗證程式在 VEK280 執行。看到 `READY_GA_INPUT` 後保留視窗。伺服器只聽指定 IP 和連接埠，讀取範圍為這些資料夾內的輸入檔案。

在板子輸入 Windows 視窗顯示的 IP、連接埠和連線金鑰。`read` 這行會等待你貼上金鑰並按 Enter。

```sh
export V32_GA_INPUT_IP=192.168.10.95
export V32_GA_INPUT_PORT=8407
read -r V32_GA_INPUT_KEY
export V32_GA_INPUT_KEY
```

先以相同的 `g_a.9` 前 32 分片測 SD 和網路各約 1 GiB，包含完整分片 SHA-256。`verified_MiB_per_second` 為含輸入驗證的實際吞吐。傳輸失敗時可先看 Windows sender 是否就緒以及 Windows 防火牆是否允許板子連線到指定連接埠。

```sh
python3 -B transport/probe_board.py ga9 --input sd --parts 32
python3 -B transport/probe_board.py ga9 --input net --parts 32
python3 -B run_board.py run ga9 smoke --input net
```

網路模式可使用板上現有資料目錄。若只保留小型 metadata，`g_a.0` 需要 `fixture.json`、`INDEX.tsv`、`basis.txt`、`expected.txt`，`g_a.3` 需要 `SHA256SUMS_DATA`、`shape.json`、`jobs.tsv`，`.6／.9` 各需要 `manifest.json`。`g_a.3` 預設串流原始格式，每筆都重新驗原始 SHA-256，結果會列出實際傳輸量。

Windows 若已有先前建立的 `g_a.3` 無損 `.qpk` 快取，可在啟動 sender 時加 `-Ga3CacheRoot` 指定該目錄，並在板上設定 `V32_GA3_NET_CACHE_INDEX` 為同一份 `CACHE_INDEX.tsv` 的路徑。索引列出的檔案改走壓縮傳輸，其餘維持原始格式。板上核對壓縮檔雜湊，解碼後再核對原始運算元雜湊。原始與壓縮串流都可以單獨跑 `python3 -B run_board.py run ga3 smoke --input net` 對照；切回原始串流時執行 `unset V32_GA3_NET_CACHE_INDEX`。

## 一次跑四層全量

```sh
python3 -B run_board.py suite smoke --input net
python3 -B run_board.py suite full --input net
```

使用板上原資料可把 `--input net` 改成 `--input sd`。兩種來源都會報讀取或接收工作時間、預讀等待、排除檔案載入的主流程，以及整次重播的秒數。`g_a.0` 另外保留 ARM NTT。預讀的工作時間可和運算重疊，完整請求請看 `request_seconds`。

四層通過時會顯示 `PASS_GA_FOUR_LAYER_REPLAY` 和 `CAMPAIGN=`，中途有錯會留住已完成層的結果。將以下路徑換成輸出中的 `CAMPAIGN=` 路徑。完成後取回 `DOWNLOAD=` 指向的檔案。

```sh
python3 -B run_board.py collect --campaign /root/114C75007/vek280/AIE/v32_ga_all_20261117/campaigns/實際檔名.json
```
