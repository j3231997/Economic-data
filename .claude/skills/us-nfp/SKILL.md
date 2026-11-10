---
name: us-nfp
description: 收集並整理美國非農就業（NFP / BLS CES）產業別逐月變化，產出可展開/收合產業階層的互動網頁。Use when the user asks to update, collect, or analyze US nonfarm payrolls (NFP, 非農, CES employment by industry).
---

# 美國 NFP 收集與整理

資料來源：BLS Current Employment Statistics（CES），季調後、All Employees、單位千人。
產業階層依 BLS `ce.industry` 的 display_level，收錄 L0（Total nonfarm）到 L4（細產業，例如 Wholesale trade、Finance and insurance、Accommodation and food services）。階層與 series ID 定義在 `series.json`，要增減產業改那個檔即可。

## 步驟

1. 抓資料（需要網路可連 `api.bls.gov`）：
   ```bash
   python3 .claude/skills/us-nfp/scripts/fetch_ces.py --start 2025-01 --out data/nfp_ces.json
   ```
   - 有 `BLS_API_KEY` 環境變數時用 v2 API（一次 50 檔、每日 500 次）；沒有則用 v1（一次 25 檔、每日 25 次，共用 IP 很容易用完）。
   - 若 API 回 `daily threshold ... reached`，代表免金鑰額度已滿，請使用者提供金鑰（不要叫使用者把金鑰貼在對話裡，請他設成環境變數）。
   - 腳本會列出沒有回傳資料的 series ID，若有，檢查 `series.json` 中代碼是否因 NAICS 改版而變動。
2. 產生網頁：
   ```bash
   python3 .claude/skills/us-nfp/scripts/build_dashboard.py --data data/nfp_ces.json --out output/nfp_dashboard.html
   ```
3. 確認：最新月份與 BLS Employment Situation 公布值一致（Total nonfarm MoM），最近兩個月應標示 P（初值）。

## 網頁功能

- 「展開至 L0–L4」按鈕一鍵切換顯示階層；每列 ▸/▾ 可個別展開收合。
- 數值切換：MoM 變化、3 個月平均、就業人數水準。
- 年度累計欄（各年度 12 月對前一年 12 月，當年為 YTD）。
- 異常值上色：MoM 偏離該產業期間平均 1 個標準差以上時上色（橘 = 偏強、綠 = 偏弱）。
- 目前 Payroll（百萬人）與占總非農比重。

## 分析時注意

- NFP 每月會修正前兩個月，且每年 2 月的 1 月報告會做年度基準修正（benchmark），重抓整段資料而不是只追加最新月。
- MoM 由水準值相減而得，與 BLS 新聞稿表 B-1 的變化數可能因四捨五入差 1 千人。
