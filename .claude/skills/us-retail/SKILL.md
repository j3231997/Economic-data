---
name: us-retail
description: 收集美國零售銷售（Census Advance Monthly Retail Trade）各業別季調銷售額，算出兩位小數 MoM、官方一位小數、控制組（control group）、對總額的貢獻、3 個月年化、3m/3m 年化、YoY 與前次公布的修正，產出可展開/收合業別階層的互動網頁。Use when the user asks to update, collect, or analyze US retail sales, control group / retail control, 零售銷售, 美國零售 分項.
---

# 美國零售銷售分項

資料來源：U.S. Census Bureau，季調、百萬美元、**名目值（未經物價調整）**，不需要 API 金鑰。
- **MARTS**（Advance Monthly Retail Trade）時間序列檔 `https://www.census.gov/retail/marts/www/adv<code>.txt`：總額、扣除項總額與 13 個三位數業別，含最新的預估月（advance）。
- **MRTS**（Monthly Retail Trade）活頁簿 `mrtssales92-present.xlsx` 的 ADJUSTED 區塊：更細的業別（電商、量販、藥局、汽車零件等），**比預估報告晚一個月**，最新月份空白。
- 階層定義在 `series.json`：總額 → L1 五塊（控制組、汽車與零件、加油站、建材、餐飲，加總 = 總額）→ 業別 → 細業別。扣除汽車／扣除加油站／扣除汽車與加油站／零售總額（不含餐飲）是 `"special": true` 的斜體列，放在總額正下方，不參與加總。
- 控制組 = 總額 − 441 汽車與零件 − 444 建材 − 447 加油站 − 722 餐飲，用季調金額相減（`derived`，在 `build_dashboard.py` 計算）。Census 沒有公布這個序列，這是市場與 BEA 估算 PCE 商品消費用的口徑。
- api.census.gov 現在要金鑰（沒有金鑰會被轉到 missing_key 頁），所以不用 API，直接抓上面兩個檔案。

## 步驟

1. 抓資料（需要網路可連 `www.census.gov`）：
   ```bash
   python3 .claude/skills/us-retail/scripts/fetch_retail.py --start 2025-01 --out retail/data/retail.json
   ```
   - 會下載 21 個 adv 文字檔、MRTS 活頁簿（約 450 KB）與 `marts_current.xlsx`（只取公布日期）。只用 Python 標準函式庫（xlsx 用 zipfile 自行解析）。
   - 終端最後列出最新月份各業別的兩位小數 MoM，可直接引用。
   - **前次公布（prior vintage）**：若 `--out` 已存在且最新月份不同，舊檔的金額會存進 `prior`，網頁的「MoM 修正 pp」才有資料。所以每次更新都寫到同一個檔案，不要先刪掉舊檔；同一次公布重抓不會覆蓋已存的 prior。
   - `WARNING: no data for ...` 表示 `series.json` 的 adv / mrts 代碼在 Census 檔案裡找不到（例如 NAICS 改版），到 `https://www.census.gov/retail/marts/www/timeseries.html` 或 MRTS 活頁簿確認新代碼。
2. 產生網頁：
   ```bash
   python3 .claude/skills/us-retail/scripts/build_dashboard.py --data retail/data/retail.json --out retail/output/retail_dashboard.html
   ```
3. 發布分享網頁（使用者要網頁時）：
   ```bash
   python3 .claude/skills/us-retail/scripts/build_dashboard.py --artifact --out <scratchpad>/retail_artifact.html
   ```
   用 Artifact 工具發布這個檔案（去掉 html/head/body 外殼的版本）；之前發布過就更新同一個網址。
4. 確認：總額、扣除汽車、扣除加油站、扣除汽車與加油站的「官方 1 位」欄要跟 Census 新聞稿 Table 2 一致（`marts_current.xlsx` 或 `https://www.census.gov/retail/marts/www/marts_current.pdf`）。2026-09（10/15 公布）驗證：總額 0.77→0.8、扣除汽車 0.90→0.9、扣除加油站 0.24→0.2、扣除汽車與加油站 0.25→0.2（未捨入 0.246）、16 個業別全部一致；13 個業別加總剛好等於總額。

## 網頁功能

- 「展開至 L0–L4」一鍵切換顯示階層；每列 ▸/▾ 可個別展開收合。
- 數值切換：MoM 兩位小數、MoM 官方一位小數、3 個月平均 MoM（近 3 個月幾何平均）、MoM 貢獻 pp、3 個月年化、3m/3m 年化（近 3 個月平均對前 3 個月平均，常用來看控制組對季度 GDP 的動能）、YoY、銷售額（十億美元）、MoM 修正 pp（有前次公布資料才出現）。
- 月份欄標 **A**（advance 預估值，最新月）與 **P**（preliminary 初值，前一月）。
- 占比 = 最新月銷售額 ÷ 總額；MoM 貢獻 pp =（本月 − 上月）÷ 上月總額 × 100，同層加總等於母項貢獻（例如 L1 五塊加總 = 總額 MoM）。
- MoM 上色：以 0.30%（約年增 4% 的名目趨勢）為中心，高於紅、低於藍，偏離 1.0 個百分點最深，套用在 MoM 2位、官方1位、3個月平均三種檢視；門檻在 template.html 的 `HEAT_CENTER`、`HEAT_FULL`。
- 進位邊界：兩位小數為 x.x5 時加點狀底線，官方一位小數取決於第三位。
- 同層業別預設按占比由大到小排序，可切回 Census 原順序。
- 標籤：`計算` = 控制組；`MRTS` = 只有 MRTS 有的細業別（最新月空白）。

## 分析時注意

- **名目值**：零售銷售沒有經過物價調整，加油站與汽車常因油價、車價波動。要看實質消費，需用 CPI 對應分項平減（可搭配 `us-cpi` skill）。
- 預估值（A）樣本小，下個月公布初值（P）、再下個月公布終值時會修正；Table 3 有平均修正幅度。修正看「MoM 修正 pp」檢視。
- 每年 4 月左右 Census 做年度基準修正（annual benchmark / revision），會改寫過去數年的金額與季調因子，所以一律重抓整段資料，不要只追加最新月。2025 年 4 月的基準修正起只含有雇員的企業（不含非雇主企業），與之前的數字口徑不同。
- 控制組沒有官方數值，市場預期與報導用的是同一個公式（總額扣除汽車、加油站、建材、餐飲）。Census 的總額是各業別季調金額的加總（間接季調），所以用金額相減不會有季調不一致的問題。
- YoY 用季調值（與 Census Table 2 相同），不是未季調值。
