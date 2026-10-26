# 2026-10-25 存取層修正與實測

## 根因（已用實驗證實）

Wikimedia 對此專案的 HTTP 客戶端一律回 403，回應內容為
`Please respect our robot policy https://w.wiki/4wJS when crawling us.`
原因是 User-Agent 沒有聯絡方式。以前的 `Fetcher` 在狀態碼 ≥400 時丟棄 body 與標頭，
所以這個訊息從未被看到，Codex 之前以「繞路」機制處理 403。

存取探測（10 個網址，固定輸入，無模型）：

| 條件 | 200 | 備註 |
|---|---:|---|
| A：舊客戶端 | 0/10 | 8 個 Wikimedia 全部 403；Cambridge、Merriam-Webster 是 Cloudflare 挑戰頁 |
| B：Wikimedia 專用聯絡 UA | 8/10 | 兩個 Cloudflare 挑戰頁維持不可讀（沒有也不會去繞過） |

## 程式改動

- `agent/network.py`：≥400 時保留 body 前 300 字元與 `server`/`retry-after`/`x-cache`/`cf-ray`/`x-request-id`
  （事件欄位 `error_body`、`error_headers`）；`Accept-Language: en-US`；
  只對 Wikimedia 網域送 `ApertureRetrieval/1.0 (<APERTURE_CONTACT>) aiohttp`。
  聯絡方式只從環境變數 `APERTURE_CONTACT` 讀取，不寫進原始碼；其他網站仍用通用 UA。
- `agent/search.py`：Bing 加 `setlang=en-US&cc=US`；新增並行的 Wikipedia 標題搜尋
  （官方 API，用問題中的專有名詞片語組查詢）。
- `agent/engine.py`：`rank_passages` 加入以 IDF 加權的 BM25 項（`APERTURE_BM25_WEIGHT`，預設 8；
  設 0 可關閉）；大頁面解析改在執行緒中進行，讓截止時間在解析期間仍然有效。
- `agent/planner.py`："How old …" 一律判為數字（以前被 "when she married" 判成日期）。
- `eval/score_extended.py`：另列的輔助評分（不取代嚴格分數，不改 gold）。

**部署需要設定 `APERTURE_CONTACT`**（你擁有的信箱或網址）。沒設定時 Wikimedia 仍會 403。

## 成績（各列不合併、不互相替代）

| 資料 | 條件 | 嚴格答案 | 嚴格答案＋來源在 gold 內 | 備註 |
|---|---|---:|---:|---|
| fresh24（已曝光，開發） | 修前（記錄的首次） | 1/24 | 0/24 | 20/24 未進模型 |
| fresh24（開發重跑） | 全部改動後 | 10/24 | 8/24 | 擴充評分 12/24，答出時精確率 86% |
| independent60（凍結後只跑一次） | 全部改動後 | 12/60 | 7/60 | 擴充評分 19/60；答出 33 題，精確率約 58% |
| 離線回歸（見下） | — | — | — | 見下表 |

independent60：`benchmarks/independent60-20261026.json`（種子 20261026，從 720 個未曝光列抽樣，不給起始 URL）。
原始結果：`research/independent60-20261026-first/`。這 60 題現在已曝光，之後不可再當獨立題。

離線回歸（FakeWeb，搜尋關閉，自製頁面；只證明閱讀層沒有退步，不是答題能力）：
reader 12/12、proof 8/8、transfer-v2 10/10、dev 180/180、holdout 96/100、final-holdout 30/30、transfer-frozen 20/20，
合計 356/360，與修改前基線相同。中途一次 dev 179/180 是模型生成撞到 4 秒上限的暫時延遲，完整重跑為 180/180。

## 失敗分析（independent60，人工歸類）

- 27 題棄答：5 題 deadline、2 題 budget exhausted、4 題搜尋供應商隨機失敗（Bing 回無關結果、DDG 403、Yahoo 500，
  同一問題單獨重試曾成功）、其餘模型找不到證據。
- 約 10 題真正答錯並通過模型驗證：低品質來源（排行榜內容農場）、表格儲存格缺脈絡（颱風名稱欄）、
  引用同名但不同年份的來源。約 6 題是格式差異（彎引號、`&`/`and`、序數日期）。
- 3/60 超過 25 秒（最長 29.7 秒）。生產環境在 25 秒強制終止，這種情況會變成空答案。

## 未解決

- 無金鑰搜尋仍不穩（DDG 202/403、Yahoo 機器人驗證、Bing 偶發無關結果）；不繞過這些限制。
- 4B 模型的生成速度約 8–12 tok/s，預算耗盡常見。
- 驗證仍是同一個 4B 模型對同一批段落自我確認；沒有跨來源一致性檢查。
- 沒有做 AMD／官方介面驗收。任何成績都不能外推到隱藏測資。
