# 2026-10-23：搜尋提示縮短，保留原 deadline

十二題完整外網重跑有六題無法完成搜尋 hints：五次 model_deadline、一次 TimeoutError。服務紀錄顯示部分輸出到約三十多 token 時就耗盡 3.8 秒預算，不能以部分 JSON 當成功。

本次把原本最多八個提示的 system prompt，改為要求最多兩個短查詢、每個以五詞為目標，並保留原題主體與關係；expansion generation cap 由 64 降為 48 token。HTTP deadline、取消、其他選擇／驗證模式的 token cap 完全不變。沒有提高 timeout，沒有解析不完整 JSON，也不使用提示當答案。

「兩個／五詞」是生成指示，不是硬 API 限制；現有 parser 與搜尋仍有各自的長度、數字、URL、錨點檢查。實測有一個新查詢為七詞，仍在既有允許範圍內，不能宣稱模型嚴格遵守五詞限制。

## 同權重完整 4B 的 HTTP 比較

八個執行前凍結的原問題：六個已暴露的提示失敗案例，加兩個自編識別字／縮寫控制。載入同一份完整 Qwen3-4B BF16 權重一次，在自有 HTTP 服務閒置時切換 d79f29d／current 的實際 Runtime.infer；每題交錯前後順序。client cap 3.8 秒、context cap 1536，沒有網路搜尋或 gold 答案。

| 指標 | d79f29d | 修改後 |
|---|---:|---:|
| 合法完成的 hints | 3/8 | 8/8 |
| 完成且有原問題錨點的 hints | 3/8 | 8/8 |
| 平均秒數 | 3.163 | 1.049 |
| 平均生成 token | 62.375 | 21 |

原版此時有四次 64-token 未完整 JSON、一次 deadline；修改後八題都完成。這次設備狀況比十二題重跑較快，舊版有部分提示也能完成，沒有把兩次環境差異冒充同輸入比較。表中的比較是在同一權重／服務內量測。

paired 原始 `anchored` 計數是所有可用短 query，包含 expansion 失敗後由原題引號形成的 fallback，因此原版為 4/8。上表要求 query 必須實際存在於完成的模型 hints，正確為 3/8；兩種定義在 [摘要](../benchmarks/expansion-20261023-summary.json) 分開，沒有把引號 fallback 當成模型完成。

- [八題](../benchmarks/expansion-20261023-cases.json)、[執行前 freeze](../benchmarks/expansion-20261023-freeze.json)
- [完整 HTTP paired 結果](../benchmarks/expansion-20261023-paired.json)、[診斷程式](../eval/diagnose_expansion.py)

最後一次正常 select 請求也成功，證明 worker 在 deadline 後仍可用；本機實際 [HTTP／tiny CPU cancellation 10/10](../benchmarks/expansion-20261023-service.json) 與 [P0 16/16](../benchmarks/expansion-20261023-p0.json) 保留。這些 cancellation 檢查不是完整 4B accuracy 證據。

## 來源探索與三題完整外網流程

將新版實際輸出不變地交給搜尋，人物、案件、專輯三題各有八個相關候選，前四內容頁分別有 2、2、4 頁可讀。[query-only input](../benchmarks/expansion-20261023-discovery-input.json)、[實際檢索](../benchmarks/expansion-20261023-discovery.json)。未使用 gold 值或替代 gold URL。

之後在另一個自有完整 4B 服務，使用原十二題中三題的完整問題與原 gold 子集，執行實際搜尋、browser、select 與 verify。相同 cap 1536、budget 24 秒、depth 2；執行前[子集／protocol](../benchmarks/expansion-20261023-live-protocol.json)已凍結，來源與答案沒有改。

| 指標 | 前一次十二題中的這三題 | 本次三題 |
|---|---:|---:|
| 答案字串符合原 gold | 0/3 | 1/3 |
| 答案＋來源符合 | 0/3 | 0/3 |
| hints 完成 | 0/3 | 3/3 |

姓名題輸出 Akiko Kumahira，字串與標準答案相同，但來源是 Notable People Project，並非預列 gold 來源。更重要的是，選中段落只說兩人結婚，沒有題目指定的 1985 年，語意 verifier 仍支持；因此不能把答案字串恢復說成所有要求已有證據。這暴露了下一個需修正的事件年份完整性問題。

案件題的選擇未通過語意驗證；專輯認證日期仍出現 invalid selection。兩題都保留棄答，沒有為取得數字而放寬型別或語意檢查。

[完整三題結果](../benchmarks/expansion-20261023-live.json)、[摘要](../benchmarks/expansion-20261023-live-summary.json)、[原 gold 子集](../benchmarks/expansion-20261023-live-cases.json)。動態外網回應不同，這不是固定輸入因果比較，也不是新 holdout。沒有重跑全部十二題，因此不能與其他九題拼出新的 5/12；最新完整十二題仍是答案 4/12、joint 2/12。

兩個模型程序均已結束，沒有留服務；三題結束後 GPU 1005 MiB。程式在兩次執行期間雜湊均不變，八題 freeze／三題子集與所有 capture SHA 已核對。本輪沒有 rebuild、push、submission 或 AMD 驗證。
