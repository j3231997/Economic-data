# Economic-data

美國總經數據的收集腳本與互動網頁。每個指標一個 skill（`.claude/skills/us-*`），資料在 `<指標>/data/`，網頁在 `<指標>/output/`，並各自發布成固定網址的 Artifact。

## 總經數據入口

- 入口頁：https://claude.ai/artifact/9GhDBgXT3GNcX6XdjS8zh8 ，由 `macro-hub` skill 產生。
- 任何總經網頁更新後，都要接著重建並發布入口頁（`macro-hub` skill 的步驟）。
- 新做的總經網頁一律加進入口頁：在 `.claude/skills/macro-hub/pages.json` 加一筆、在 `build_hub.py` 加 extractor，並在新 skill 的 SKILL.md 最後加「更新入口頁」一步。不確定分在哪一組（目前有「勞動市場」「通膨」）時先問使用者。
- 發布已存在的網頁時，一律用 SKILL.md 記錄的網址更新，不要建立新的 Artifact。
