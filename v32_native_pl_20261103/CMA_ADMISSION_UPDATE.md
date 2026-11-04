# 2026-11-01 記憶體檢查修正

原程式、測資、CPU self-test與UUID均已由使用者上板確認通過。該次CmaFree=125652KiB，套件原本以160MiB當硬門檻，會過早拒絕測試。

新版保留MemAvailable>=1800MiB及CmaTotal>=160MiB的檢查，CmaFree改成記錄值；由既有XRT BO的實際配置結果決定是否通過。沒有自行清除page cache、改sysctl、換映像、重新開機或略過實際BO配置錯誤。不能從單一meminfo判定哪些頁面可以回收，也不保證配置成功。

兩組bank、兩條lane原本的BO payload按4KiB頁面估算為117.265625MiB，不含driver/runtime其他用量；160MiB原門檻不等於實際需求，也不等於真正可連續分配量。真正配置在硬體程式的setup階段，配置失敗仍中止並保留log與memory snapshot。

新套件名稱v32_full_hs4_20261101。沿用同層既有v32_full_hs4_20261031_data和v32_hs4_20261027，測資不需再傳，UUID仍為050ea5cc23fb5038bad0aca23cbd240b。

上傳此新版資料夾到板子的AIE目錄，執行：

```sh
cd /root/114C75007/vek280/AIE/v32_full_hs4_20261101
sh check_package.sh
sh build_board.sh
python3 full_board.py detect
sh run_board.sh smoke
```

smoke通過後，仍使用原formal、formal --reverse和collect流程。

Linux6.12對page cache、reclaim、compaction的官方說明：
https://docs.kernel.org/6.12/admin-guide/mm/concepts.html

本修正僅改善測試前置判斷，沒有新的硬體效能提升或上板通過聲明。
