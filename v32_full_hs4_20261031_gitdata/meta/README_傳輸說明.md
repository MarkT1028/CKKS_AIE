# 本機經Git到遠端電腦的完整測資傳輸

流程：本機 → GitHub → 遠端電腦 → MobaXterm/SFTP → 板子。

這是原本2.83GiB測資壓縮檔的61個分片，每片最多48MiB。分成4批，每批約768MiB以下；原壓縮檔和原始資料的SHA256完全不變。無需Git LFS。沒有修改原已封裝程式或硬體映像。

請在本機CMD依序執行同目錄GIT_COMMANDS.txt的4段add/commit/push。每段push成功後，才做下一段。不要git add .把全部分片合成單次push，也不要把原3GB壓縮檔放進Git。此工具沒有自動commit或push。

遠端電腦完成git pull後，在遠端Git根目錄執行：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File .\v32_full_hs4_20261031_gitdata\meta\restore_data.ps1
```

先核對61片SHA，再還原原始壓縮檔，最後核對整檔SHA。會顯示PASS_RESTORED_ORIGINAL_ARCHIVE及路徑；預設輸出在Git資料夾的上一層。遇到同名不同內容會停止，不會覆蓋。中斷的.partial檔會保留，可用-OutputPath指定新的位置重試。

Linux或有Python的Windows也可以：

```sh
python3 v32_full_hs4_20261031_gitdata/meta/restore_data.py
```

遠端還原後，將原程式資料夾v32_full_hs4_20261031和還原的v32_full_hs4_20261031_data.tar.gz用MobaXterm上傳板子。板上依原START_HERE.md解壓、check/build/detect/smoke/formal/collect。分片資料夾無需上傳板子。

總傳輸量仍約2.83GiB；分片是為了配合GitHub單檔與每次push限制，不會讓網路總傳輸量變少。

GitHub官方限制：https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits
