---
name: us-gdp
description: 拆解美國 GDP 支出面分項（BEA NIPA）：PCE（商品／服務細項）、民間投資（設備、智財、建築、住宅、存貨）、淨出口（商品 end-use／服務）、政府，算出季增年率（兩位小數與官方一位）、對 GDP 成長的貢獻、YoY、占比、金額與前次公布的修正，最上方可切換實質 Real／名目 Nominal，實質模式在最左邊加上亞特蘭大聯準 GDPNow 對最新一季的分項預估，產出可展開/收合分項階層的互動網頁。Use when the user asks to update, collect, or analyze US GDP components, contributions to GDP growth, GDPNow, core GDP / final sales to private domestic purchasers, 美國 GDP 分項, GDP 貢獻.
---

# 美國 GDP 支出面分項拆解

資料來源（都不需要 API 金鑰）：
- **BEA NIPA 季資料平面檔** `https://apps.bea.gov/national/Release/TXT/NipaDataQ.txt`（約 35 MB，所有季度 NIPA 序列，格式「代碼, 期間, 值」）。HTTP `Last-Modified` 當作 BEA 檔案日期，用來推定最新一季是 advance（季末後 ≤45 天）／second（≤75 天）／third。推錯時用 `--estimate A|S|T` 指定。
- **GDPNow 活頁簿** `https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/gdpnow/GDPTrackingModelDataAndForecasts.xlsx`（約 11 MB）：`ContribHistory`（各分項對 GDP 貢獻）、`TrackingHistory`（各分項季增年率）是目前追蹤季度每次更新的歷史，`TableCont` 提供每次更新對應的資料公布名稱。
- 階層定義在 `series.json`：GDP → PCE（商品→耐久／非耐久→細項；服務→家庭服務細項＋非營利機構）、國內民間投資（固定投資→非住宅〔建築、設備、智財細項〕、住宅；存貨變動）、淨出口（出口／進口→商品 end-use 六類＋服務）、政府（聯邦→國防／非國防；州與地方）。最終銷售、**對民間國內購買者的最終銷售（核心 GDP = PCE + 民間固定投資）** 是 `"special": true` 的斜體列。
- 欄位：`nom`／`real` = 名目（當期美元）與實質（2017 連鎖美元）序列代碼；`pct` = BEA 公布的實質季增年率（1 位小數）；`ry` = BEA Table 1.1.2 的官方貢獻（2 位小數）；`minus` = 進口子樹（以負號計入 GDP）；`gdpnow` = GDPNow 活頁簿的列鍵（標籤前的行號，或標籤本身）。

## 步驟

1. 抓資料（需要網路可連 `apps.bea.gov`、`www.atlantafed.org`）：
   ```bash
   python3 .claude/skills/us-gdp/scripts/fetch_gdp.py --start 2022Q1 --out gdp/data/gdp.json
   ```
   - 只用 Python 標準函式庫。終端最後列出最新一季實質 GDP 兩位小數年率、主要分項貢獻與 GDPNow 最新值，可直接引用。
   - **實質貢獻**：有 `ry` 的列用 BEA 官方值。其餘細項用 BEA 精確 Fisher 公式（NIPA Handbook 第 4 章）自算：
     `C_i = 100 × (p_i,t / P_t + p_i,t−1) × (q_i,t − q_i,t−1) / Σ_j (p_j,t / P_t + p_j,t−1) × q_j,t−1`，乘 `((1+g)^4 − 1)/g` 年化。
     BEA 季資料另有未公開的調整，所以公式值與官方會差幾 bp（終端會印出最近 8 季的最大差距），細項最後把差額依上季名目金額比例分攤，讓子項加總 = 官方母項。網頁上自算的貢獻以斜體顯示。
   - **名目貢獻** =（本季 − 上季）÷ 上季名目 GDP × 100 × 年化因子 `(V^4 − 1)/(V − 1)`，所有分項精確加總 = 名目 GDP 季增年率。
   - **GDPNow** 只在追蹤季度比 BEA 最新一季新時寫入（BEA 公布初估當天 GDPNow 會換到下一季）。GDPNow 只有 13 個分項；非住宅、固定投資、GPDI、PCE 等加總列與最終銷售也有，細項留白。
   - **前次公布（prior vintage）**：用「最新一季 + GDP 近 6 季名目與實質金額的雜湊」當版本；`--out` 已存在而版本不同時，舊檔存進 `prior`，網頁才有「貢獻修正 pp」。所以每次更新都寫到同一個檔案，不要先刪掉舊檔。
   - `WARNING: no data for ...` 表示 BEA 改了序列代碼：到 `https://apps.bea.gov/national/Release/TXT/SeriesRegister.txt` 用 `TableId:LineNo` 找新代碼（例如 T10105 是名目、T10106 是實質、T10101 是成長率、T10102 是貢獻）改 `series.json`。`WARNING: GDPNow rows not found` 表示 GDPNow 改了列標籤，修改 `gdpnow` 鍵。
2. 產生網頁：
   ```bash
   python3 .claude/skills/us-gdp/scripts/build_dashboard.py --data gdp/data/gdp.json --out gdp/output/gdp_dashboard.html
   ```
3. 發布分享網頁（使用者要網頁時）：
   ```bash
   python3 .claude/skills/us-gdp/scripts/build_dashboard.py --artifact --out <scratchpad>/gdp_artifact.html
   ```
   用 Artifact 工具發布這個檔案（去掉 html/head/body 外殼的版本）；之前發布過就更新同一個網址。
4. 確認：實質 GDP 的「官方 1 位」要等於新聞稿；PCE、固定投資、存貨、淨出口、政府的貢獻要等於 Table 1.1.2。2026-11 驗證（2026Q3 advance，檔案日期 11/4）：實質 GDP 3.37→3.4；貢獻 PCE 2.52、GPDI 3.27（固定投資 1.66＋存貨 1.61）、淨出口 −3.32、政府 0.90，加總 3.37；核心 GDP（PCE＋固定投資）4.18。名目 GDP 5.61% = 4.01 + 3.99 − 4.22 + 1.83。GDPNow 2026Q4（11/9）3.48%，與 Atlanta Fed 網站一致。

## 網頁功能

- **最上方「口徑」單選：實質 Real／名目 Nominal**，同一張表切換；展開狀態、數值檢視、排序切換後保留。
- **實質模式在最左邊（占比之後、最新一季之前）加一欄黃色 GDPNow**，顯示對下一季的最新預估（貢獻、季增年率檢視才有數字）；滑鼠移到數字上可看每次 GDPNow 更新的數值、觸發的資料公布與較前次變化。名目模式沒有 GDPNow（它只預估實質）。
- 數值切換：對 GDP 貢獻 pp（GDP 列顯示成長率）、季增年率兩位小數、**季增年率官方一位（預設）**、YoY、占 GDP 比重、金額（十億美元）、貢獻修正 pp（有前次公布資料才出現）。
- 最新一季標 **A**（advance）、**S**（second）、**T**（third）。
- 「展開至 L0–L6」一鍵切換顯示階層；每列 ▸/▾ 可個別展開收合。預設 L2。
- 上色：貢獻以 0 為中心（實質 ±1 pp、名目 ±1.5 pp 最深）；成長率以趨勢成長為中心（實質 2%、名目 4.5%，±5 個百分點最深）。門檻在 template.html 的 `HEAT`。
- 進位邊界：季增年率兩位小數為 x.x5 時加點狀底線。
- 同層分項預設照 BEA 原順序，可切成占比大→小。

## 分析時注意

- **存貨與淨出口波動大、常互相抵銷**（例如進口提前搶貨時進口大增壓低 GDP，同時存貨增加墊高 GDP）。看需求面趨勢用「對民間國內購買者的最終銷售」（核心 GDP）。
- 進口在 GDP 裡是減項：進口成長為正時貢獻為負。
- 存貨變動、淨出口是差額（流量的變化），沒有成長率，只看貢獻。
- 實質細項的連鎖美元不具可加性，所以實質「占比」一律用名目金額。
- GDPNow 是模型即時預估，不是官方數字；它在 BEA 公布前會隨每筆月資料（零售、ISM、貿易、營建、耐久財等）更新，滑鼠提示可看哪筆資料推動了變化。
- 每次估計（advance → second → third）與每年 9 月左右的年度修正都會改寫過去幾年的資料，所以一律重抓整段。
