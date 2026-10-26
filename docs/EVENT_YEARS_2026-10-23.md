# 2026-10-23：指定事件年份必須有局部來源依據

縮短搜尋提示後，原外網姓名題找到與 gold 相同的姓名，但所選來源只說兩人已婚，沒有題目指定的 1985 年。舊版僅在有年份且不符時拒絕，因此完全缺少年份的來源會通過，獨立語意 verifier 也接受了它。本輪保留原始錯誤選擇，沒有把 gold 姓名當作充分證據。

對題目明確指定單一年份、單一已辨識事件類型的情況，來源檢查現在要求局部事件與日期依據。涵蓋婚姻、出生、死亡、成立、發布／出版與獲獎的有限字面模式。所選名字所在子句／句子中的日期須對應該事件；另一句的他人婚姻、同段中的出生／出版日期不能直接借用。結構化記錄可使用明確事件／年份標題；同一 passage 的緊鄰句若明確用 Their wedding 等方式續述，也可提供日期。

這是必要的字面 witness，不是完整句法或時間推理器。實作以局部切分及最近事件詞檢查日期，沒有宣稱它能證明任意主體、否定、並列關係或真正因果。多年份、多事件、as-of 等情況不猜測應套哪個年份，仍由原流程處理；語意驗證仍必要。

## 一併修正句尾年份

舊 `calendar_years` 把句尾的 `1998.` 一律當成可能的版本號而略過，造成「出生 1970，結婚 1998.」只看到 1970，錯拒正確來源。現在句尾句點可以結束年份，`1998.2`、`1998.beta` 仍不當日曆年份，PEP／RFC 識別字也不算年份。這帶回一個正向答案，不是只有增加棄答。

## 相同完整 4B 服務的十一題比較

baseline f6b7d0b 與修改後在同一自有完整 Qwen3-4B BF16 服務，使用相同十一頁與 fixture SHA，context cap 1536、depth 0、budget 12 秒、無搜尋。兩個實際來源為先前已暴露的 undated 人物頁及 Alchetron 明確年份頁，其餘為自編控制。

| 指標 | 修改前 | 修改後 |
|---|---:|---:|
| 各案答案＋來源符合預期 | 5/11 | 11/11 |
| 正確正向答案 | 5/6 | 6/6 |
| 證據不足時正確棄答 | 0/5 | 5/5 |
| 模型呼叫 | 21 | 17 |

五個不充分來源改為棄答：實際缺少年份頁、未註日期、另一出版事件、另一人的婚姻、出生年份。原本五個正確答案保留，包括實際完整年份頁、相鄰句婚期、年份標題記錄及沒有時間限制的一般配偶問題；出生與婚姻雙年份正向案例恢復。六項勝、零退步。

平均 1.288 → 1.124 秒，僅本組比較，不代表廣泛速度提升。執行前後程式雜湊相同，自有模型已停止，停止後 GPU 897 MiB。

- [十一題與預期](../benchmarks/event-years-20261023-cases.json)、[freeze／實際來源 hashes](../benchmarks/event-years-20261023-freeze.json)
- [完整 paired 記錄](../benchmarks/event-years-20261023-paired.json)、[摘要](../benchmarks/event-years-20261023-summary.json)

提供正確頁面能控制 reader，不能當作外網來源探索或新 holdout。undated 實際頁的獨立控制預期棄答，沒有改原外網題的 gold。先前三題外網的答案字串 1/3、joint 0/3 是舊執行紀錄，這次沒有重跑外網。最新完整十二題仍保持答案 4/12、joint 2/12，不拼接局部測試算新分數。

## 獨立 guard 與回歸

[最終 CPU／實際 HTTP 41 項](../benchmarks/event-years-20261023-final.json)：**21/41 → 41/41**，含原始實際 Candidate、年在事件之前／之後、不同事件、同段另一人、相鄰續述、過遠續述、來源標題、獎項／出生／成立／出版、普通查詢及年份／版本號邊界。HTTP 模型端刻意支持所有選擇，隔離來源 guard，不能用這個數字代表 LLM 能力。[程式](../eval/diagnose_event_years.py)

最初 34 項 pilot 有一個正向雙事件失敗，發現原因是既有句尾年份邊界。修正後 v2 的 39/39 保留原始範圍，再新增兩個句點邊界控制為最終 41 項；不把不同總數混成同一比較。

完整 4B 執行後，把此事件檢查的年份 pattern 也統一成上述句點規則，涵蓋題目與 heading 以句點結尾的情況。已保留實際 paired source 原文，並對十一頁所有抽取候選及兩版模型所選 span 核對，29 個 guard 決策完全相同；新增兩項由最終 CPU 測試覆蓋，沒有再次載入 GPU。[精修證據](../benchmarks/event-years-20261023-period-refinement.json)

保留 [CPU 15/15](../benchmarks/event-years-20261023-regression.json)、[proof／HTTP 27/27](../benchmarks/event-years-20261023-proofs.json)、[transfer 10/10 與 metamorphic 16/16](../benchmarks/event-years-20261023-transfer.json)、[名錄 HTTP 11/11](../benchmarks/event-years-20261023-records.json)、[欄位 10/10](../benchmarks/event-years-20261023-bindings.json)、[第一行 22/22](../benchmarks/event-years-20261023-lines.json)、[P0 16/16](../benchmarks/event-years-20261023-p0.json)、[方位 28/28](../benchmarks/event-years-20261023-directions.json)。編譯與 whitespace 檢查通過。

限制：未辨識的同義事件、跨段落／跨來源日期、複雜並列或較遠的指代可能棄答；最近事件詞也不是語義歸屬的完整證明。這次修的是已確認的缺日期與錯借日期，不是通用時間推理或來源可靠性認證。下一步仍需提高外網完整證據的覆蓋，尤其認證日期的 gold／platinum、專輯／單曲區分與多實體答案。
