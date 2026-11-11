---
name: us-cpi
description: 收集美國 CPI-U 分項指數，用 3 位小數指數算出兩位小數（unrounded）的 MoM，並與官方一位小數、3 個月年化、YoY 並列，產出可展開/收合分項階層的互動網頁。Use when the user asks to update, collect, or analyze US CPI components, unrounded / 2-decimal CPI MoM, core / supercore CPI, or 美國 CPI 分項.
---

# 美國 CPI 分項兩位小數 MoM

資料來源：BLS CPI-U，U.S. city average。
- **MoM**：季調指數 `CUSR0000<item>`，(本月 ÷ 上月 − 1) × 100，取兩位小數。BLS 新聞稿只公布一位小數，這裡的兩位小數就是市場說的「unrounded」值。
- **YoY**：未季調指數 `CUUR0000<item>`（官方 12 個月變動就是用未季調值算的）。
- 分項階層以 CPI 新聞稿 Table 2/3 為基礎：總指數 → 食品 / 能源 / 核心 → 核心之下分三塊（L2）：核心商品、核心服務、超級核心服務。核心服務底下只放住房（Rent、OER）；外宿、醫療服務、運輸服務、水費、休閒服務、教育通訊服務、其他個人服務都放在超級核心服務底下，因為它們屬於超級核心的計算範圍。定義在 `series.json`，要增減分項改那個檔即可。

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
   - 超級核心不在 Table 2，權重由核心服務 − Rent − OER 自動算出，不用手動填。
   - `anchors` 放 BLS 每年 12 月 relative importance 表（`https://www.bls.gov/cpi/tables/relative-importance/<年>.htm`）中 SASLE、SEHA、SEHC 的值，用來推算歷史月份的權重；每年 1 月指數公布後補上新一年的 12 月值。
   - 驗算：子項加總應約等於母項（例如在家食品 6 項 ≈ Food at home；食品 + 能源 + 核心 ≈ 100）。
3. 產生網頁（權重在這一步併入，改權重不必重抓指數）：
   ```bash
   python3 .claude/skills/us-cpi/scripts/build_dashboard.py --data data/cpi.json --out output/cpi_dashboard.html
   ```
4. 確認：總指數與核心的「官方 1 位」欄要跟 BLS 新聞稿的季調月增率一致。

## 網頁功能

- 「展開至 L0–L4」一鍵切換顯示階層；每列 ▸/▾ 可個別展開收合。
- 最新月摘要欄：MoM 兩位、官方一位、3 個月年化、YoY。
- 數值切換：MoM 兩位小數、MoM 官方一位小數、3 個月年化、YoY（NSA）、季調指數。
- 異常值上色：MoM 偏離該分項期間平均 1 個標準差以上時上色（橘 = 偏熱、藍 = 偏冷）。
- 進位邊界標示：兩位小數剛好是 x.x5（例如 0.35）時加點狀底線，代表官方一位小數取決於第三位（0.345 → 0.3、0.350 → 0.4），公布前預估時要特別注意。
- 權重：顯示 `weights.json` 的 relative importance（占總指數 %），同層分項預設按權重由大到小排序，可切回 BLS 原順序。
- MoM 貢獻 pp = 權重 × 最新月 MoM ÷ 100，即該分項對總指數 MoM 的百分點貢獻；食品 + 能源 + 核心的貢獻加總 ≈ 總指數 MoM。

## 超級核心算法

口徑與 Bloomberg `CSXHSPCI` 相同：**核心服務（SASLE）扣除主要住所租金（SEHA）與 OER（SEHC）**，旅館住宿、房屋保險等其他住房項目仍保留在內。BLS 沒有公布這個指數，由 `build_dashboard.py` 自行計算：

g = (w_s·g_s − w_r·g_r − w_o·g_o) ÷ (w_s − w_r − w_o)

- g：各分項季調指數的未捨入 MoM（完整精度，不先四捨五入）。
- w：**前一個月**的 relative importance。最新月直接用 Table 2 的值；歷史月份用 RI_m = RI_錨點 × (I_m ÷ I_錨點) ÷ (總指數_m ÷ 總指數_錨點)（未季調指數）從錨點推算。
- 逐月連鎖成指數（首月 = 100），所以網頁的指數水準和 Bloomberg 不同，但 MoM 相同。YoY 用同樣方法、改用未季調指數計算。
- 驗證：2026-01～10 共 10 個月，兩位小數全部與 Bloomberg 一致（例如 07～10 月算出 0.189 / 0.5095 / 0.4224 / 0.3995%，Bloomberg 為 0.19 / 0.51 / 0.42 / 0.40%）。
- 2025 年以前的權重是從 2025-12 錨點往回推，跨過年度權重更新，可能差 0.01；補上前一年 12 月的 SASLE、SEHA、SEHC relative importance 到 `anchors` 即可修正。
- 住房（Shelter）列的 MoM 是 BLS 的住房總指數，仍含外宿與房屋保險；底下只列 Rent、OER 兩項，外宿顯示在超級核心服務底下。房屋保險（Tenants' and household insurance，權重約 0.29）也在超級核心範圍內，但沒有列為分項，所以超級核心底下各分項權重加總會略小於超級核心本身。
- BLS 的 `SASL2RS`（Services less rent of shelter）含能源服務與房屋保險，口徑不同，不要拿來當超級核心。

## 分析時注意

- BLS 指數公布到 3 位小數，月增率由指數算出後四捨五入到 1 位小數，所以從指數算出的兩位小數在絕大多數情況下四捨五入後會等於官方值。
- 每年 2 月公布 1 月 CPI 時，BLS 會修正過去 5 年的季調因子，季調 MoM 會跟著改，所以重抓整段資料，不要只追加最新月。
- 2025-10 的 CPI 因聯邦政府關門沒有發布（網頁頁首會列出缺漏月份）。因此 2025-11 沒有 MoM，2026-10 起大多數分項沒有 YoY；少數有用其他來源補值的分項（例如汽油、新車）仍有數字。
- 分項 MoM 用一位小數乘上權重加總不會剛好等於總指數；要拆貢獻度，請用兩位小數值和前一個月的 relative importance（網頁的貢獻欄就是這樣算的）。權重只對最新月有意義，舊月份的貢獻要用當時的權重。
