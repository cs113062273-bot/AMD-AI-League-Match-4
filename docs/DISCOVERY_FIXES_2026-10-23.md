# 2026-10-23：檢索與站內入口恢復

接續 [轉移案例修正](TRANSFER_FIXES_2026-10-23.md)。這輪處理來源發現失敗，尚未重跑完整外網評估。

- 模型提供的搜尋提示會附加在原實體與欄位查詢後，避免被泛用提示取代。
- 搜尋供應者只回傳不相關連結時，仍會啟用既有備援。弱結果保留為最後選項，不再讓「有 URL」等同搜尋成功。
- 當語義選頁棄答、所有連結分數偏低時，最多探索兩個非負分的同 origin 連結，處理只有「More」「Details」的站內入口。沿用頁數、深度、時限與網路存取限制。
- 只有一個可探索連結時省略選頁模型呼叫。

受控 HTTP 診斷從 **1/7 到 7/7**，包含三個查詢錨點、供應者備援、單一／兩個弱站內連結與無關外站負例。選答服務只抽取實際 passage 中的電話並對導航棄答，沒有真實 LLM 或公開搜尋供應者；這是流程證據，不是外網準確率。

原始 [before](../benchmarks/discovery-20261023-before.json)、[after](../benchmarks/discovery-20261023-after.json)，重現程式為 [diagnose_discovery.py](../eval/diagnose_discovery.py)。既有 proof／HTTP 檢查 [27/27 保持通過](../benchmarks/discovery-20261023-proof-regression.json)，語法編譯與 diff whitespace 檢查通過。

尚有限制：詞彙重疊只是搜尋品質的粗估；相關標題不保證內文含答案。初始結果的候選覆蓋、被擋來源與證據驅動的再次檢索仍需另行評估。沒有更新提交 image 或對外推送。
