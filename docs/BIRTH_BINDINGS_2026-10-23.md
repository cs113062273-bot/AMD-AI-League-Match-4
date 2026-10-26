# 出生年份採用實際欄位綁定

這一步使用 CPU、解析器與本機 HTTP 語意服務替身，沒有載入模型、使用 GPU、啟動瀏覽器或呼叫公開 API。

## 重現的問題

人物資料的年份檢查原本依靠證據文字中最近的事件詞，出現兩個相反錯誤：

- `name: Mira Vale, birthDate: 1998-03-04` 被拒絕，因為 CamelCase 的 `birthDate` 沒有被當成獨立的 birth 詞。
- `name: Mira Vale, Born: 1970, lastUpdated: 1998` 卻能通過「誰出生於 1998」的必要檢查，因為更新年份附近只有 Born 事件詞。

另有巢狀資料問題：父資料 Rowan 的 `Born: 1998` 仍出現在子資料 Mira 的展示脈絡中。解析器已在新人物邊界清掉繼承的 bindings，但文字後備檢查又讀進了父資料的出生年。

## 修正

對單一出生年份約束，若來源本身有結構化出生日期／年份欄位，就優先使用這些欄位：`birthDate`、`dateOfBirth`、`birthYear`、`yearOfBirth`、`Born`、`DOB`，大小寫、空格及底線沿用既有鍵名正規化。

每個已綁定出生欄位都必須只包含題目要求的同一年，且值必須實際出現在選定的證據段落中。空白、未知、錯誤年份、日期範圍及相互衝突的出生年份不會借用其他欄位補足。只檢查所需年份，沒有將年份推定成完整出生日期。

JSON、JSON-LD 及 embedded JSON 缺少出生日期欄位時，文字後備只使用現有 bindings 所保留的資料範圍及該欄位自己的 literal value，避免重新借用另一個具名父資料。普通敘述仍使用既有規則，本地傳記內容也保留可用性。

這是來源欄位與年份的必要檢查；人物身分、完整姓名及語意仍需獨立驗證。沒有將本地通過直接視為模型答對。

## 驗證

[最終固定 51 個 CPU／實際本機 HTTP 檢查](../benchmarks/birth-bindings-20261023-v3.json)從 **30/51 到 51/51**，21 個改善、0 個退步。涵蓋出生欄位命名、日期及年份、錯誤更新年、欄位衝突、父子人物範圍、傳記文字、來源未顯示日期及無日期約束的問題。

HTTP 替身會選擇實際姓名文字並一律回覆 supported，用來隔離獨立來源檢查。正例仍經過 select 與 verify；錯誤年份／人物範圍會在呼叫語意 verify 前被擋下。這不是模型或公開網路準確率。

先前的 [47 個檢查 pilot](../benchmarks/birth-bindings-20261023.json)及 [51 個檢查 v2](../benchmarks/birth-bindings-20261023-v2.json)保留：它們揭露了父資料透過 section 再次進入年份檢查的漏洞。v2 的長傳記控制另受到既有「Who 問題不得截取 JSON scalar」規則阻擋；最終改用明確詢問完整姓名的問題，驗證長傳記的年份後備且不改動該 scalar 規則。比較數字以最終相同 51 個檢查為準。

既有回歸保持：[年份約束 41/41](../benchmarks/birth-bindings-20261023-year-regression.json)、[代表性解析 15/15](../benchmarks/birth-bindings-20261023-reader-regression.json)、[組合證據 27/27](../benchmarks/birth-bindings-20261023-proof-regression.json)、[段落欄位 19/19](../benchmarks/birth-bindings-20261023-field-regression.json)、[資料範圍 11/11](../benchmarks/birth-bindings-20261023-record-regression.json)。

這個修改尚未把 HTML 的相鄰姓名／出生日期列聚合成資料範圍。實際球員頁的完整姓名段落仍缺少同段年份；後續需保留可靠 DOM 範圍，不能直接借用附近日期。整體答題分數維持原報告。
