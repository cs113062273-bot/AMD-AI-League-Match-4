# 2026-10-23：拒絕未傳送的候選 ID

目前 selector payload 採逐字 passage 模式，`candidates` 固定為空，但用戶端仍可能把端點回傳的 `candidate: 0` 當成本機排名第一的候選。那個值從未出現在模型請求內，因此這種回覆不成立。本機 resident protocol 已有拒絕機制，這次補齊用戶端，讓替換端點或異常服務回覆也受到相同限制。

修改僅要求候選 ID 必須存在於該次實際傳送的 `candidates`；否則回傳 `invalid_selection`。合法 passage 0、最後一個已送 passage、逐字邊界、布林 ID、混合模式與空答案棄答都保留原有判定。

[實際 HTTP 診斷](../eval/diagnose_selector_boundary.py) 使用可控端點回覆、不呼叫模型，也不把 gold 放進請求。相同十項條件，254741a 為 **7/10**，修改後 **10/10**；恢復三個未傳送 ID 的拒絕，零退步。[結果](../benchmarks/selector-boundary-20261023.json)

整合回歸保留 [P0 16/16](../benchmarks/selector-boundary-20261023-p0.json)、[名錄 HTTP／衝突 11/11](../benchmarks/selector-boundary-20261023-records.json)、[proof／HTTP 27/27](../benchmarks/selector-boundary-20261023-proofs.json)。編譯與 whitespace 檢查通過；沒有為這個協定邊界改動再載入 4B。

```powershell
.venv\Scripts\python.exe eval/diagnose_selector_boundary.py --out benchmarks/selector-boundary-new.json
```

這是協定健全性修正，不是新增答案能力或競賽分數。[本輪外網三題的觀察與限制](LIVE_PIPELINE_2026-10-23.md) 保持不變；該外網執行早於本次用戶端補強。
