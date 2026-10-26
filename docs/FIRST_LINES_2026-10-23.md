# 2026-10-23：保留明確換行，拒絕以摘要證明第一行

外網十二題的第一行請求，模型選中了 meta description 預覽。該預覽把多行合成一段，回傳了過長節錄，語意驗證仍支持。這次用自編、非歌曲文字重現，不以改寫上游答案來補分。

對明確要求文字／歌曲／詩／檔案等「first line」的問題，現在只使用具備來源行序的內容：純文字第一行、HTML BR 之前的文字，或 preformatted block 第一行。行內粗體等標籤不會分割行。隱藏內容先移除；DOM data-source-line 屬性不會成為行序證據。新增的 HTML 行 passage 在一般問題中不參與檢索，也不取代原有頁面事實。

來源行資訊會送給 selector，答案還必須完整等於該行：不能只取部分詞句、跨到下一行或用沒有行序的摘要。一般 description 問題仍可使用 metadata。

## 完整 4B 比較

同一個自有完整 Qwen3-4B BF16 服務，a701685 對比修正後；相同八題、fixture SHA，context cap 1536、max_depth 0、budget 12 秒，不搜尋。

| 控制題 | 修改前 | 修改後 |
|---|---|---|
| BR 與行內粗體，同頁有多行摘要 | 回傳兩行合併內容 | 完整第一行 |
| preformatted 文字 | 正確 | 正確 |
| 純文字檔 | 正確 | 正確 |
| 只有 metadata 預覽 | 不當作答 | 棄答 |
| 只有宣稱行號的 data 屬性，無明確換行 | 不當作答 | 棄答 |
| 隱藏內容在第一行之前 | 正確 | 正確 |
| 較長但仍在上限內的完整第一行 | 正確 | 正確 |
| 一般 description 請求 | 正確 | 正確 |

各案答案與來源符合預期 **5/8 → 8/8**，三項恢復、零退步。原本五個正確答案保留，另恢復一個完整第一行與兩個正確棄答。模型呼叫 16 → 12，平均 1.476 → 1.083 秒；兩個無行序證據的頁面不再呼叫語意讀取。這只是本組比較，沒有廣泛速度主張。

執行中程式雜湊不變；模型已停止，停止後 GPU 889 MiB。

- [凍結八題](../benchmarks/first-lines-20261023-cases.json)、[fixture freeze](../benchmarks/first-lines-20261023-freeze.json)
- [完整 paired 記錄](../benchmarks/first-lines-20261023-paired.json)、[摘要](../benchmarks/first-lines-20261023-summary.json)

## 最終檢查與邊界

[22 項最終 CPU 檢查](../benchmarks/first-lines-20261023-final.json) **6/22 → 22/22**，測量行序提取、完整／部分答案、沒有行序證據、過長行、前置空白行、一般 metadata 請求及原外網錯誤預覽。這是結構／guard 契約，不能作答題正確率。歷史版的答案接受檢查也實際使用其原有來源段落，不要求它具有新增的行 metadata。[診斷程式](../eval/diagnose_first_lines.py)

最初診斷以新 metadata 是否存在代替部分舊版答案接受檢查，該 pilot 的 1/20 已被修正方法取代；不可與最終結果直接比較。v2 的 6/20 已使用實際舊驗證器，最後再加入兩個空白行控制。

模型比較後另修正一個邊界：不再刪除 pre 開頭空白換行再把第二行標成第一行，空白第一行改為棄答。已保留當時 parser 原文與 hash，並逐頁確認八個模型比較輸入在精修前後解析結果完全相同：[等價檢查](../benchmarks/first-lines-20261023-blank-refinement.json)。兩個新增空白行案例由最終 CPU 診斷覆蓋，沒有重複載入 GPU。

保留 [CPU 15/15](../benchmarks/first-lines-20261023-regression.json)、[proof／HTTP 27/27](../benchmarks/first-lines-20261023-proofs.json)、[欄位綁定 10/10](../benchmarks/first-lines-20261023-bindings.json)、[名錄 HTTP 11/11](../benchmarks/first-lines-20261023-records.json)、[方位 28/28](../benchmarks/first-lines-20261023-directions.json)、[P0 16/16](../benchmarks/first-lines-20261023-p0.json)、[selector 邊界 10/10](../benchmarks/first-lines-20261023-selector.json)。編譯與 whitespace 檢查通過。

本輪沒有重新評分或重跑原外網歌曲題，僅確認原錯誤預覽不再是合格證據。上游答案、來源及首次十二題結果未改。HTML 視覺排版造成的自動折行、沒有明確換行的段落、空白第一行、超過答案長度上限的行、任意第 N 行與多文字區塊的語意主體仍有限制；沒有宣稱一般排版理解或外網正確率已達 8/8。
