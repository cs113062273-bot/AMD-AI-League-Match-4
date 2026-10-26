# 2026-10-23：正確證據下的型別、metadata 與表格綁定修正

這輪接續 [P0](P0_FIXES_2026-10-22.md)。同一組固定頁面的完整 4B 實測由 **9/12 → 12/12**，3 題由拒答變成正確答案，沒有對→錯。這是已曝光的 reader 開發診斷，不是陌生題、通用網路或官方競賽分數。

## 確認的根因與實作

1. **答案型別被背景文字蓋過。** 問 timeout，卻因後面的 stable version 4 被判成 version。現在先界定要問的欄位，再解析版本、實體等背景；常見排班出發時間獨立為 time，不再要求 calendar date。模糊的季節開始、明確問日期仍維持 date。
2. **合法期間格式遭拒。** 模型原本已抽到 90-day，duration 正規式只接受空白與複數單位。現在保留原文，同時接受單複數及連字號，不靠改 gold 或刪掉型別檢查換分數。
3. **JSON-LD/schema 與應用程式設定混成事實。** parser 保留 schema record 類型及 scalar 型別；同一套 eligibility 同時用於候選抽取、context 排序和最終驗證。schema type/context/id、導覽 scaffold 與未綁定主體的 embedded 設定不自動當一般事實。人物問題不能把布林值當人名，也不能從某欄位的 parent context 偷取另一個值。
4. **表格字串存在，不代表選對位置。** parser 保留 row、column、header、cells、section。驗證從真實 passage 讀這些資料，檢查明確要求的欄、已指明的 row key，以及同頁不同表格區段的角色；不能只靠候選自己宣稱綁定。表格查詢綁定依 page/query 快取，避免每個候選都掃整頁、重新引入平方級成本。
5. **輸出格式與導航條件。** 題目明列 enabled/disabled 等選項時，把選項送入 constraints，且只在相符的 literal span 上移除 by default 這種附語。導航另清除答案選項，避免用 enabled/disabled 去限制 URL 選擇。

原有 Article/Person/Product、真正的 WebPage 作者/標題、被明確詢問的設定值 false/0 均有保留檢查。不是把 JSON-LD 或 false 全面封鎖。

## 同條件完整模型實測

同一份既有 Qwen3-4B、RTX 4070 SUPER、相同案例及 fixture SHA、每側各跑一次。指定已知答案頁，停用搜尋與導航，隔離 discovery 與 reader；不把原站 index 改成答案頁的結果冒充完整檢索成績。兩個負例仍提供缺證據頁。

| 指標 | 修正前 | 修正後 |
|---|---:|---:|
| 答案＋正確來源 | 9/12 | 12/12 |
| 非空回答 | 7/12 | 10/12 |
| 非空回答中正確 | 7/7 | 10/10 |
| 錯→對 / 對→錯 / 平手 | — | 3 / 0 / 9 |
| 平均時間 | 1.153s | 1.539s |
| p50 / p95 / max | 1.211 / 1.483 / 1.622s | 1.674 / 1.982 / 2.018s |
| 模型服務完成呼叫 | 20 | 22 |
| 最大 input tokens | 990 | 1028 |

具體改善：

- BirchClient timeout：空白 → **8 seconds**。
- Wren Island weekday ferry：空白 → **06:20**。
- Juniper repair warranty：空白 → **90-day**。

三題修正前其實已由模型選中正確值，卻被錯誤型別/格式檢查拒絕。因此這證明 pipeline 修正有效，不代表模型推理能力突然提升。其餘表格、設定更名、條件預設、作者、產品、合法 false 與兩個拒答控制均保留。

平均時間增加約 0.386s，需如實列出；更多答案走完 semantic verification，呼叫量也有變化，單次各側測量不能隔離所有時間差原因。這輪沒有宣稱加速。

context cap 為 **1536**，不是 production 預設 3072；沒有 context pruning。修正後 Torch peak 約 8.04 GiB，整卡測後約 10704 MiB，owned 模型關閉後約 1805 MiB。沒有 503 或未完成的模型回覆。

原始證據：[before](../benchmarks/reader-20261023-before.json)、[after](../benchmarks/reader-20261023-after.json)。[案例](../benchmarks/reader-20261023-cases.json)與 [fixture](../fixtures/reader-20261023.json) 均已保存，production 不讀 gold。8 題來自既有 SourceTrail 公開合成頁面，4 題是作者自製控制；沒有新獨立 holdout 的宣稱。

## 最小退步檢查

| 檢查 | 結果 | 能證明什麼 |
|---|---:|---|
| 明確錯欄、錯列、錯區段、人物布林值，以及合法 metadata/false/0 | 6/10 → 10/10 | 直接把候選送進實際 parser/verify；4 項修復、0 項退步；不是模型得分 |
| 舊 CPU fixtures 代表性子集 | 15/15 → 15/15 | phone、price、JSON/JSON-LD、CSV/XML、日期、rowspan、版本、期間、metadata 等保留 |
| 前輪 P0 故障與 identity 診斷 | 16/16 | 沒有恢復服務故障放行、錯套件等問題 |
| 日期/時間/期間邊界 | 11 項通過 | 不把季節當 clock，不接受 23:20 pm、部分秒數或省略 pm 的片段 |

原始證據：[binding replay](../benchmarks/bindings-20261023-cached.json)、[CPU regression](../benchmarks/reader-regression-20261023.json)、[P0 regression](../benchmarks/p0-after-reader-20261023.json)。完整模型實測後僅收緊模糊 clock 規則、保留 WebPage 真實內容欄位、清除導航 choices、檢查 clock 邊界及加入表格綁定快取；最後的快取版本另確認 10/10 binding 通過，沒有為此重跑整套 GPU 診斷。

重現使用新輸出檔名：

```powershell
.\.venv\Scripts\python.exe eval/diagnose_reader.py --out benchmarks/reader-repeat.json
.\.venv\Scripts\python.exe eval/diagnose_bindings.py --out benchmarks/bindings-repeat.json
.\.venv\Scripts\python.exe eval/diagnose_reader_regression.py --out benchmarks/reader-regression-repeat.json
```

第一個命令會啟動及關閉它自己建立的模型程序；需空閒 8765 和足夠 GPU 記憶體。後兩個為 CPU，baseline 讀取 81d7a9e 的 parser/planner/candidates（這幾個模組在 P0 沒變），沒有複製 repo 或模型。沒有恢復 tests/、重測 670 題、訓練、模型下載、重掃權重 SHA 或容器重建。

## 剩餘限制

跨版本比較、日＋時段這類複合答案、兩個來源的映射證明、同條件不同值的語意衝突，仍未完成。當前模型仍以單一 literal span 作答，無法靠換成多個 sources 就取得 multi-hop 能力。

下一批應處理有來源與步驟的 evidence bundle/複合答案，再回到真正起始頁測完整導航與來源回收。原本 3072-token 長輸入資源壓力、AMD 完整模型、正式 evaluator 仍未驗證；現有 source ZIP/image 仍是舊版。
