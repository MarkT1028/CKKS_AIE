# g_a 即時純 PL 乘加板端套件

把本目錄放到板子的 `/root/114C75007/vek280/AIE`，與 `v32_ga3_splitbo_20261109` 同層。使用既有 `v32_native_splitbo_2_pipe` 映像，UUID `9bee253b8f345f39bd9c18d612897ce3`。兩路 PL 共用每個 RNS／係數區塊的輸入，並透過 SSH 的標準輸入、輸出接收密文 residue 與回傳計算結果。

在板端執行：

```sh
cd /root/114C75007/vek280/AIE/v32_ga_live_20261111
sh build_board.sh && python3 -B smoke_server.py
```

預期結尾為 `PASS_GA_SERVER_SMOKE backend=pure_pl tiles=24 slots=6`。這會在兩路 PL 上逐項比對 24 個小區塊，檢查六個權重槽、輸出順序和短 RNS 區塊。通過後回到執行 v32 的主機啟動整段測試。

板端服務會在每次連線內配置七個輸入 BO、兩個輸出 BO 與兩份參數 BO，估計頁面取整約 227 MiB，驅動額外開銷依實際配置。輸入和回傳值透過連線傳送，板上儲存套件、編譯檔和執行狀態。`serve_board.sh` 由主機程式透過 SSH 啟動。

板端 smoke 若出現錯誤，請保留完整終端輸出。若服務在 PL 執行中中斷，先依 recovery 訊息復原板子，再繼續測試。
