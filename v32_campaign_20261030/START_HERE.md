# 下一輪：跨開機重現與 AIE／reducer 四版本比較

這一輪先完成研究比較的前兩項。新增實驗管理與證據封裝，沿用原有四份實際 routed 映像、雙 AIE、host 數學運算及 CPU 參考。**本套件尚未上板，不預填新速度，也不保證每個候選都變快。** 前輪 545.388ms 是另一個套件、單一 boot、固定真實 h_s.4 工作組的已驗收歷史結果。

## 要上傳哪個

上傳整個 `v32_campaign_20261030`，放在原測資套件旁邊：

```text
/root/114C75007/vek280/AIE/
  v32_hs4_20261027/       # 保留原896MiB輸入與42MiB golden
  v32_overlap_20261030/   # 原實驗與結果保留
  v32_campaign_20261030/  # 這次的新資料夾
```

新套件重用 `v32_hs4_20261027` 的凍結測資，不重複上傳938MiB資料。舊結果不自動計入這輪計畫，也不覆寫或刪除它們。

## 第一次先做這些

```sh
cd /root/114C75007/vek280/AIE/v32_campaign_20261030
sh check_package.sh
sh build_board.sh
python3 board_runner.py detect
sh run_study.sh next
```

check及build只校驗／編譯，不運行PL/AIE、不改開機映像、不重啟。建置包括相同CPU自我測試、非同步排程功能檢查、四份host的真實16塊拆分合併檢查。detect應顯示 `v32_core_2_pipe`，UUID `050ea5cc23fb5038bad0aca23cbd240b`。若不是，`next`會提示既有受保護的check／arm指令；請按提示切換後自行重啟。

## 第一階段：三個獨立開機

在相符core映像下執行：

```sh
sh run_study.sh host
```

每次只完成目前boot的一個步驟：H01、H02或H03。每步自動串行執行smoke、兩次正式模式比較與獨立CPU診斷。每種模式正式5筆乘兩輪，合計10筆；每輪各1次硬體暖機，相鄰CPU前後各1次暖機加3筆正式，CPU固定兩個worker。兩個模式為原map_pingpong與新map_finish_overlap。H02反轉兩次formal的先後順序，三個boot都保留同boot正反模式比較。

跑完會印出進度，例如 `HOST_BOOTS=1/3`，並提示需要新boot。**同一開機重複執行不會算第二個boot，也不會再跑硬體。** 你準備好時才自行執行：

```sh
sync && reboot
```

重新登入，回到新資料夾，先detect，再跑同一指令：

```sh
cd /root/114C75007/vek280/AIE/v32_campaign_20261030
python3 board_runner.py detect
sh run_study.sh next
sh run_study.sh host
```

如果重開後UUID不同，先依 `next` 提示切回core映像。**一般同映像重開不用arm**，只有切換映像才需要check／arm。第三個boot完成後：

```sh
python3 collect_results.py --phase host
```

下載印出的 `collected_study_host_*.tar.gz` 給我。可以先回傳這一階段，稍後再做硬體比較。

## 第二階段：兩輪相反順序的四版本比較

主機三個boot完成後，執行：

```sh
sh run_study.sh next
sh run_study.sh ablation
```

每次只運行目前需要的一個版本、一個boot。四種版本都固定兩顆AIE、225MHz PL、相同輸入、相同CPU與 **map_pingpong** 主機排程，避免把收尾重疊的收益混入硬體貢獻。

| 步驟 | 區組 | variant | AIE核心 | reducer |
| --- | --- | --- | --- | --- |
| A01 | 1 | v32_core_2_pipe | 新 | 新 |
| A02 | 1 | v32_aie_only_2_pipe | 新 | 原 |
| A03 | 1 | v32_reducer_only_2_pipe | 原 | 新 |
| A04 | 1 | v32_diag_2_pipe | 原 | 原 |
| A05 | 2 | v32_diag_2_pipe | 原 | 原 |
| A06 | 2 | v32_reducer_only_2_pipe | 原 | 新 |
| A07 | 2 | v32_aie_only_2_pipe | 新 | 原 |
| A08 | 2 | v32_core_2_pipe | 新 | 新 |

每步含smoke、兩輪formal，各版本每個boot合計10筆正式硬體及相鄰CPU前後測。完成兩個區組後，每版本有兩個不同boot的10筆資料，仍分boot呈現。A01可直接沿用H03的core開機；A04與A05雖是同映像，仍需重新開機，不能把同一boot當兩個獨立區組。

跑完任何步驟，`next`會顯示下一個variant。以A02為例：

```sh
sh switch_fair_board.sh v32_aie_only_2_pipe check
sh switch_fair_board.sh v32_aie_only_2_pipe arm
```

確認成功出現 `ARMED_ONLY` 後，**親自執行** `sync && reboot`。重開、回到資料夾後：

```sh
python3 board_runner.py detect
sh run_study.sh next
sh run_study.sh ablation
```

請照 `next` 所列版本，不自行跳步或同時開兩個測試。腳本不會自行寫入開機區、arm或重啟。既有切換工具沿用前版，會備份slot1，保留BOOT.BIN、Image、boot.scr與slot2；重啟前若要取消既有arm，執行 `sh prepare_variant_srst.sh --cancel`。

每完成一個區組即可單獨回傳：

```sh
python3 collect_results.py --phase ablation --block 1
python3 collect_results.py --phase ablation --block 2
```

分別下載 `collected_study_ablation_block1_*.tar.gz` 和 `collected_study_ablation_block2_*.tar.gz`。先完成第一個區組就可以先收集，不必等待第二個。完成8步後會停在core映像。

## 進度、失敗及中斷

```sh
sh run_study.sh status
sh run_study.sh summary
```

status／next只重讀已保存的資料，不執行硬體或重寫原比較；summary另產生 `study_summary.json` 和 `study_summary.csv`。進度以固定協議、Linux boot_id、variant UUID、CPU及全部host執行檔雜湊、相鄰CPU、逐塊時間線和輸出SHA重算，不只相信先前的PASS字串。步驟按協議編號排序，不依賴可能在重開或NTP後倒退的UTC時間。

整個步驟共用跨套件硬體鎖，涵蓋三次運行之間及診斷、封存期間，避免另一個套件插入板測。每個成功步驟均有完整檔案SHA索引。重新跑相同phase會從下一個尚未成功的步驟開始；中斷／失敗重跑會建立新attempt，重做該步，保留先前全部資料，不選最快結果。

失敗、未完成、未納入計畫的手動結果與CPU漂移超過5%的輪次會標示review，保留原值。**速度沒有變快也會保留並計入，沒有設速度達標才算成功的條件。** 如果既有成功結果、協議或執行檔遭更動，會阻止混合統計。診斷約50ms取樣另跑，不當作正式CPU基準，未啟用PMU也不填入零計數。

## 重開後恢復既有IP

如需使用先前的設定，在序列埠終端機執行：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

這是目前開機的設定，不會由此套件自動修改網路。

## 統計與驗收範圍

- 主機比較先算各boot的10筆中位數，再以每個boot等權摘要，不把同boot重複樣本當獨立開機。
- 硬體四格先按兩個區組分開報告，列出只改AIE、只改reducer、同時修改與描述性的交互作用。版本在不同boot執行，反序區組不能完全消除跨boot影響，不宣稱已取得隨機化或純cycle因果歸因。
- 主指標是從首塊準備到末塊完整合併及5,505,024個residue驗證的實際常駐wall。smoke、暖機、一次setup、CSV寫入和獨立export replay另列；export包括重算、驗證與保存，非純存檔時間。
- execute_sum_ms是主機start至wait返回包絡，可能含前塊收尾，並非純AIE／PL時間，也不是DMA事件。完整模型、跨機傳輸、物件重建與解密續算沒有計入主要wall。
- 仍為同一組N131072、L14、K16的真實輸入。更多真實工作組／level、reader profiling與即時整模型留作後續，不在這輪虛構新數據。
- 板上逐字比對通過後，原context解密、平方與原Python續算仍需回傳實際輸出後獨立驗收。套件不包含私鑰。

收集使用gzip level1並顯示INDEX／PACK／VERIFY進度，每個壓縮成員重新驗SHA；會包含原始輸出、失敗資料、boot／建置身分、時間線、CPU診斷及nested routed證據。若發現原始資料完整性異常，仍可打包供診斷並明確標記INTEGRITY_REVIEW_REQUIRED；壓縮檔byte驗證不等於科學驗收。
