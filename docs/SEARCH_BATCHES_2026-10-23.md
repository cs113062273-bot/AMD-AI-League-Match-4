# 2026-10-23：以搜尋回應為單位排除錯題結果

Later [search-anchor changes](SEARCH_ANCHORS_2026-10-23.md) supersede the all-weak fallback policy after new live evidence; the measurements below describe this earlier stage.

從三題既有外網失敗案例檢查當下的公開搜尋，均找到可讀來源（前四候選中分別 1、1、4 頁可讀）。也重現同一次查詢混入整批無關主題的結果，例如山丘高度題混入動物園、醫學史題混入停班停課、歌曲製作題混入股票討論。這是實際 HTTP 回應，不是推測的供應者失敗。

搜尋現在保留每個 provider/query 回應的邊界。如果至少一批結果有原查詢詞彙重疊，捨棄其他整批零相關的回應；相關回應中標題泛用的個別 URL 仍保留。如果各批都沒有重疊，保留既有弱結果與備援，不因這項修正直接清空結果。相關性仍沿用既有詞彙與失敗 host 粗估，不是語義或來源可靠性認證。

## 證據

- 受控 HTTP [before](../benchmarks/search-batches-20261023-before.json)／[after](../benchmarks/search-batches-20261023-after.json)：**1/3 → 3/3**，包含無關供應者回應、無關 rewrite 回應，以及全弱結果仍可保留的對照。相關批次中的 generic link 保持可用。
- 三題 [初次 live probe](../benchmarks/live-discovery-20261023.json) 與 [修正後 live capture](../benchmarks/live-discovery-20261023-filtered.json) 均保留；不同時間的搜尋內容有變化，不能直接把兩次 live 差異當因果比較。
- 將第二次抓到的相同 HTTP 回應凍結，讓 fbed467 與修正後 search 重播：[paired replay](../benchmarks/search-batches-20261023-frozen-replay.json)。三題均由 12 個 URL 變 8 個；前四個候選完全相同。原先可見結果合計排除 16 個無關 URL，另外保住 4 個原先被 12 筆上限擠掉、出自相關回應的 URL。這是候選品質／覆蓋證據，不是答案正確率。
- 既有 [檢索 7/7](../benchmarks/search-batches-20261023-discovery-regression.json)、[候選佇列與邊界 6/6](../benchmarks/search-batches-20261023-queue-regression.json) 保持通過，編譯與 whitespace 檢查通過。

抓到的搜尋原文與 hash 存在 `research/live-discovery-20261023/`，依既有 ignore 規則留在本機；tracked manifest 記錄每份 snapshot 的 SHA。重播程式 [replay_discovery_snapshots.py](../eval/replay_discovery_snapshots.py) 只讀這些回應，不連網、不呼叫模型，也不把 gold 傳入 production。

限制：若詞彙粗估誤判整批實際有用但無錨點的結果，可能損失召回；因此保留 mixed response 的 generic link 與全弱情況的回退。尚未進行廣泛外網答案評估或 AMD 驗證，也沒有重新製作／發布 image。
