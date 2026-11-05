# 完整 g_a.3 測資傳輸

測資包含全部 16 輸出、64 組 MAC、53 模數與 131072 係數。壓縮檔為 39,334,819,787 bytes（36.63 GiB），解壓約 43.07 GiB。沒有改成首尾子集。

兩種傳輸方式會還原同一個 `v32_ga3_20261104_data.tar.gz`，SHA256：

`f9d28c8e22ae5fcc3c96b5ee42babb64ab157cd0d09eff94b035d0ca84c095cf`

## 方法一：保留原本普通 Git 搬移方式

在本機 Windows CMD、Git 根目錄執行，先提交程式與 metadata：

```bat
git add -- v32_ga3_20261104 v32_ga3_20261104_gitdata
git commit -m "Add complete real g_a.3 PL and dual-AIE comparison kit"
git push origin main
```

資料分片被新 gitdata/.gitignore 忽略，避免一次 add 全部。以下腳本會逐片核對 SHA256，依序執行 37 批 commit 與 push；每批最多 1 GiB，仍會在 Git 歷史增加總計約 36.63 GiB 的資料。它不會處理其他 staged 修改：若有，會先停下讓你確認。

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\push_all_batches.ps1"
```

中斷時已推成功的批次保留。可重跑同一指令；已相同的批次不重複建立 commit。或指定續跑某一批，例如第 8 批：

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\push_batch.ps1" -Batch 8
```

全部完成後，遠端 Windows CMD 在相同倉庫根目錄執行：

```bat
git pull origin main
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\restore_data.ps1"
```

還原檔預設存放在倉庫上一層；以最後 `PASS_RESTORED_ORIGINAL_ARCHIVE=...` 顯示位置為準。腳本不會覆寫不同 SHA256 的既有檔案。

## 方法二：程式用 Git，資料用同倉庫 Release（建議）

適合避免讓倉庫多出約 36.63 GiB 永久歷史。GitHub 官方建議用 Release 搬大型二進位檔，而不是持續加入 Git objects；倉庫 10 GB 是建議值，不能說成硬性總容量上限。[大型檔案說明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[倉庫限制](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits)。

這條路也使用完整資料，已準備 37 個每檔不超過 1 GiB 的 Release assets，保留於本機 `D:\CodexBuilds\v32_ga3_20261104\release_assets`。它們沒有加入 Git，也**尚未上傳／發布**。

先提交並 push 上述程式與 metadata。若你已有官方 GitHub CLI 並登入，於本機 CMD 執行：

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\upload_release_data.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\upload_release_data.ps1" -AssetDirectory "D:\CodexBuilds\v32_ga3_20261104\release_assets" -Upload
```

第一行只顯示計畫，不接觸 GitHub；第二行才會建立草稿並上傳。它逐檔核對遠端 SHA256／大小，重跑跳過已相同的檔案，不刪除或覆蓋既有 assets。若 GitHub 未提供 digest，會保留草稿並報錯，不能當已驗證成功。`gh` 未安裝時會停止；工具不替你安裝或讀取 token。

檢查所有 assets 成功後，由你另行發布：

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\upload_release_data.ps1" -Publish
```

也可以用 GitHub 網頁，以 `RELEASE_TRANSFER_MANIFEST.json` 指定的 tag 建立 Release，貼上 `RELEASE_NOTES.md` 並附上全部 37 個 `.part`。不要把缺檔的草稿當作可下載版本。

遠端 Windows CMD：

```bat
git pull origin main
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\v32_ga3_20261104_gitdata\meta\download_release_data.ps1"
```

腳本使用 Windows curl 續傳，再核對所有檔案並還原壓縮檔；不需要 Python／OpenFHE。只做 git pull 不會下載 Release assets。

無論哪一種方法，最後僅把 `v32_ga3_20261104` 程式資料夾與還原出的 `.tar.gz` 傳至板子，依程式資料夾的 START_HERE.md 執行。不必把所有 Git 分片再傳到板子。

發行工具語法依 [gh release create](https://cli.github.com/manual/gh_release_create)、[upload](https://cli.github.com/manual/gh_release_upload)、[edit](https://cli.github.com/manual/gh_release_edit)。工具沒有使用會刪掉舊附件的 `--clobber`。
