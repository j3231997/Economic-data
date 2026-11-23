# Economic-data 工作規則

## 每次更新後都開 PR 合併到 main
- 只要有 commit 並 push 到工作分支（更新數據、改版面、改 skill 都算），就主動開一個 PR 合併到 `main`，不用再問使用者。
- PR 標題用一句話說明改了什麼；內文列出更新的資料月份與公布日期，以及發布或更新的 Artifact 網址。
- 原因：每次新對話都從 `main` 開分支。如果新資料只留在舊分支，下次重建網頁就會用到舊資料，把已經發布的較新月份蓋掉。

## 重建網頁前先確認資料是最新的
- 用 `*/data/*.json` 重建、重新發布 dashboard 之前，先比對 repo 內資料的最新月份（`latest`、`fetched_at`）和已發布 Artifact 上的最新月份。
- 如果 repo 的資料比網頁上的舊，先找出較新的資料（`git fetch` 後檢查其他 `origin/claude/*` 分支），或用 skill 重新抓取。不要拿舊資料覆蓋網頁。
