# G5 完整密文短測的分項計時

將此資料夾放在板子 `/root/114C75007/vek280/AIE/`，與 `v32_ga_activation_20261121` 並排。使用已建置的 tuned 板端程式和已重組的 `v32_ga_activation_20261121/ga5_full_ct0`。

```sh
cd /root/114C75007/vek280/AIE
python3 -B ga5_ct0_bench_20261122/bench.py
```

預設依序測 `stream → tiles → tiles → stream`。兩種方法都依序核對每個輸入和輸出 tile 的 SHA-256，檢查固定測資、協定、字數和座標。Stream 額外重算完整輸入和回傳串流的 SHA-256。預設只保存小型 JSON，不寫出 465 MiB 的回傳檔。

若要把寫檔另外量一次，使用 `--mode export`。此模式保留完整串流 SHA-256，另計輸出寫入和刷新到系統緩衝的時間，並保留 `actual.bin`。先送回 `GA5_BENCH_RESULT=` 的 JSON，再依需要收集實際回傳檔。

`replay_excluding_file_read_seconds` 從同輪請求牆鐘扣除輸入讀檔，仍含管線傳輸和雜湊。板端接收及 MAC 時間涵蓋於傳輸與等待，分項不要相加。第一支完整密文的結果可用來選 G5 整層測試的驗證配置，完整 16 支的即時 OpenFHE 續算另量。
