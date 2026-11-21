# G5 一支完整密文的 Git 測資

此資料夾中的 13 個分片可以一起提交及推送。它們重組為原先已驗證的第 0 支密文請求，共 192 個 tiles、60,948,480 個輸出字。所有分片和重組後的資料都會檢查 SHA-256。

遠端 Windows 拉取這個資料夾後，將整個 `ga5_full_ct0_git_20261122` 放到板子的 `/root/114C75007/vek280/AIE/v32_ga_activation_20261121/`。使用目前已建置的 tuned 套件。為分片、重組、回傳與結果打包預留約 2.5 GiB。

```sh
cd /root/114C75007/vek280/AIE/v32_ga_activation_20261121 &&
python3 -B ga5_full_ct0_git_20261122/assemble.py &&
python3 -B ga5/replay.py replay --fixture ./ga5_full_ct0 &&
python3 -B run_board.py collect --ga5-latest
```

板端通過會印出 `PASS_GA5_RAW_MAC_BOARD`。下載 `DOWNLOAD=` 指向的結果壓縮檔供地端回填。
