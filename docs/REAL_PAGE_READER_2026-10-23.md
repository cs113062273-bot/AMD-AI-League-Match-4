# 2026-10-23：真實網頁的日期精度與名錄結構

從已曝露的 external-transfer100 失敗紀錄選四題，當日重新抓取其原始起始來源；四頁均 HTTP 200。保留完整 HTML 與凍結回播 fixture 在本機 `research/realpages-20261023/`（依既有 ignore 規則未納入 Git），[capture manifest](../benchmarks/realpages-20261023-capture.json) 記錄時間、URL、HTTP 狀態與 SHA。這是正確來源頁的 reader 開發評估，不含搜尋，也不是獨立 holdout。

## 改動

- 「Which month and year…」原本被解析為只問 year，因此模型正確複製完整日期後，反而遭型別檢查拒絕。新增明確的 month 精度；保留 literal 完整日期作為 raw/evidence，僅把已驗證的日曆日期投影為英文月名與年份。語義 verifier 仍須確認它是所問事件的日期。
- 也接受來源直接提供的月份與年份；缺年份、缺月份、無效日期、錯誤投影和截取無效日期的月份前綴均拒絕。只問年、完整年月日及時間長度的既有行為保持原樣。
- 緊湊的 article／ARIA row 記錄保留同一 DOM 容器內的欄位，避免年份與姓名被拆散。保留實際 document headings 作為記錄的語義脈絡；單次走訪標題與記錄，避免逐記錄回溯整個 DOM。

## 完整 4B 結果

基準為 c3d7e49；前後 case、fixture SHA 完全相同，cap 1536、max_depth=0、budget=12。未改 gold alias、來源或問題。

| 指標 | Before | Final |
|---|---:|---:|
| 原始嚴格答案與來源 | 1/4 | 2/4 |
| 額外報告：忽略答案大小寫、仍精確比對來源 | 2/4 | 3/4 |
| 平均秒數 | 1.688 | 1.934 |
| 最大 input tokens / pruning 次數 | 1526 / 3 | 1479 / 2 |

兩種評分分開保留：上游 gold 為 `LAGRANGE`，模型兩次都正確複製來源的 `Lagrange`。沒有把大小寫差異算成模型修正的成果。實際恢復的是任命日期的「月與年」答案；既有獎項年份與姓名答案保持。

名錄題仍未完成：selector 從棄答進步到選出同一筆姓名記錄的正確年份，但 semantic verifier 仍拒絕它與所問獎項的關係，最終維持空答案。沒有繞過驗證來增加分數。後續應處理記錄欄位／頁面獎項脈絡的關係證據。

[Before](../benchmarks/realpages-20261023-before.json)、[第一次修正](../benchmarks/realpages-20261023-after.json)、[Final](../benchmarks/realpages-20261023-final.json)、[並排比較](../benchmarks/realpages-20261023-comparison.json) 均保留。Final 之後僅擴充同義的 are/were/the 問法，這項由結構檢查驗證，未再重載模型。中間版本逐記錄回溯標題使平均延遲為 3.199s；final 改為單次走訪，仍比 baseline 慢，不能宣稱加速。自有模型程序每次皆已關閉，final 關閉後 GPU 為 1550 MiB；其他使用者工作未動。

## 有限驗證

- [日期／DOM 結構 24/24](../benchmarks/realpages-20261023-structural-v2.json)，含錯誤投影、無效日期與跨記錄負例。
- [代表性 CPU 15/15](../benchmarks/realpages-20261023-core-regression.json)、[表格綁定 10/10](../benchmarks/realpages-20261023-binding-regression.json)、[轉移結構 10/10 與欄位／主體變形 16/16](../benchmarks/realpages-20261023-transfer-regression.json)、[proof／HTTP 27/27](../benchmarks/realpages-20261023-proof-regression.json) 保持通過。
- Python 編譯及 diff whitespace 檢查通過。未重跑 670 題、製作 image、對外推送或提交。
