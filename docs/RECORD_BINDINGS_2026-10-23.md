# 2026-10-23：名錄事件脈絡與衝突年份

接續 [原始欄位修正](RECORD_FIELDS_2026-10-23.md) 的兩個剩餘誤答。同一組八題、相同 case／fixture SHA，以 408426d 為 baseline，在同一個自有完整 Qwen3-4B session 比較。

## 改動

- 保留 h1 前的來源類別 banner，再按後續標題追蹤所屬小節，避免把獎項名稱丟掉，或借用兄弟小節。
- 對明確詢問獲獎年份／日期的記錄，若來源最近的具名獎項範圍與所問名稱完全沒有詞彙交集，排除該記錄。這是有限的事件不相容檢查；不是任意語義關係或別名解析。
- 緊湊記錄內的 p、div、span 只以完整記錄提供，避免子節點又被抽成無脈絡的年份來繞過綁定。具標題、表格、pre、dl 的內容仍沿用原解析方式；API signature 的獨立驗證保留。
- 同人物、同小節、同欄位且其餘文字相同的記錄出現不同值時回報衝突。以實際選中的記錄為準，低詞彙分數或更高排名的無關 metadata 都不能遮掉這項檢查。

## 完整 4B 結果

| 指標 | 408426d | 修正後 |
|---|---:|---:|
| 答案與來源均正確 | 6/8 | 8/8 |
| 原本答對的四個有答案案例 | 4/4 | 4/4 |
| 正確棄答 | 2/4 | 4/4 |
| 平均秒數 | 1.553 | 1.400 |
| 模型呼叫 | 15 | 12 |

錯獎項由錯答 1987 改成棄答；衝突年份由任選 1987 改為 `unresolved_conflict`。保留真實名錄題及其他正確答案，0 退步。原始 [paired report](../benchmarks/recordbinding-20261023-paired.json)、[comparison](../benchmarks/recordbinding-20261023-comparison.json) 均保留。

與前一輪 source_fields 合起來，同八題經兩次迭代由 4/8 → 6/8 → 8/8；兩次對照各自在同一 session 執行，但兩輪 session 不同，不跨 session 串接耗時或模型呼叫比較。Cap 1536、max_depth=0、budget=12、無搜尋。這些是已曝露的 reader 開發情境，不是外網或獨立 holdout 分數。自有模型已關閉，關閉後 GPU 1499 MiB。

## 獨立檢查與限制

[11 項受控 HTTP 檢查](../eval/diagnose_record_bindings.py) 使用會選實際年份、並一律回覆 supported 的服務，測試 deterministic source guards，而非 LLM 能力。包含 paragraph／ARIA row 變形、兄弟小節、不同人物、低分衝突與 API signature；[v2 before](../benchmarks/recordbinding-20261023-v2-before.json)／[v2 after](../benchmarks/recordbinding-20261023-v2-after.json) 為 **5/11 → 11/11**。原 pilot 的 baseline 10 項、after 11 項不對稱，保留但未混入這個比較。

既有 [日期／記錄結構 27/27](../benchmarks/recordbinding-20261023-structural-base.json)、[CPU 15/15](../benchmarks/recordbinding-20261023-core-regression.json)、[表格綁定 10/10](../benchmarks/recordbinding-20261023-table-regression.json)、[轉移 10/10 與變形 16/16](../benchmarks/recordbinding-20261023-transfer-regression.json)、[proof／HTTP 27/27](../benchmarks/recordbinding-20261023-proof-regression.json) 保持通過，編譯與 whitespace 檢查通過。

事件檢查限於可辨識的英文獲獎問法和具名來源標題；共享詞彙、縮寫／別名、不同措辭的矛盾、時間版本解析仍需進一步證據與語義驗證。沒有修改 gold、繞過 verifier、重跑完整 670 題、製作或發布 image。
