# 2026-10-23：有錨點的簡短主題備援與十二題外網重跑

搜尋頁回顯了完整送出的 query，但實際結果常是不同主題。九個 Bing 查詢形式探測（原詞、短提示、加引號）仍未改善，沒有把結果錯怪為用戶端少送了 query。多個其他公開入口也分別遇到空結果、redirect loop、429 或 captcha；未處理挑戰，也未改用外部推論服務。

DuckDuckGo Lite 的簡短主題 query 則取得相關連結：人物資料、原刊物案件文章及專輯資料。這些 query 僅由原問題或已保存的未驗證模型 hints 形成，沒有使用 gold 答案或替代來源 URL。

## 有限改動

只有標準供應者的原搜尋沒有相關結果、且 query 剩餘時間大於七秒時，在原 RSS／Lite 備援同批最多增加一次簡短 Lite 查詢。hint 必須短、無 URL／數字／換行，並至少與原主題兩詞重疊（單詞主題為一詞）；排除 first、name、day 等泛用問句詞。沒有合格 hint 時，可用原問題中的引號標題加最多兩個上下文詞。最多 120 字元／十詞，仍受既有 provider、相關批次、頁數與整體 deadline 限制。

簡短 query 只影響探索，reader 與 verifier 使用原問題，不能用 hint 填答案。原搜尋已有相關結果時不增加這個請求。挑戰頁視為沒有結果，不解題或重試繞過。

## 搜尋證據

- [受控實際 HTTP v2](../benchmarks/concise-discovery-20261023-http-v2.json)：**7/9 → 9/9**，恢復有錨點 hint 與原文引號兩項；測試無關提示、泛用詞、數字、URL、已成功搜尋、低 budget 及簡短回應仍無關時不接受。最初 pilot 有診斷 query 與斷言錯誤，7/9 的 after 不是最終結果，已保留並以 v2 取代。
- [實際原始 provider 探測](../benchmarks/query-forms-20261023-providers.json)、[三個簡短 query 探測](../benchmarks/query-forms-20261023-concise.json) 僅證明當時來源探索可用，不能推成答案正確率。不同時間有變動；案件題初次成功、整合執行卻遇到 202 挑戰頁，失敗也保留。
- [共用回應 capture](../benchmarks/concise-discovery-20261023-live-paired.json) 及[固定回應重播](../benchmarks/concise-discovery-20261023-replay.json)：人物與專輯兩題各 **0 → 8** 個主題候選，案件題 **0 → 0**。baseline 與 current 共用初始事件、已抓取回應快取，另外保存兩種演算法請求的聯集；離線 paired replay 都有完整回應，不把先後執行當速度比較。
- [先前三題正向 query 重播](../benchmarks/concise-discovery-20261023-old-replay.json)：候選各 **8 → 8**，全部排序保留。
- [discovery 7/7](../benchmarks/concise-discovery-20261023-discovery.json)、[queue 6/6](../benchmarks/concise-discovery-20261023-queue.json)、[anchors 6/6](../benchmarks/concise-discovery-20261023-anchors.json)、[batch 3/3](../benchmarks/concise-discovery-20261023-batches.json) 保留；編譯與 whitespace 檢查通過。

## 實際十二題重跑：沒有新增正確答案

同一份原十二題、答案別名、來源集合與 all-returned-source 評分規則均未變；執行前另存 [repeat protocol](../benchmarks/external-disjoint12-20261023-repeat-protocol.json)。完整 Qwen3-4B BF16、context cap 1536、budget 24 秒、depth 2、實際搜尋與 browser，和首輪設定相同。資料已暴露，這是回歸，不是新 holdout。

| 指標 | 首次 | 此次重跑 |
|---|---:|---:|
| 答案精確符合 | 4/12 | 4/12 |
| 答案＋來源同時符合 | 2/12 | 2/12 |
| 有回答 | 7/12 | 5/12 |
| 平均秒數 | 9.378 | 10.552 |
| 模型呼叫 | 37 | 32 |

沒有答案或 joint 的新勝／退步。先前地理錯誤答案、過長節錄改為棄答；這是減少不當作答，不能說正確率或覆蓋提高。橋長字串仍與範圍描述 gold 不同，兩題正確答案的來源仍不在 gold 集合，原評分不放寬。外網回應變動、期間累積多個修正，這不是固定輸入的因果比較或速度改善。

[完整 repeat](../benchmarks/external-disjoint12-20261023-repeat.json)、[比較摘要](../benchmarks/external-disjoint12-20261023-repeat-summary.json)。程式前後雜湊相同，全部十二份 capture SHA 已核對、無容量漏存，模型已停止，停止後 GPU 898 MiB。

重要的新發現：這次六題搜尋提示沒有完成，五次 model_deadline、一次 TimeoutError。服務 request trace 顯示部分 expansion 在約 3.7 秒產生三十多 token 後被 deadline 中止。沒有提高全域 timeout 或恢復部分 JSON；下一步應縮短模型 expansion 輸出，驗證能否在原預算內形成有效提示。短查詢的來源覆蓋潛力，尚未轉成這次端到端的新答案。
