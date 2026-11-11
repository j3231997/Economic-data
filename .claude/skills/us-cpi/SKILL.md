---
name: us-cpi
description: 收集美國 CPI-U 分項指數，用 3 位小數指數算出兩位小數（unrounded）的 MoM，並與官方一位小數、3 個月年化、YoY 並列，產出可展開/收合分項階層的互動網頁。Use when the user asks to update, collect, or analyze US CPI components, unrounded / 2-decimal CPI MoM, core / supercore CPI, or 美國 CPI 分項.
---

# 美國 CPI 分項兩位小數 MoM

資料來源：BLS CPI-U，U.S. city average。
- **MoM**：季調指數 `CUSR0000<item>`，(本月 ÷ 上月 − 1) × 100，取兩位小數。BLS 新聞稿只公布一位小數，這裡的兩位小數就是市場說的「unrounded」值。
- **YoY**：未季調指數 `CUUR0000<item>`（官方 12 個月變動就是用未季調值算的）。
- 分項階層依 CPI 新聞稿 Table 2/3：總指數 → 食品 / 能源 / 核心 → 核心商品、核心服務 → 住房（Rent、OER、Lodging）、醫療服務、運輸服務等。另外列出超級核心（Services less rent of shelter，`SASL2RS`）。定義在 `series.json`，要增減分項改那個檔即可。

## 步驟

1. 抓資料（需要網路可連 `api.bls.gov`）：
   ```bash
   python3 .claude/skills/us-cpi/scripts/fetch_cpi.py --start 2025-01 --out data/cpi.json
   ```
   - 每個分項抓季調和未季調兩條，約 94 條序列。有 `BLS_API_KEY` 環境變數時用 v2 API（一次 50 條，2 次請求）；沒有則用 v1（一次 25 條，4 次請求，每天 25 次額度、共用 IP 很容易用完）。
   - 若 API 回 `daily threshold ... reached`，代表免金鑰額度已滿，請使用者提供金鑰（不要叫使用者把金鑰貼在對話裡，請他設成環境變數）。
   - 腳本最後會在終端列出最新月份各分項的兩位小數 MoM，可直接引用。
   - `Series does not exist for CUSR0000...` 表示 BLS 沒有季調該分項（目前是 Health insurance `SEME`、Other personal services `SAGS`），MoM 會改用未季調值，網頁上標 `NSA`。
2. 更新權重（每次 CPI 公布後）：用 WebFetch 讀 `https://www.bls.gov/news.release/cpi.t02.htm`（新聞稿 Table 2），取 "Relative importance" 欄（標題是前一個月，例如 10 月 CPI 的表標 Sep. 2026），更新 `weights.json` 的 `as_of`、`release` 與各分項數值。
   - 不要用 curl 抓 bls.gov 網頁，會被擋（403）；BLS API 也沒有權重。
   - 超級核心 `SASL2RS` 不在 Table 2，用 (Services less energy services + Energy services) − Rent of shelter 推算。
   - 驗算：子項加總應約等於母項（例如在家食品 6 項 ≈ Food at home；食品 + 能源 + 核心 ≈ 100）。
3. 產生網頁（權重在這一步併入，改權重不必重抓指數）：
   ```bash
   python3 .claude/skills/us-cpi/scripts/build_dashboard.py --data data/cpi.json --out output/cpi_dashboard.html
   ```
4. 確認：總指數與核心的「官方 1 位」欄要跟 BLS 新聞稿的季調月增率一致。

## 網頁功能

- 「展開至 L0–L4」一鍵切換顯示階層；每列 ▸/▾ 可個別展開收合。超級核心固定顯示在總指數下方。
- 最新月摘要欄：MoM 兩位、官方一位、3 個月年化、YoY。
- 數值切換：MoM 兩位小數、MoM 官方一位小數、3 個月年化、YoY（NSA）、季調指數。
- 異常值上色：MoM 偏離該分項期間平均 1 個標準差以上時上色（橘 = 偏熱、藍 = 偏冷）。
- 進位邊界標示：兩位小數剛好是 x.x5（例如 0.35）時加點狀底線，代表官方一位小數取決於第三位（0.345 → 0.3、0.350 → 0.4），公布前預估時要特別注意。
- 權重：顯示 `weights.json` 的 relative importance（占總指數 %），同層分項預設按權重由大到小排序，可切回 BLS 原順序。
- MoM 貢獻 pp = 權重 × 最新月 MoM ÷ 100，即該分項對總指數 MoM 的百分點貢獻；食品 + 能源 + 核心的貢獻加總 ≈ 總指數 MoM。

## 分析時注意

- BLS 指數公布到 3 位小數，月增率由指數算出後四捨五入到 1 位小數，所以從指數算出的兩位小數在絕大多數情況下四捨五入後會等於官方值。
- 每年 2 月公布 1 月 CPI 時，BLS 會修正過去 5 年的季調因子，季調 MoM 會跟著改，所以重抓整段資料，不要只追加最新月。
- 2025-10 的 CPI 因聯邦政府關門沒有發布（網頁頁首會列出缺漏月份）。因此 2025-11 沒有 MoM，2026-10 起大多數分項沒有 YoY；少數有用其他來源補值的分項（例如汽油、新車）仍有數字。
- 分項 MoM 用一位小數乘上權重加總不會剛好等於總指數；要拆貢獻度，請用兩位小數值和前一個月的 relative importance（網頁的貢獻欄就是這樣算的）。權重只對最新月有意義，舊月份的貢獻要用當時的權重。
