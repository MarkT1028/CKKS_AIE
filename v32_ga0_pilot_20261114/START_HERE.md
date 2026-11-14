# g_a.0 純 PL 密文乘明文短測

由原 v32 的 `input_64x64.png`、模型 checkpoint 與 CKKS 參數產生。
選取第 0、15 個輸出，各保留其 64 個卷積對角，分成四組 K=16 的乘加。
對第 0 個輸出取首端 128 個係數，對第 15 個輸出取尾端 128 個係數。
兩端皆涵蓋全部 57 個 RNS 模數。板上逐字比對 OpenFHE 的兩個乘積分量，並檢查第三分量為零。
短測共有 32 個硬體區塊、175,104 個輸出字。套件約 30 MiB。

將本資料夾上傳到 `/root/114C75007/vek280/AIE/`，和 `v32_ga_live_20261111`、
`v32_ga3_splitbo_20261109` 同層。沿用 `v32_native_splitbo_2_pipe` 的啟動映像
與既有板端服務。啟動 UUID 為 `9bee253b8f345f39bd9c18d612897ce3`。
板端服務已有 `BUILD_READY_GA_LIVE` 時可直接執行。

```sh
cd /root/114C75007/vek280/AIE/v32_ga0_pilot_20261114
python3 -B run_board.py
```

如果尚未編譯過板端服務，可先執行 `sh ../v32_ga_live_20261111/build_board.sh`。
短測通過會印出 `PASS_GA0_CTPT_PILOT`，請傳回 `ga0_pilot_result.json`。
`sample_resident_seconds` 是已載入樣本的重播時間，涵蓋主機管線、
BO 搬移、PL 運算、取回及驗證。整層速度要等完整測資測試。
