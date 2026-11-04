# 原生整數純 PL 候選與比較邊界

套件版本標記為20261103，開發於2026年11月3日開始，最終交付檢查於11月4日完成。目標是用0顆AIE的純PL，對同一h_s.4六組raw MAC，與現有雙AIE比較完整request。

## 數值與資料路徑

資料檔保留原64-bit a0/a1/b0/b1格式；主機逐項確認0≤輸入<q，且2^44≤q<2^60。因此60-bit無號輸入相乘可精確放入120-bit結果，不用浮點或近似計算。

原版為15-bit limb、7組32-bit精確對角和及120-bit乘積重建。新reader以512-bit AXI讀取，將4個120-bit完整乘積放入480-bit串流，直接送原Barrett模數約減與三個raw密文component累加。每個乘積的中間資料由224bit變120bit；這是內部表示大小，不能當作DDR或磁碟流量下降。主機完整input BO同步仍為每輪5376MiB涵蓋範圍。

原公式保持：c0累加a0×b0，c1累加a0×b1及a1×b0，c2累加a1×b1，皆在每個RNS模數下精確計算。K、N、L與全部輸出字不變，原有relinearization、rotation及後續mean處理仍在原驗收流程。

## 硬體與代價

三版皆保留兩條完整管線、DDR0與PL225MHz。新純PL無AIE計算核心、無libadf、原生entry不建立graph物件或呼叫graph.run；boot metadata亦無AIE_METADATA與AIE_RESOURCES。Versal晶片本身仍含AIE實體區域，0指此版本使用0個AIE compute tiles。

實際routed完整bd_wrapper：新純PL34031 LUT、45402 FF、420 DSP、38RAMB36＋2RAMB18＝39BRAM36等效、URAM0。舊純PL為66979 LUT／376DSP／25BRAM36等效，雙AIE為35857 LUT／334DSP／25BRAM36等效及2AIE。新候選LUT較少，但DSP與BRAM較多，不能宣稱所有資源或功耗都改善。

新候選225MHz setup WNS+0.488ns、hold WHS+0.019ns，routing及DRC error為0；保留286個DRC warning checks。不是零warning或已量到更高Fmax。

## 已通過的離線檢查

完整實際HLS C模型處理同一真實capture的96塊、33030144字，輸出96檔逐byte/hash等於golden。小型多次呼叫與L14/L16變動形狀都通過隨機背壓RTL。另測15016個非法參數、輸出保護及獨立unsigned128餘數參考案例。

主機套件測試包含打包等價、變動輸入、錯誤注入、bank重用、ASan/UBSan/TSan、measure/export分離、三方metadata與錯誤UUID、隔離開機工具、壓縮檔去重還原與比較統計。雙AIE及舊純PL預處理後C++控制內容完全相同；CPU、來源打包與排程檔案保持byte一致。

HLS C／RTL及routed完成只代表候選可進入上板測試。沒有把模擬耗時、理想頻寬或HLS週期換算為板上加速。新實際板上輸出仍需另做原上下文解密、平方與mean回填。

## 實驗限制與記取的問題

優先做同套件的AIE前測、新純PL、AIE回測，分開boot、順序與cache policy。CPU前後漂移超過5%要保留review，不以慢CPU或最快單筆取代正式結果。正式measure-only不匯出，CPU後測完成後才另起程序重算export，保留前版匯出造成後測失真的教訓。

新架構同時改變算術與內部資料寬度，是整體設計比較；不能把可能加速只歸因於單一因素。完整h_s.4即時服務、影像模型、跨機傳輸、功耗與新真實輸入的泛化結果尚未在本套件完成。

## 官方設計依據

AMD UG1399 2025.2 arbitrary-precision integers支持明確的無號位寬，DATAFLOW支持階段並行。官方文件不能取代本候選的實際綜合、時序及上板結果。

- https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/Arbitrary-Precision-AP-Data-Types
- https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/pragma-HLS-dataflow

原v32、私鑰、context與原資料不更動；遠端Windows只需Git及SFTP，板端沿用既有Python／g++／XRT環境。
