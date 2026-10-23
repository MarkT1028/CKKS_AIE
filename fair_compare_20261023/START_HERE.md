# 新版 CPU／硬體公平對照

本包沿用已板測的四個硬體映像，不需要重跑 Vivado／Vitis。
新增同板 ARM CPU 的1／2執行緒比較；真正板上時間須由使用者執行後取得。
單／雙路流水線16份保存輸出的解密與平方驗證，已於2026/10/23在開發主機全部完成。

## 第一次：先跑目前已開機的版本

整個fair_compare_20261023資料夾上傳到板子，例如：

```sh
cd /root/114C75007/vek280/AIE/fair_compare_20261023
sh check_package.sh
sh build_fair_board.sh
python3 board_experiment.py detect
```

看matching_variants顯示哪一個。若是raw_1_pipe，依序跑：

```sh
sh run_fair_board.sh raw_1_pipe 1 smoke
sh run_fair_board.sh raw_1_pipe 30 round1
```

若顯示raw_2_pipe，就把上述版本名稱改成raw_2_pipe。
若顯示baseline_1或raw_2_full，也可以先用該名稱測；沒有匹配版本時先停止。
1是短測；30是每案例正式樣本數，另有3次暖機。
同一次命令會依序執行CPU前測、硬體四種案例、CPU後測，每輪都完整核對。

## 換下一個版本

四個版本為baseline_1、raw_1_pipe、raw_2_full、raw_2_pipe。
以下以raw_2_pipe示範；保留序列埠終端機：

```sh
sh switch_fair_board.sh raw_2_pipe check
sh switch_fair_board.sh raw_2_pipe arm
```

確認成功後，由你另行執行：

```sh
sync && reboot
```

重開機後回到本資料夾，執行detect及該版本的短測／30次正式測試。
check不改開機檔；arm備份並切換slot1、預約一次性切換，但不自動重開機。
BOOT.BIN、slot2、Image與boot.scr沿用原保護檢查。

## 要回傳哪些資料

每次會產生results_fair_開頭的新資料夾。請完整保留並回傳，包含短測及正式測試。
先完成四種版本的round1，之後再於不同開機session各跑round2；第二輪建議反向版本順序。
先完成一個版本也能回傳分析，不需等全部結束。
切換硬體需要重新開機；同一個已匹配版本直接測試即可。

若重開機後需要恢復原本網路設定：

```sh
ip link set end0 up
ip addr replace 192.168.10.98/24 dev end0
```

完整計時定義、比較方法與結果彙整方式見README_測試說明.md。
