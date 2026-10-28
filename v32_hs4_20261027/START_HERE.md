# 真實 v32 單組乘加：雙 AIE 上板測試

本套件的輸入來自原始 v32 完整 CKKS 推論中 `h_s.4` 的第一組 K=16 BSGS 乘加
（對角線索引 80～95），保留原本 N=131072、實際活動 RNS towers、45/51-bit 模數與 FLEXIBLEAUTO。
完整密文依 NTT 位置分塊送進兩顆 AIE，再合併成同一個原始密文。

本次實際活動 L=14，原始兩側輸入 level 為 42／43，經原版 OpenFHE 規則正規化到 level 43。
實際質數有 2 個 45-bit、11 個 46-bit、1 個 51-bit，因此保留四個 15-bit limb 來涵蓋全部值。
原始輸入 payload 共 896 MiB，完整 raw 輸出 42 MiB；一個檔案不是一個獨立小環密文。

這輪先驗證「真實運算匯出 → 板上 raw MAC → 回到原始密文上下文」。
板上測試仍待執行；離線通過不代表已取得板上加速結果。目前還沒有讓整個 v32 自動透過網路呼叫板子。

## 1. 上傳整個資料夾

請完整上傳 `v32_hs4_20261027`，包括 `fixture/`、`variants/`、`host/`、`cpu/` 及全部腳本。
真實密文資料比之前的小型測資大很多；不要只傳腳本。私鑰與 OpenFHE 私有狀態不在此套件中。

假設上傳到 `/root/114C75007/vek280/AIE/v32_hs4_20261027`，依序執行：

```sh
cd /root/114C75007/vek280/AIE/v32_hs4_20261027
sh check_package.sh
sh build_board.sh
python3 board_runner.py detect
```

`BUILD_READY` 表示編譯、CPU 自測與全部分塊的格式／拆合檢查通過，尚未執行 PL/AIE。
XRT `read_register` 的 deprecated 警告沿用之前已上板驗證的狀態讀取方式；真正的編譯錯誤會中止腳本。

## 2. 切換到支援 v32 模數的新映像

之前的 `diag_2_pipe` 只接受至少 48-bit 的模數，不能直接跑這份 45-bit 輸入。
請先執行唯讀檢查：

```sh
sh switch_fair_board.sh v32_diag_2_pipe check
```

檢查成功後，再依序執行：

```sh
sh switch_fair_board.sh v32_diag_2_pipe arm
sync && reboot
```

`arm` 會備份並更新 slot 1，保留既有 BOOT.BIN 與 slot 2；最後一行才會重新開機。
若重開機前要取消，使用 `sh prepare_variant_srst.sh --cancel`。
套件也保留先前 `diag_2_pipe`、`raw_2_pipe` 映像供同一個切換腳本回復。

重開機後，若有線 IP 遺失，可在板子序列終端執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

## 3. 確認映像，再測試

```sh
cd /root/114C75007/vek280/AIE/v32_hs4_20261027
python3 board_runner.py detect
```

確認 `matching_variants` 是 `v32_diag_2_pipe`。接著每個指令跑完再執行下一個：

```sh
sh run_board.sh smoke
sh run_board.sh formal
python3 collect_results.py
```

- `smoke`：完整真實 MAC 回放 1 次，所有分塊都驗證；沒有 warmup。
- `formal`：硬體先 warmup 1 次，再量測 5 次完整 MAC；另以前後各 3 次量測、1 次 warmup 的雙執行緒 ARM raw-MAC 參考觀察 CPU 漂移。
- `collect_results.py`：產生 `collected_real_v32_時間.tar.xz`，列出檔案路徑、大小與 SHA256。

請將最後產生的整個 `.tar.xz` 給我。收到後才會對這批**實際板上輸出**做原始上下文的重建、relinearization、解密與續算驗證。

## 4. 如何看時間

- `execution_sum_ms`：各分塊 PL/AIE 主流程時間加總。
- `transaction_sum_ms`：含板上資料載入、BO 準備／傳輸、主流程、讀回與整數驗證。
- `full_replay_ms`：板上完整回放經過時間；最後一輪包含輸出存檔，逐塊 CSV 另列 `output_save_ms`。
- 以上都不含 PC 匯出、PC↔板子網路、PC 匯入、relinearization 或其餘 v32 層。
- ARM CPU 參考是相同 raw modular MAC 的 U128 實作，並非完整 OpenFHE 推論，也不代表最佳 CPU 實作。

請勿把先前 N=8192、L=3 的約 10.94 ms 當成這次完整 N=131072 密文的耗時；工作量不同。
每次執行會建立獨立結果資料夾，完整保存分項時間、CPU 環境與最後一次所有硬體輸出。

## 5. 這輪已完成的離線檢查

詳見 `OFFLINE_VERIFICATION.json` 與 `offline_evidence/`。包括整份實際操作數的 C 模型、
完整整數密文／metadata、解密與平方續算、原版 Python 後端回讀，以及 HLS、RTL、AIE 模擬和 routed timing。
AIE x86 模擬涵蓋所有 16 對的原始 NTT 端點；較慢的 AIE 硬體模擬使用首／末兩對、完整活動 tower 與兩端位置。
完整運算的所有 NTT 位置與全部 16 對則由整份 C 模型與精確整數檢查覆蓋。
新映像的 routed 資源為 35,292 LUT、334 DSP、24 RAMB36 + 2 RAMB18（25 個 BRAM tile）；
setup slack 0.359 ns、hold slack 0.013 ns，DRC 與繞線錯誤均為 0。
