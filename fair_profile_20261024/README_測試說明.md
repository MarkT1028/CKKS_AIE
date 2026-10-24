# 2026/10/24 CPU 控制實驗與新版雙路 profiling

## 範圍

上一輪單／雙流水線K16 execution約30.67／15.46 ms；CPU單執行緒前後有約32%及−20%的變動。本包新增控制實驗和raw_2_pipe實際mapping的profiling。四個硬體映像、算術與fixture沿用；不增加AIE、不修改CPU頻率或governor、不自動重開機。新板上結果仍待實測。

## 第一項：CPU與四架構比較

入口：`sh run_controlled_board.sh VARIANT REPS LABEL forward|reverse`。

每命令24案例，CPU前10＋硬體4＋CPU後10。CPU的K1／K16各測：

| 名稱 | 計算執行緒 |
| --- | --- |
| unbound_t1 | 1個，可在原可用核心集合內排程 |
| unbound_t2 | 2個持續重用worker，不綁定個別核心 |
| pinned_t1_c0 | 單執行緒固定選定第一核心 |
| pinned_t1_c1 | 單執行緒固定選定第二核心 |
| pinned_t2_c01 | 兩worker分別固定第一、第二核心 |

實際核心通常0／1，以selected_cpus和host/affinity.json為準。雙執行緒只對計算worker逐一綁核，沒有把整個driver限成一個CPU。單執行緒由主執行緒直接算。保存實際mask、TID及每輪CPU起終點，綁核失敗立即停止；端點採樣不能觀察兩點間的所有遷移。

前測／後測的案例順序互相反轉；reverse再反轉K、CPU設定及resident／transfer順序。全部順序存入plan，不依session標籤猜測。

CPU保留U128累加後取模，N8192／L3、K1／16測資不變。pool建立及綁核排除於compute，派工、等待、CPU端點採樣和端點檢查包含於compute。poison＋compute＋完整整數核對為verified_call。新控制組採相同觀測方式，但增加的觀測開銷使它不是舊CPU程式完全相同的逐cycle重測。

正式硬體host與上一輪四版來源一致。execution包含XRT啟動、PL／AIE及等待；transaction包含每輪上傳（transfer）、填毒、execution、狀態、讀回、合併、核對。resident迭代前上傳並重用輸入。皆排除檔案解析、一次性配置、OpenFHE及完整應用。

每案例父程式以100ms間隔記錄頻率、governor、溫度與/proc/stat；CPU和硬體都採同一方法。採樣本身有主機負擔，快照不代表兩點間沒有改變，不會被解釋為已排除降頻、快取或排程因素。

正式每案例3暖機＋30次。四版round1之後，反向架構順序於另一個boot做round2。每版要再次arm並重開機，包括連續測相同映像時。短測不計正式覆蓋。

彙整：

```sh
python3 summarize_controlled.py results_controlled_*
```

分析器重算phase和、樣本數、median、nearest-rank P95，檢查完整golden、worker mask及端點；輸出CPU_DRIFT.csv、CPU_HW_COMPARISON.csv及comparison.json。前後測始終分開，pooled只作描述。超過5%是事先設定的報告旗標，不是顯著性標準或刪除樣本理由。

完整覆蓋需四架構各至少兩個不同boot_id，正反順序在不同boot。跨日資料保留實際日期，不宣稱同日比較。

## 第二項：raw_2_pipe目前瓶頸

入口：`sh run_profile_board.sh all 200 profile1`。皆K16 resident，各3暖機＋200輪，另存診斷資料。

| 組別 | 觀察內容 |
| --- | --- |
| baseline／baseline_after | AIE profile關閉，仍使用診斷host與native XRT API trace，觀察整批前後差異 |
| heat_map | active、stall、vector及memory conflicts |
| stalls | memory／stream／lock等停等，按實際counter覆蓋解讀 |
| execution | vector／load／store相關事件 |
| dma_in0 | S2MM ch0：MG(16,0)、MG(18,0)、MG(18,1) |
| dma_in1 | S2MM ch1：MG(16,0) |
| dma_out0 | MM2S ch0：MG(17,1)、MG(18,0) |

核心是CR(17,0)、CR(18,0)。上述MG是AIE tile的local memory module，不是獨立memory tile。profiling_mapping.json、references/AIE_METADATA_raw_2_pipe.json及DMA_report保留實際映射依據。

採graph-based同時覆蓋core／local DMA；throughputs的core及memory選同metric/channel，符合XRT互相關聯事件設定。不要求shim counter，不呼叫先前失敗的native PLIO event::start_profiling。每組退出後才啟動下一組。

每輪完整核對73728 words。counter_coverage.json檢查實際METRIC_DATA，heat_map／stalls必須覆蓋兩顆core，DMA必須覆蓋實際tile/channel。保留所有原始CSV、JSON、run_summary和log。零stall可以是有效值，不以非零作成功門檻；缺事件才標partial。dma_out1是未使用channel的選擇性控制組，不列入all，也不能以其零活動推論輸出無反壓。

獨立profile_host額外保存每lane reader／reducer啟動返回及等待完成的觀察時間，並保留launch、execution、讀回等phase。**等待依序呼叫，觀察是主機看到完成的上界，不是各kernel精確硬體時間。** profiler與host相對時鐘也不能未校準就相減。自動檢查只驗證counter覆蓋，不直接宣稱新版stall百分比或唯一瓶頸。

現有映像未新增PL AXI stream monitor或reducer內部cycle counter。若runtime counters與host紀錄不足以區分供料／消費限制，後續才需另建含PL觀測點的診斷映像；此包不聲稱已量到不存在的觀測點。

## 切換與資料保存

check只讀，arm沿用既有SHA、備份、slot與stock BOOT.BIN／slot2／Image／boot.scr保護，準備一次性切換但不重開機。成功後才由使用者另行sync和reboot；同一已匹配版本直接測試即可。

完整回傳results_controlled_*、results_profile_*、switch_logs及板上bin。失敗資料也保留；不覆蓋舊結果。每輪raw核對仍使用兩份固定fixture，不等於隨機資料或每輪獨立解密。不在板子發佈secret key，解密證據沿用既有16份驗證。

## 方法來源

- [AMD 2025.2系統profiling](https://docs.amd.com/r/2025.2-English/ug1701-vitis-accelerated-embedded/Stage-2-System-Profiling)
- [AMD 2025.2 metric sets](https://docs.amd.com/r/en-US/ug1076-ai-engine-environment/Metric-Sets?contentId=rQSEoHPjB8TTcmv~GKzlwA)
- [AMD xrt.ini](https://docs.amd.com/r/en-US/ug1702-vitis-accelerated-reference/xrt.ini-File?contentId=mhOVohPXmBg4USmtsCB78g)
- [Linux pthread_setaffinity_np](https://man7.org/linux/man-pages/man3/pthread_setaffinity_np.3.html)
- XRT 2025.2 aie_profile_util.cpp／aie_profile_metadata.cpp（先前已核對的來源）；只對hardware generation2檢查既有事件ID。
