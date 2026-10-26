# 2026-10-23：避免檢索候選提早耗盡

接續 [檢索恢復](DISCOVERY_FIXES_2026-10-23.md)。既有 external-transfer100 的失敗紀錄有「前四個候選全被擋住」情形，例如 simpleqa-3081；程式只保留前四個搜尋結果，後續候選即使存在也不再讀取。同一 URL 的不同標題又會重複占位。這輪以新的受控 HTTP 情境重現並修正流程，未宣稱原外網題目已答對。

- 搜尋結果與導航連結按 URL 去重，保留較高排名的標題。去重發生在候選截斷前，也避免選頁模型看到重複選項。
- 保存搜尋結果中尚未嘗試的候選，在下一輪不足四頁時補入；既有站內導航仍保有優先位置。
- 保持原頁數、深度、總時限、網路存取與語義驗證限制。到達頁數上限而無新頁可讀時停止，避免對舊內文再呼叫一次模型。

六個開發情境由 **2/6 到 6/6**：供應者重複 URL、前四頁 HTTP 403、前四頁可讀但無答案、頁數上限、深度上限、導航重複 URL。前後使用同一診斷程式 SHA；baseline 為 a4ac7f2，原始 [before](../benchmarks/discovery-queue-20261023-before.json)、[first after](../benchmarks/discovery-queue-20261023-after.json)、[final](../benchmarks/discovery-queue-20261023-final.json) 保留。

選答／驗證使用只讀取 literal phone span 的受控 HTTP 服務，不是實際 LLM。這測的是檢索覆蓋與邊界，不能當作外網準確率。[既有檢索 7/7](../benchmarks/discovery-queue-20261023-discovery-regression.json)、[proof/HTTP 27/27](../benchmarks/discovery-queue-20261023-proof-regression.json) 保持通過，語法與 diff whitespace 檢查通過。未建 image、推送或提交。
