---
name: us-jolts
description: 收集並整理美國 JOLTS（職缺 Job openings、招聘、自願離職、裁員、總離職）產業別逐月水準與比率，產出可切換指標、展開/收合產業階層的互動網頁。Use when the user asks to update, collect, or analyze US job openings (JOLTS, 職缺, hires, quits, layoffs, labor turnover, 失業人數 / 職缺比).
---

# 美國 JOLTS 職缺與勞動流動

資料來源：BLS Job Openings and Labor Turnover Survey（JOLTS），季調後。每個產業 × 5 個指標（職缺 JO、招聘 HI、自願離職 QU、裁員與解僱 LD、總離職 TS）各抓水準（千人，`...L`）與比率（%，`...R`），共 280 條，另加 CPS 失業人數 `LNS13000000` 算「失業人數 ÷ 職缺」，以及 32 條 CES 就業人數做職缺 vs NFP 對照。
- 序列代碼：`JTS` + 產業 6 碼 + `00` + `00000` + `00` + 指標 2 碼 + `L`/`R`，例如 `JTS000000000000000JOL` 是總非農職缺水準。
- 產業階層依 BLS `jt.industry`：L0 總非農 → L1 民間 / 政府 → L2 超級產業（民間 10 個 + 聯邦、州與地方）→ L3 細產業。定義在 `series.json`，要增減產業或指標改那個檔即可。
- JOLTS 比 NFP 晚一個月（例如 11 月初公布 9 月），只有最新月是初值 P，下個月修正一次。

## 步驟

1. 抓資料（需要網路可連 `api.bls.gov`）：
   ```bash
   python3 .claude/skills/us-jolts/scripts/fetch_jolts.py --start 2025-01 --annual-from 2019 --out jolts/data/jolts.json
   ```
   - 有 `BLS_API_KEY` 環境變數時用 v2 API（一次 50 條，7 次請求）；沒有則用 v1（一次 25 條、13 次請求，每天 25 次額度、共用 IP 很容易用完）。
   - 若 API 回 `daily threshold ... reached`，代表免金鑰額度已滿，請使用者提供金鑰（不要叫使用者把金鑰貼在對話裡，請他設成環境變數）。
   - 腳本最後會列出最新月總非農各指標水準、比率與失業人數 ÷ 職缺，可直接引用；有缺資料的序列也會列出。
2. 產生網頁：
   ```bash
   python3 .claude/skills/us-jolts/scripts/build_dashboard.py --data jolts/data/jolts.json --out jolts/output/jolts_dashboard.html
   ```
3. 發布分享網頁（使用者要網頁時）：
   ```bash
   python3 .claude/skills/us-jolts/scripts/build_dashboard.py --artifact --out <scratchpad>/jolts_artifact.html
   ```
   用 Artifact 工具發布這個檔案，並傳 `url`: https://claude.ai/artifact/Kop8CZDuqe7wExvaQbjP62 更新同一個網址（不要建立新的）。
4. 確認：總非農職缺水準與職缺率要跟 BLS JOLTS 新聞稿一致。

## 網頁功能

- 頁首卡片：最新月總非農 5 個指標的水準、比率、MoM 變化，以及失業人數 ÷ 職缺（附 1、3、12 個月前的值）。
- 指標切換：職缺 / 招聘 / 自願離職 / 裁員與解僱 / 總離職。
- 數值切換：水準（千人）、MoM 變化（千人）、3 個月平均水準、比率（%）、比率 MoM 變化（pp）。
- 年度欄放最右邊：水準、3 個月平均、比率檢視顯示年平均；變化檢視顯示 12 月對前一年 12 月的變化（當年為 YTD，到最新月）。
- 「展開至 L0–L3」一鍵切換階層；每列 ▸/▾ 可個別展開收合。
- 職缺 vs NFP 對照（頁面下方）：每個產業過去 6 個月（以 JOLTS 最新月為準）各分一類。職缺與 NFP 都用 3 個月平均每月變化 (本月 − 3 個月前) ÷ 3，再除以 3 個月前水準換成 %；以顯示精度（職缺 1 位、NFP 2 位小數）達到門檻才算明顯，門檻預設職缺 ±1.5%/月、NFP ±0.05%/月，網頁上可調。
  1. 職缺明顯上升、NFP 增加 → 聘僱需求超級好
  2. 職缺不升（下降或持平）、NFP 增加 → 有成交
  3. 職缺上升、NFP 不變或下降 → 找不到人
  4. 職缺下降、NFP 下降；職缺持平、NFP 下降；職缺下降、NFP 持平 → 該行業慘淡
  5. 兩者都持平 → 變化不明顯
  NFP 對應的 CES 序列寫在 `series.json` 各列的 `ces`（多條時相加，例如運輸倉儲 + 公用事業、州 + 地方政府）。類別旁的數字是民間 10 個超級產業最新月落在該類的個數。
- 排名上色：只排 Total private 底下的 10 個 L2 超級產業，每月數值最高前 3 名橘色、最低 3 名綠色（以顯示精度比較，同值並列，比率檢視常會超過 3 個）。水準檢視不排名。

## 分析時注意

- 比率定義：職缺率 = 職缺 ÷（就業 + 職缺）；其他比率 = 該指標 ÷ 就業。
- 每年 3 月公布 1 月資料時會做年度修正（季調因子與 CES 基準），重抓整段資料而不是只追加最新月。
- 2025-10 美國政府關門，CPS 沒有 10 月失業人數，所以 2025-10 的失業人數 ÷ 職缺是空白。
- 自願離職率常被當作工資壓力的領先指標；裁員率則看勞動市場是否從「少招聘」轉為「主動裁員」。
