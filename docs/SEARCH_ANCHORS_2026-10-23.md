# 2026-10-23：單一問句詞不足以認定搜尋成功

[首次不重疊 12 題評估](DISJOINT12_2026-10-23.md) 暴露三個失敗：姓名題走進 first 字典、球隊題走進 two 字典、日期題走進 day 字典。原搜尋相關性把 `entity_terms` 中任何一個詞的重疊視為成功，因此不再嘗試完整備援。若各備援也失敗，原策略仍把全弱結果交給內容讀取。

現在，多詞查詢至少需要兩個查詢詞重疊，才能把一批結果認定為有主題錨點；單詞主題仍只需一個詞，精確底線識別字仍可單獨成立。相關批次中標題為 More details 的個別連結繼續保留。所有可用備援都沒有錨點時，回傳空清單，避免把明顯不同主題的 URL 當成最後來源。頁數、深度、時間與原有 provider 邊界不變。

## 證據

- [六項受控 HTTP 最終檢查](../benchmarks/search-anchors-20261023-final.json)：同輸入 c052c78 **2/6 → 6/6**，四項恢復、零退步。涵蓋 first/two/day 誤命中、全無關回應應為空、單詞主題與精確程式識別字。[診斷程式](../eval/diagnose_search_anchors.py)
- [三題實際搜尋 capture](../benchmarks/search-anchors-20261023-v2-live.json)：重用首輪 trace 的未驗證搜尋 hints，沒有模型推論；嘗試備援後，均無相關候選，也沒有再抓取無關內容頁。
- [相同實際 HTTP 回應的 paired replay](../benchmarks/search-anchors-20261023-v2-replay.json)：c052c78 各回傳八個 URL，修改後各為零，合計排除 24 個錯題候選。這是固定回應的檢索判斷證據，不是答案分數。snapshot 與 SHA 在 live manifest 中，原文留在忽略版控的 research。
- [先前三題可用查詢的相同回應重播](../benchmarks/search-anchors-20261023-old-query-replay.json)：高度、Laennec、作曲者各八個候選與排序完整保留，沒有任何 URL 損失。
- [discovery 7/7](../benchmarks/search-anchors-20261023-v2-discovery.json)、[queue／資源邊界 6/6](../benchmarks/search-anchors-20261023-v2-queue.json)、[batch 3/3](../benchmarks/search-anchors-20261023-v2-batches.json)、[proof／HTTP 27/27](../benchmarks/search-anchors-20261023-proofs.json) 通過；編譯與 whitespace 檢查通過。

batch 診斷中的全弱保留案例已明確改為「全無關應回空」，這是刻意改變的政策；舊版三項結果不可冒充同一組修正前後比較。其餘 mixed batch 的 generic link 保留規則不變。

## 未採用的嘗試

曾試將 hints 放到原 query 前方。[pilot 受控檢查](../benchmarks/search-anchors-20261023.json) 通過，但[實際搜尋](../benchmarks/search-anchors-20261023-live.json) 仍回傳購物中心與停班停課等錯題結果。因此已撤回排序改動；最終只保留較嚴格的錨點與空結果判定。pilot 檔案保留各自 production hash，不能和 v2 混成同一測量。

## 限制與下一步

這會降低單一詞碰巧相符的召回；實際有用但僅帶一個查詢詞的獨立批次，也可能被判為弱。來源相關性仍是粗略詞彙檢查，不是語意或可靠性認證。三個正向重播未退步，只能支持這個窄範圍，不能證明廣泛無損。

本輪沒有修好搜尋供應者本身的錯題回應，也沒有取得三題的新答案。12 題首次嚴格答案 4/12、joint 2/12 保持原結果。後續優先修正 `first and last name` 被當成兩欄表格 proof 的路由問題，並繼續尋找可讀、真正相關的來源；另有地理方位誤答與過長答案待處理。
