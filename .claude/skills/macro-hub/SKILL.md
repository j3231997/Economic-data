---
name: macro-hub
description: 重建並發布「總經數據入口」網頁：依勞動市場 / 通膨分組列出各總經儀表板（NFP、時薪、JOLTS、CPI）的連結、最新月份、重點數字與近 12 個月小圖。Use when the user asks to update or open the macro hub (總經入口、總經數據入口), after any us-nfp / us-wages / us-jolts / us-cpi update, or when a new macro dashboard is added.
---

# 總經數據入口

網址：https://claude.ai/artifact/9GhDBgXT3GNcX6XdjS8zh8 （發布時傳這個 `url`，不要建立新的）

入口頁的卡片清單在 `pages.json`（分組、標題、網址、資料檔、公布時間、說明）；重點數字和小圖由 `scripts/build_hub.py` 從各儀表板的資料 JSON 讀出，所以入口頁永遠跟最近一次抓的資料一致。

## 步驟

1. 先更新要更新的指標（各自的 skill：抓資料、產生網頁、發布到原網址）。
2. 重建入口頁：
   ```bash
   python3 .claude/skills/macro-hub/scripts/build_hub.py --out hub/macro_hub.html
   ```
3. 用 Artifact 工具發布 `hub/macro_hub.html`，傳上面的 `url` 更新同一個網址。
4. 把 `hub/macro_hub.html` 跟資料一起 commit。

## 新增一個總經儀表板

1. 在 `pages.json` 加一筆：`kind`、`group`（沒有的分組要加進 `groups`）、`title`、`skill`、`url`、`data`、`release`、`desc`。
2. 在 `build_hub.py` 加同名的 extractor 函式（回傳 `latest`、`prelim`、`fetched`、`figures`、`chart`），並登記到 `KINDS`。
3. 該指標的 SKILL.md 最後加一步「重建並發布總經數據入口（macro-hub）」。
4. 重建並發布入口頁。
