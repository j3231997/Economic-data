---
name: us-wages
description: 收集美國 CES 平均時薪（Average hourly earnings, all employees）產業別資料，從時薪水準算出兩位小數（unrounded）MoM，並與官方一位小數、3 個月平均、3 個月年化、YoY 並列，產出可展開/收合產業階層的互動網頁。Use when the user asks to update, collect, or analyze US average hourly earnings (AHE, 時薪, wage growth MoM, 薪資成長).
---

# 美國平均時薪 MoM

資料來源：BLS Current Employment Statistics（CES），全體員工平均時薪（All employees，data type `03`），季調後，美元。
- 產業階層與 us-nfp 相同，但以 Total private 為 L0（政府沒有時薪資料），並拿掉 BLS 沒有季調時薪的 Finance and insurance、Real estate、Private educational services（所以 Financial activities 是末端列，Private education and health 底下只有醫療）。定義在 `series.json`；`ai` 欄位沿用 NFP 的 AI 影響標示。
- **MoM**：(本月時薪 ÷ 上月 − 1) × 100，取兩位小數。BLS 新聞稿只公布一位小數，這裡的兩位小數就是市場說的 unrounded AHE。時薪本身只公布到美分，所以兩位小數已是公開資料能算到的最高精度。

## 步驟

1. 抓資料（需要網路可連 `api.bls.gov`）：
   ```bash
   python3 .claude/skills/us-wages/scripts/fetch_ahe.py --start 2025-01 --annual-from 2019 --out wages/data/ahe.json
   ```
   - 有 `BLS_API_KEY` 環境變數時用 v2 API（一次 50 條，2 次請求）；沒有則用 v1（一次 25 條，3 次請求，每天 25 次額度）。
   - 若 API 回 `daily threshold ... reached`，請使用者把金鑰設成環境變數（不要貼在對話裡）。
   - 腳本最後會列出民間總時薪近 6 個月的兩位小數與一位小數 MoM，可直接引用。
2. 產生網頁：
   ```bash
   python3 .claude/skills/us-wages/scripts/build_dashboard.py --data wages/data/ahe.json --out wages/output/ahe_dashboard.html
   ```
3. 發布分享網頁（使用者要網頁時）：
   ```bash
   python3 .claude/skills/us-wages/scripts/build_dashboard.py --artifact --out <scratchpad>/ahe_artifact.html
   ```
   用 Artifact 工具發布這個檔案，並傳 `url`: https://claude.ai/artifact/CWqCGD6vxvPiCCuPfG6buV 更新同一個網址（不要建立新的）。
4. 確認：Total private 的「官方 1 位」要跟 Employment Situation 新聞稿的時薪月增率一致。

## 網頁功能

- 數值切換：MoM 兩位小數、MoM 官方一位小數、3 個月平均 MoM（近 3 個月幾何平均）、3 個月年化、YoY、MoM 變化（美分）、時薪水準。
- MoM 上色：以 0.30% 為中心，高於用紅色、低於用藍色，偏離 0.5 個百分點（≥ 0.80% 或 ≤ −0.20%）為最深色；套用在 MoM 2 位、官方 1 位、3 個月平均三種檢視。門檻在 template.html 的 `HEAT_CENTER`、`HEAT_FULL`。
- 進位邊界標示：兩位小數剛好是 x.x5 時加點狀底線，代表官方一位小數取決於第三位。
- 年度欄（最右邊）：12 月對前一年 12 月的 %，當年為 YTD（未年化）。
- 「展開至 L0–L4」一鍵切換階層，預設 L2 超級產業；每列 ▸/▾ 可個別展開收合。AI 影響標示同 NFP。

## 分析時注意

- 時薪會跟 NFP 一起修正前兩個月（最近兩個月標 P），每年 2 月有基準修正，重抓整段資料。
- 平均時薪受組成效果影響：低薪產業（如休閒旅宿）就業大減時，平均時薪會被拉高，不代表個人薪資加速，解讀時搭配 NFP 產業別變化一起看。
- 細產業時薪波動大（單月 ±1% 常見），看趨勢請用 3 個月平均或 3 個月年化。
