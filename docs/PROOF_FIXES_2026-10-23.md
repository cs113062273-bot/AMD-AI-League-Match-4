# 2026-10-23：複合答案與多來源證明

接續 [reader 修正](READER_FIXES_2026-10-23.md)。這次從真正的本機起始頁執行導航，完整 Qwen3-4B 的同題答案＋必要來源由 **4/8 → 8/8**，4 項改善、0 項退步、4 項平手。都是已曝光的開發案例，並非陌生題或正式賽事成績。

## 已完成

新增 `agent/proofs.py`，每個 premise 保留實際 source、locator、原文、值及角色，再執行有界的操作：

- **跨版本比較**：兩個指定版本都必須有明確數值與相同單位，依題目順序比較，保留兩個來源。不同值衝突、版本不符、預覽版或單位不相容不能拼成結果。
- **欄位組合**：將題目明列的兩個欄位投影自同一個已綁定 row，不能把 Electronics 的日期與 Glass 的時間湊在一起。例：`First Saturday of each month, 09:00–12:00`。
- **分類鍵映射**：例如 Book vendors→category B→$18。分類與金額都要有明確原文、相同 key、同 origin 及共同具名實體的標題範圍；兩個必要來源都輸出。有兩個分類或同 key 不同金額時拒絕選一個。

所有操作都先通過可執行的來源/欄位/版本/key 檢查，再把實際 premises 交給既有 4B semantic verifier，確認整個問題成立。不是讓模型自由生成答案後附一串 URL。答案可以由這些 literal premises 組合而成，不再要求整句出現在單一頁面；目前沒有任意程式運算或單位換算。

`Engine` 會等待完整 proof，缺欄位、缺版本或缺映射時繼續有界導航。服務失敗、拒絕、協定錯誤與證據不完整分開記錄，不回退到部分答案。CLI 外部仍是 `answer`＋`sources`，完整推導留在 trace。

## 實測

基準 revision 為 **0fe4e64**，固定了前兩輪 P0/P1。評測以隔離的歷史 Python package 載入基準，不複製 repo 或模型。兩側相同既有權重、backend instructions、1024-token cap、20 秒 engine budget、max_depth=2、搜尋關閉、同案例與 fixture SHA，各執行一次。

| 指標 | 基準 | 新版 |
|---|---:|---:|
| 答案正確 | 5/8 | 8/8 |
| 答案＋完整必要來源 | 4/8 | 8/8 |
| 非空回答 | 4/8 | 5/8 |
| 平均時間 | 2.915s | 2.009s |
| p50 / p95 / max | 3.315 / 4.675 / 4.835s | 2.238 / 3.302 / 3.545s |
| 模型呼叫 | 23 | 14 |
| 最大 input tokens / context pruning | 1011 / 1 | 675 / 0 |

改善不是全部變成拒答：比較與組合題新增正確回答；映射題保留 $18 並補齊兩個必需來源；矛盾分類題由亂選 $18 改為留白。缺版本、缺同列時段及兩個原本正確的單值控制均保留。

這組測量變快且呼叫變少；小樣本各跑一次，不能宣稱一般網站都加速。基準有一次 context pruning，新版更精簡的 proof 沒有 pruning，這也是實際執行條件的一部分，不能隱藏。

資料包括 3 個既有 SourceTrail 公開合成案例及 5 個新增、實作前凍結的診斷案例。新增案例仍由同一作者設計，不是獨立 unseen holdout。

原始資料：[基準](../benchmarks/proof-20261023-before.json)、[新版](../benchmarks/proof-20261023-after.json)、[paired ledger](../benchmarks/proof-20261023-summary.json)、[案例](../benchmarks/proof-20261023-cases.json)、[網頁](../fixtures/proof-20261023.json)。原始 harness 的 scope 文字沿用了 oracle-reader 描述；本輪實際使用 index 起點及 max_depth=2，ledger 已修正範圍說明，未改 raw score。

## 檢查與交付

- [最終 27/27](../benchmarks/proof-checks-20261023-complete.json)：20 項 proof/範圍/反例檢查，以及 7 項真 HTTP verifier 拒絕、503 和壞回覆檢查。表格 fault case 直接提供正確頁，隔離 verifier 與導航。
- [P0 16/16](../benchmarks/p0-after-proofs-20261023.json)：服務故障不放行錯答、錯套件不回錯實體。
- [CPU 舊題 15/15](../benchmarks/reader-regression-after-proofs-20261023.json)：代表性既有 parser/field/type fixtures 保留。
- [獨立 CLI](../benchmarks/proof-cli-20261023.json)：真 retrieval worker 與輸出檔保留完整兩來源；semantic endpoint 為受控服務，因此此項只證明程序與 serialization，不能冒充模型正確率。

完整模型對照後，另補強 checker 的全域矛盾、操作型別與預覽版限制，以及細分終態；這些最終小改由 27 項 CPU/HTTP 檢查覆蓋，沒有再完整跑 8 題 GPU。中間診斷報告仍保留，交付結果以上述 complete 檔為準。

啟動的 owned 模型均已關閉，沒有關閉使用者程式。未下載模型、未重掃大型權重 SHA、未恢復 tests/、未重測 670 題、未重建映像或正式提交。現有 image/source ZIP 仍是舊版。

重現：

```powershell
.\.venv\Scripts\python.exe eval/diagnose_reader.py --cases benchmarks/proof-20261023-cases.json --fixtures fixtures/proof-20261023.json --max-depth 2 --budget 20 --context-tokens 1024 --baseline 0fe4e64 --out benchmarks/proof-before-repeat.json
.\.venv\Scripts\python.exe eval/diagnose_reader.py --cases benchmarks/proof-20261023-cases.json --fixtures fixtures/proof-20261023.json --max-depth 2 --budget 20 --context-tokens 1024 --out benchmarks/proof-after-repeat.json
.\.venv\Scripts\python.exe eval/diagnose_proofs.py --out benchmarks/proof-check-repeat.json
```

前兩個需要空閒的模型 port 與足夠顯存，會關閉它們自己啟動的模型；預設保守顯存 gate 仍保留。本次第一輪因其他工作占用而未啟動模型，後來實際占用下降才完成對照。

## 邊界與下一步

這是第一版有界 proof，支援同列表格投影、明確 copular/數量子句的指定版本比較，以及 category/class/tier/group/band 的直接分類映射。一般自然語言關係、任意多跳、跨 origin 身分解析、單位換算、三個以上欄位/步驟與複雜有效日期政策仍未完成。不能為增加 coverage 放寬來源或 key 綁定。

下一步先用新來源、新敘述及欄位順序的凍結轉移題檢查 proof 是否過擬合，再處理真實網路的 discovery/evidence recall。原本 3072-token 的資源壓力、AMD 全模型、正式 evaluator 契約仍待驗證。
