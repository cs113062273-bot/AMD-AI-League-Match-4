# 短查詢保留更多原題內容

全程使用 CPU、保存的提示及六次公開搜尋 HTTP GET，沒有啟動模型或瀏覽器，也沒有使用付費 API。

## 問題與選擇

短查詢原本直接取第一個通過安全及主題門檻的提示。已曝光的 Activision 題目有兩個提示：`esports division announcement`、`activision blizzard esports launch`。前者合格但省略公司名稱，實際結果集中在其他電競組織。

現在在同一批合格提示中，選擇保留最多原題內容詞的一個；相同分數保留原順序。原有字數、長度、數字、URL、換行及最低主題重合限制不變；沒有合格提示時仍使用原本的引號標題後備。只影響原有的一次短查詢，不增加查詢、延長時限或更動模型作答／驗證使用的完整問題。

這是字面重合排序，不是命名實體辨識，也不能保證選到的提示保留所有重要語意。

## 實際探查與未採用方案

[提案探查](../benchmarks/hint-selection-20261023-probe.json)在修改生產程式前，比較 11 組已保存的模型提示。較多原題詞的方式改變 2 組，其他 9 組不變，包括先前姓名、Oyez 及認證日期的短查詢。

另外探查「優先保留 focus 欄位詞」的方式。它雖保留球員題目的 `full name`，卻將 `odd fellows hall architecture` 改成較籠統的 `eureka ca building style`，因此沒有採用。兩個方案涉及的三組前後查詢共六個 HTTP 回應均保存，沒有隱藏未採用方案的結果。

本次公開回應中：

| 題目 | 原短查詢 | 採用的短查詢 | 觀察 |
| --- | --- | --- | --- |
| 電競部門 | esports division announcement | activision blizzard esports launch | 原結果多為其他組織；新結果包含 Activision 官方新聞室、官網與公司介紹。尚未驗證其是否提供題目所需的宣布日期。 |
| 球員姓名 | juan guzmán full name | colombian player juan guzmán | 原前四項包含棒球與消歧義結果；新前四項集中於足球球員資料。尚未逐一驗證人物及出生年份。 |

這些是動態公開搜尋的檢索觀察；結果標題仍只能用於發現來源，不能當答案證據。

## 驗證

[CPU 與本機 HTTP 檢查](../benchmarks/hint-selection-20261023-controls.json)由 17/20 變成 **20/20**，3 個改善、0 個退步，涵蓋提示順序、同分穩定性、Unicode、不合格提示、一次短查詢後備、原搜尋已可用及時間不足時不額外查詢。

六個原始公開回應的 SHA256 均核對通過；用現行搜尋解析器重播得到相同候選清單。這不代表來源內容或答案已驗證。

既有回歸保持：[短查詢 9/9](../benchmarks/hint-selection-20261023-concise-regression.json)、[主題錨點 6/6](../benchmarks/hint-selection-20261023-anchor-regression.json)、[批次保留 3/3](../benchmarks/hint-selection-20261023-batch-regression.json)、[搜尋發現 7/7](../benchmarks/hint-selection-20261023-discovery-regression.json)、[候選佇列 6/6](../benchmarks/hint-selection-20261023-queue-regression.json)。

沒有新的模型或完整公開網路答題重跑，因此答案準確率維持原報告，不合併局部結果、不修改標準答案。
