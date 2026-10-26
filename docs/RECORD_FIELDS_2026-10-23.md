# 2026-10-23：名錄原始欄位已通過完整 4B 對照

接續 [原提案](RECORD_FIELDS_PROPOSAL_2026-10-23.md)。GPU 空出後，套用原 patch，在同一個自有 Qwen3-4B session 先跑隔離 fbed467，再跑提案。八題 case 與 fixture SHA 均與凍結提案一致；Git 在 Windows 套用時把 LF 轉為 CRLF，三個檔案正規化換行後的 SHA 仍與原提案完全相同。原 byte-level mismatch 有檢查，不是忽略程式差異。

改動只保留同一 article／ARIA row 上、能對上可見文字的受限 data-* 屬性，提供 source_fields 給 selector/verifier。未加入特定人名、年份或獎項規則，也未更動 verifier 標準。

| 指標 | fbed467 | source_fields |
|---|---:|---:|
| 答案與來源均正確 | 4/8 | 6/8 |
| 平均秒數 | 1.397 | 1.431 |
| 模型呼叫數 | 16 | 16 |

恢復既有真實名錄題與新名字的獎項名錄題，0 退步。錯姓名、錯事件維持棄答；隱藏 `data-year` 不等於可見年份時，仍只接受可見年份。

兩個舊問題仍存在：錯獎項及同一人兩筆衝突年份，baseline 與 after 都會誤答。這一輪未把它們當成通過，也未改 gold 或排除案例；接著修正事件脈絡與同欄位矛盾。

原始 [paired result](../benchmarks/recordfields-20261023-paired.json) 與 [comparison](../benchmarks/recordfields-20261023-comparison.json) 保留。Cap 1536、max_depth=0、budget=12、無搜尋；這是已曝露的 reader 開發案例，不是外網或 holdout 分數。自有 model tree 已關閉，關閉後 GPU 1548 MiB。

[結構 27/27](../benchmarks/recordfields-20261023-structural-applied.json)、[CPU 15/15](../benchmarks/recordfields-20261023-core-regression.json)、[proof／HTTP 27/27](../benchmarks/recordfields-20261023-proof-regression.json) 保持通過；語法與 whitespace 檢查通過。未建 image 或對外發布。
