# 2026-10-23：實際外網流程與兩個錯誤拒答

前三輪正確頁面名錄測試的 8/8，不能代表外網表現。本輪選取先前已暴露的三個外部失敗案例，使用實際搜尋、HTTP、選擇性瀏覽器與完整 Qwen3-4B，從原始起始 URL 執行。題目、原始答案別名和來源網址在第一次執行前凍結，沒有按輸出修改標準。

## 外網觀察

| 案例 | 修改前 | 修改後 | 修改後來源 |
|---|---|---|---|
| Vickerman Hill 高度 | `model_evidence_rejected`，空答案 | `1141 ft MSL`，`model_verified` | [TopoQuest](https://topoquest.com/place/new-york/summit/vickerman-hill/968529) |
| Laennec 的結核病因果主張年份 | `model_no_evidence` | 仍棄答 | 搜到的 1819 年段落未充分支持問題所問的因果主張 |
| We Rollin 音樂作曲者 | `unresolved_conflict`，空答案 | `Anabolic Beatz`，`model_verified` | [BharatLyrics](https://bharatlyrics.com/we-rollin-lyrics/) |

原始答案與來源嚴格比對仍為 **0/3 → 0/3**。高度的原始標準是描述可接受範圍的完整字串，作曲者標準帶句點，且這次取回的來源不在凍結來源集合。這些都沒有事後放寬。兩題從棄答變成通過逐字、型別及獨立語意驗證的答案，屬於流程恢復；不能寫成競賽正確率提升。

兩次外網回應會變動，作曲者第二次使用的頁面也不同，故這不是固定輸入的因果比較，也不作速度提升主張。固定原始回應另有機械檢查，見下文。

執行條件：context cap 1536、max_depth 2、budget 24 秒、完整本機 4B 模型，保留原有 GPU 資源門檻。兩次均正常完成，沒有服務錯誤。修改後三題耗時 8.167、9.878、9.521 秒，合計九次模型呼叫。模型程序已停止，停止後 GPU 使用量 1406 MiB。

- [凍結三題](../benchmarks/live-pipeline-20261023-cases.json)
- [修改前完整記錄](../benchmarks/live-pipeline-20261023-before.json)
- [修改後完整記錄](../benchmarks/live-pipeline-20261023-after.json)

## 修正與固定回應檢查

1. 地理高度答案可保留原文 `MSL`。之前完整字串 `1141 ft MSL` 被 measurement fullmatch 拒絕。現在只在高度、海拔語境接受這個有限後綴；補齊 feet/foot/metre/meter 字面單位，並拒絕問題明確要求英尺、答案卻是公尺的情形。不換算、不刪除後綴，未知後綴仍拒絕。
2. 衝突檢查以實際選中的欄位為準。之前兩個無關的 infobox 標題／媒體欄位平手，會擋住模型已選出的作曲者段落。現在仍拒絕選中欄位的電話／價格衝突及同人同獎的名錄衝突，但其他欄位平手不再否決選擇。沒有模型選擇時的保守策略保留。

[固定檢查](../eval/diagnose_live_guards.py) 用修改前保存的真實 TopoQuest、Bharatpedia 回應，以及合成的單位與電話／價格反例，測量判定函式。相同輸入的 e74e5da 為 **13/19**，修改後 **19/19**，六項恢復、零退步；其中兩項直接重現上述真實選擇。這是 guard 行為，不是 LLM 或外網正確率。[報告](../benchmarks/live-guards-20261023.json)

保留既有 [CPU 15/15](../benchmarks/live-guards-20261023-regression.json)、[欄位綁定 10/10](../benchmarks/live-guards-20261023-bindings.json)、[名錄 HTTP／衝突 11/11](../benchmarks/live-guards-20261023-records.json)、[proof／HTTP 27/27](../benchmarks/live-guards-20261023-proofs.json)。

## 重現與限制

```powershell
.venv\Scripts\python.exe eval/diagnose_reader.py --cases benchmarks/live-pipeline-20261023-cases.json --live-web --browser --capture-web research/live-pipeline-new --max-depth 2 --budget 24 --context-tokens 1536 --out benchmarks/live-pipeline-new.json
.venv\Scripts\python.exe eval/diagnose_live_guards.py --out benchmarks/live-guards-new.json
```

原始 HTTP 回應在忽略版控的 `research/live-pipeline-20261023*`，報告內保留各案檔案 SHA；本輪六份 capture 都沒有因數量／容量限制漏存。這些是 Fetcher 回應，未包含瀏覽器渲染後的完整 DOM，因此不能宣稱完整外網流程可逐位元重播。機械診斷需要本機保留的兩份修改前回應。

reader runner 新增 live-web 與 bounded capture 模式，禁止以變動外網執行 paired baseline 比較，並保留中途失敗前已完成的 rows。local/live 評分路徑與 partial rows 保留另以 stub 控制檢查通過；這不增加答案能力證據。

下一個瓶頸是取回精確關係的證據：Laennec 案已有年份，卻缺問題所問的因果主張。下一輪應改善探索的證據覆蓋，不以放寬語意驗證補分。尚未重跑完整 670 題、重建 image、提交外部競賽，或驗證 AMD／私有 evaluator。
