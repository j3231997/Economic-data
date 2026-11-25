---
name: us-durable-goods
description: 收集美國耐久財（Census M3 Manufacturers' Shipments, Inventories, and Orders）各產業季調新訂單與出貨，算出兩位小數 MoM、官方一位小數、3 個月平均 MoM、對總額的貢獻、3 個月年化、3m/3m 年化、YoY 與前次公布的修正，產出同一個網頁、最上方可切換新訂單／出貨、可展開/收合產業階層的互動網頁。Use when the user asks to update, collect, or analyze US durable goods orders or shipments, core capital goods (core capex orders/shipments), 耐久財訂單, 耐久財出貨, 核心資本財.
---

# 美國耐久財訂單與出貨分項

資料來源：U.S. Census Bureau M3 調查，季調、百萬美元、**名目值（未經物價調整）**，不需要 API 金鑰。
- **完整報告歷史檔**（1992 至今，所有公布的 M3 類別）：`https://www.census.gov/manufacturing/m3/prel/historical_data/histshts/naics/naicsnop.xlsx`（新訂單，代碼字尾 `NO`）與 `naicsvsp.xlsx`（出貨，字尾 `VS`）。每列是「代碼, 年, 1–12 月」。
- **Advance 預估報告** `https://www.census.gov/manufacturing/m3/adv/table1a.xlsx`：只有主要產業與資本財、最近 3 個月。Advance 比同月份的完整報告早約一週；它比歷史檔新時，用它的 3 個月覆蓋有 `adv` 標籤的列（前兩個月是修正值），細項則停在完整報告的最新月份（最新月空白）。
- `prel/table1p.xlsx` 只用來讀完整報告的公布日期。
- 階層定義在 `series.json`：耐久財總額 → L1 七大產業（基本金屬、金屬製品、機械、電腦與電子、電機、運輸設備、其他耐久財，加總 = 總額）→ 細產業 → 次細產業。扣除運輸、扣除國防、資本財、非國防資本財、**核心資本財（非國防扣除飛機）**、國防資本財、耐久消費財是 `"special": true` 的斜體列，放在總額正下方，不參與加總。
- `m3` 是不含字尾的 M3 代碼（例如 `A31S` → `A31SNO`、`A31SVS`）；`adv` 是 advance table1a 的項目名稱（小寫、去掉註腳數字）。

## 步驟

1. 抓資料（需要網路可連 `www.census.gov`）：
   ```bash
   python3 .claude/skills/us-durable-goods/scripts/fetch_durable.py --start 2025-01 --out durable/data/durable.json
   ```
   - 下載兩個歷史活頁簿（約 0.9 MB）、advance table1a 與完整報告 table1p。只用 Python 標準函式庫（xlsx 用 zipfile 自行解析）。
   - 終端最後列出最新月份各產業新訂單、出貨的兩位小數 MoM，可直接引用。
   - **前次公布（prior vintage）**：以「最新月份＋報告類型（advance/full）」當版本；`--out` 已存在且版本不同時，舊檔金額存進 `prior`，網頁的「MoM 修正 pp」才有資料（例如完整報告對 advance 的修正）。所以每次更新都寫到同一個檔案，不要先刪掉舊檔。
   - `WARNING: advance labels not found` 表示 table1a 的項目名稱改了，照訊息列出的名稱修改 `series.json` 的 `adv`；`WARNING: no data for ...` 表示 `m3` 代碼在歷史檔找不到。
2. 產生網頁：
   ```bash
   python3 .claude/skills/us-durable-goods/scripts/build_dashboard.py --data durable/data/durable.json --out durable/output/durable_dashboard.html
   ```
3. 發布分享網頁（使用者要網頁時）：
   ```bash
   python3 .claude/skills/us-durable-goods/scripts/build_dashboard.py --artifact --out <scratchpad>/durable_artifact.html
   ```
   用 Artifact 工具發布這個檔案（去掉 html/head/body 外殼的版本）；之前發布過就更新同一個網址（https://claude.ai/artifact/PxoochK6zQdkhpm3ubMWxm）。
   - 同時更新「總經數據入口」https://claude.ai/artifact/9GhDBgXT3GNcX6XdjS8zh8 的耐久財卡片（`製造業與投資` 群組，`skill: us-durable-goods`）：先用 Artifact read 讀最新版，只改這張卡的 `latest`、`prelim`（完整報告 true＝P）、`fetched`、三個數字（耐久財訂單 MoM、扣除運輸 MoM、核心資本財訂單 MoM，note 放官方一位小數）與近 12 個月核心資本財新訂單 MoM 圖，再發布回同一網址。
4. 確認：總額、扣除運輸、扣除國防、核心資本財的「官方 1 位」欄要跟新聞稿一致。2026-09 驗證：advance（10/27 公布）新訂單 總額 1.84→1.8、扣除運輸 0.46→0.5、扣除國防 2.19→2.2、核心資本財 0.46→0.5，與 table1a 一致；完整報告（11/3 公布）新訂單總額修正為 1.91→1.9、核心資本財 0.649→0.6（兩位小數 0.65 正好在進位邊界，官方 1 位要看第三位）。七大產業加總剛好等於總額（新訂單 345,672、出貨 336,879）。

## 網頁功能

- **最上方「資料」單選：新訂單 New orders／出貨 Shipments**，同一張表切換；展開狀態、數值檢視、排序在切換後保留。
- 「展開至 L0–L3」一鍵切換顯示階層；每列 ▸/▾ 可個別展開收合。
- 數值切換：MoM 兩位小數、MoM 官方一位小數、**3 個月平均 MoM（近 3 個月幾何平均）**、MoM 貢獻 pp、3 個月年化、3m/3m 年化、YoY、金額（十億美元）、MoM 修正 pp（有前次公布資料才出現）。
- 月份欄標 **A**（advance 預估值）、**p**（完整報告初值）、**r**（修正值）。
- 占比 = 最新月金額 ÷ 耐久財總額；MoM 貢獻 pp =（本月 − 上月）÷ 上月耐久財總額 × 100，同層加總等於母項貢獻。
- MoM 上色：以 0.30% 為中心，高於紅、低於藍，偏離 2.0 個百分點最深（耐久財、尤其飛機波動遠大於零售），套用在 MoM 2位、官方1位、3個月平均；門檻在 template.html 的 `HEAT_CENTER`、`HEAT_FULL`。
- 進位邊界：兩位小數為 x.x5 時加點狀底線，官方一位小數取決於第三位。
- 同層產業預設按占比由大到小排序，可切回 Census 原順序。
- 標籤：`完整報告` = advance 報告沒有的細項。
- 核心資本財標色（可用「標示核心資本財」關閉）：項目欄深綠底＋實線 = 推測整個產業屬於核心資本財（非國防資本財扣除飛機），淡綠底 = 部分屬於。Census 不逐產業公布歸屬，這是依 advance table1a 註腳 3 的資本財產品清單推測，定義在 `series.json` 的 `core`（`full`／`partial`）。

## 分析時注意

- **飛機主導總額波動**：非國防飛機訂單（Boeing 接單）單月常 ±20–50%，市場看「扣除運輸」與「核心資本財」。核心資本財**新訂單**領先設備投資，**出貨**直接用於 BEA 估算 GDP 設備投資。
- 電腦與電子產品的新訂單**不含半導體**，出貨有含，所以兩者的電腦電子金額不能直接相減。
- 部分產業沒有未交訂單（農機、轎車、輕卡、重卡、電池、木製品、非金屬礦物、雜項等），Census 只公布出貨（訂單＝出貨），新訂單檢視隱藏這些列；汽車與零件、其他耐久財的新訂單仍有總數。
- advance 樣本較小，約一週後的完整報告（同時公布非耐久財與存貨）會修正；下個月的 advance 再修正前一月。修正看「MoM 修正 pp」檢視。
- 每年 Census 做年度修正（通常 5 月左右），會改寫過去數年的金額與季調因子，所以一律重抓整段資料。
- YoY 用季調值，不是未季調值。
