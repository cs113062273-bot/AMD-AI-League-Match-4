# 2026-10-23：表格投影優先使用完整欄名

[完整姓名路由修正](FULLNAME_2026-10-23.md) 的控制題留下了一個既有問題：「first name＋email」有明確 First name 欄，卻因 Name 欄也共用 name 詞而被當成歧義。同樣情況也會發生在 Departure time 與泛用 Time 欄。

投影現在先找正規化後完整相符的欄名；沒有完整相符時才沿用原本的部分詞彙匹配。提案與獨立驗證共用同一個欄位選擇函式，避免提案選對欄、驗證卻接受另一個共用詞彙的欄位。重複的完整欄名仍是歧義；沒有完整相符時，複數部分匹配也仍拒絕。日期／時間別名沿用既有 field_words，沒有新增姓名切分、時間推算或自由運算。

## 完整 4B 比較

相同四題、fixture SHA、同一個自有完整 Qwen3-4B BF16 服務，以 eed167d 作 baseline；context cap 1536、max_depth 0、budget 12 秒，無搜尋。

| 控制題 | 修改前 | 修改後 |
|---|---|---|
| First name＋email，旁有 Name 欄 | 棄答 | 正確投影並通過語意驗證 |
| Departure time＋platform，旁有 Time 欄 | 棄答 | 正確投影並通過語意驗證 |
| 重複 First name 欄 | 棄答 | 棄答 |
| 只有 Name，沒有獨立 First name | 棄答 | 棄答 |

答案與來源精確符合 **2/4 → 4/4**，兩項恢復、零退步。平均 0.006 → 0.225 秒，模型呼叫 0 → 2：原本不完整的 proof 現在有兩次成功語意驗證，不是速度提升。執行前後程式雜湊相同，模型已停止，停止後 GPU 1025 MiB。

- [凍結四題](../benchmarks/projection-fields-20261023-cases.json)、[freeze](../benchmarks/projection-fields-20261023-freeze.json)
- [完整模型記錄](../benchmarks/projection-fields-20261023-paired.json)、[摘要](../benchmarks/projection-fields-20261023-summary.json)

這是已暴露案例與自編表格的 proof 開發驗證，不能稱為新外網正確率。前一輪七題留下的 name-email 在本輪以相同頁面單獨驗證恢復，但沒有重跑全部七題，也不拼接兩輪數字宣稱新 7/7。首次十二題外網結果仍是答案 4/12、joint 2/12。

## 獨立檢查

[八項最終 CPU 檢查](../benchmarks/projection-fields-20261023-final.json) 同輸入 **6/8 → 8/8**。除兩個正向投影外，包含重複完整欄、部分欄位歧義、缺少欄位、重複使用同一欄，以及逐字正確卻取自泛用 Name／Time 欄的偽造 proof。兩版驗證器都實際檢查這些偽造 proof；不以沒有提案替代驗證。[診斷程式](../eval/diagnose_projection_fields.py)

保留 [proof／HTTP 27/27](../benchmarks/projection-fields-20261023-proofs.json)、[transfer 10/10 與 metamorphic 16/16](../benchmarks/projection-fields-20261023-transfer.json)、[欄位綁定 10/10](../benchmarks/projection-fields-20261023-bindings.json)。編譯與 whitespace 檢查通過。

原本部分詞彙匹配的語意限制仍存在；即使有唯一完整欄名，也仍需同列主體綁定、逐字值、運算驗證及獨立語意檢查。本輪沒有新增對任意表格或跨頁關係的正確性保證。地理題把「附近」當「西側邊界」的誤判尚待處理。
