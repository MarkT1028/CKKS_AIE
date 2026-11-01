本次實作依據與版本

- AMD/Xilinx XRT Native APIs：https://xilinx.github.io/XRT/2025.2/html/xrt_native_apis.html 。這個2025.2路徑目前頁首顯示Master，不能單憑URL當作版本鎖定；實際API相容性以本機保存的headers語法檢查和板上安裝版本建置為準。直接對BO map指標寫入後，仍執行TO_DEVICE同步；輸出在FROM_DEVICE同步後才讀取。延續已板測的BO group_id、2-bank、單一graph、status先於下一次start，不引入新版experimental queue API。
- 官方XRT headers的語法檢查使用既有實驗提供的host_api_headers；板上建置仍使用板上/usr/include/xrt與xrt_coreutil，並保存實際ARM binary SHA及編譯器版本。不能把header語法檢查稱為新板測成功。
- Linux man-pages專案 mmap(2)：https://man7.org/linux/man-pages/man2/mmap.2.html 。採PROT_READ/MAP_PRIVATE、offset0；映射並不代表預先讀完或複製到heap。呼叫端必須保持底層資料檔不可變。用RAII釋放mapping/fd，使用memcpy讀取uint64而不依賴C++17對映射位元組的typed-object lifetime假設。
- Linux6.12 /proc：https://docs.kernel.org/6.12/filesystems/proc.html 。rchar與實體read_bytes不同；mmap缺頁不會表現成等量read()的rchar。記錄read_bytes、缺頁及RSS/anonymous/file/HWM，不能用小heap大小宣稱小總RSS，也不能把重疊階段的work加總當wall。
- Linux6.12記憶體概念：https://docs.kernel.org/6.12/admin-guide/mm/concepts.html 。CmaFree不是配置成功或失敗保證，沿用前版MemAvailable/CmaTotal檢查，以真正XRT BO配置結果決定是否繼續。不清除全域cache、不mlock整份測資、不變更sysctl。
- OpenFHE1.4.2原始碼：https://github.com/openfheorg/openfhe-development/tree/v1.4.2 。本次不修改OpenFHE演算法或使用1.6.1新增API，原context驗收沿用已編譯並固定1.4.2的native bridge，包含levels/depth normalization、metadata、relin與FLEXIBLEAUTO續算的既有驗收。

限制：現有CPU對照是板上2-thread raw u128 MAC與同樣的mapped來源/驗證；不是原v32整層OpenFHE效能上限。新板上速度仍PENDING；完整大專案與跨機推論網路不在本輪範圍。
