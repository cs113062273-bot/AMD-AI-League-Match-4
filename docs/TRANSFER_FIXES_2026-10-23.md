# 2026-10-23：表格與敘述轉移修正

接續 [proof 第一版](PROOF_FIXES_2026-10-23.md)，新增名稱、欄位排列及關係敘述的 10 題轉移開發組。這批由同一作者設計，並不是獨立 unseen holdout。

## 修正與實測

- 按欄名找版本、數量、分類鍵、金額與主體，支援版本表和分類/費用表，取代僅讀 prose 的限制。
- 表格列綁定共用 `evidence.row_supported`，不再假定第一欄一定是識別值。複合與一般單值驗證都用同一規則，檢查快取保留有界行為。
- 支援明確的 belong to / fall under 分類關係，以及 carries/incurs/requires 某 fee 的數量子句。條件式、可能性及否定句不當作無條件 proof，仍須整題 semantic verification。
- 直接在同一列綁定產品名稱與金額時，不因多了一個 Category 欄就強迫做多餘 join；分類未知而需要跨頁時仍禁止退回部分答案。
- 複合時間欄必須是完整 clock/range，不能接受 `11:30?14:00` 這種不明格式。

| 指標 | 838b7ad | 修正版 |
|---|---:|---:|
| 答案＋必要來源 | 5/10 | 10/10 |
| 答案 | 6/10 | 10/10 |
| 平均 / p50 | 1.661 / 0.546s | 1.347 / 0.725s |
| p95 / max | 4.532 / 4.554s | 3.162 / 3.203s |
| 模型呼叫 | 16 | 14 |
| 最大 input / pruning | 980 / 3 | 631 / 0 |

兩側同權重、1024-token cap、20 秒 budget、max_depth=2、同 v2 cases/fixture SHA，各跑一次。p50 增加但均值下降，不能只展示有利時間指標。缺版本、不完整同列欄位、分類矛盾及不相容單位仍留白；既有敘述比較與單值控制保留。

原始 [before](../benchmarks/transfer-20261023-v2-before.json)、[after](../benchmarks/transfer-20261023-v2-after.json)。基準以隔離歷史 package 載入 838b7ad，並非比較不同權重。未過濾來源難度或挑多次最好成績。

## 測資編碼更正

第一次新增測資經 PowerShell stdin 傳遞時，時間範圍的 en dash 被轉成 `?`。已保留 [pilot](../benchmarks/transfer-20261023-before.json) 及原檔，另建立 [v2 cases](../benchmarks/transfer-20261023-v2-cases.json) 與 [v2 pages](../fixtures/transfer-20261023-v2.json)，只修正數字之間的被替代符號，沒有放寬別名、變更數值或偷偷覆寫 gold。v2 重新跑了雙側對照；上表不混用 pilot。

後續含 Unicode 的測資產生器應使用原生 UTF-8 檔案或 ASCII escape/codepoint，不再透過不明編碼的 shell literal 傳遞特殊符號。

## 最小回歸與限制

- [結構性對照](../benchmarks/transfer-20261023-structural.json)：同 10 題操作建構 5→10 通過；16 項列/欄排列、單值錯列及不明時間格式檢查全部通過。
- [既有 proof/HTTP 27 項](../benchmarks/transfer-20261023-proof-regression.json)、[binding 10 項](../benchmarks/transfer-20261023-binding-regression.json)、[CPU 15 題](../benchmarks/transfer-20261023-core-regression.json) 均保留。

這是 reader/proof 的有限轉移改善，不能當成真實網站或正式榜單成績。多來源 key 仍要求同 origin 與實體範圍；條件政策、任意多跳、跨 origin identity、單位換算仍待處理。模型程序均已關閉，沒有重建 image 或重新下載權重。
