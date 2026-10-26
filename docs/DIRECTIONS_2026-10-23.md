# 2026-10-23：方位邊界必須綁定所選名稱

首次外網十二題的 Goldsboro 問西側邊界河流，模型卻以「河流在城市附近」的 USGS 觀測站段落作答，獨立語意驗證也錯誤支持。原始選擇與 HTTP 回應都保留在十二題記錄中；這是實際錯誤，不能歸為答案格式問題。

現在，對明確的單一東／南／西／北邊界問題，來源檢查要求所選名稱在來源局部子句中有對應方位及邊界語境，或在明確的方位邊界標題下。另一子句、另一河流附近的方位詞不能直接借用；名稱本身的 West 也不算關係證據。同一名稱的重複敘述若出現衝突方位，拒絕。

這是必要的字面關係檢查，不是一般地理推理器。主體、否定、完整關係與來源可信度仍需語意驗證；沒有以 gold 河名補答案。

## 完整 4B 比較

同一個自有完整 Qwen3-4B BF16 服務，1285dc8 與修正後各跑相同八題、相同 fixture SHA。context cap 1536、max_depth 0、budget 12 秒，沒有搜尋。

| 結果 | 修改前 | 修改後 |
|---|---:|---:|
| 答案與來源符合各案預期 | 5/8 | 8/8 |
| 明確邊界的正向答案 | 4/4 | 4/4 |
| 證據不足／矛盾時正確棄答 | 1/4 | 4/4 |
| 模型呼叫 | 16 | 12 |

真實錯誤來源頁、只有 nearby 的自編頁、只有 West River 名稱的自編頁，原先都錯答並通過語意驗證，現在都棄答。直接西側、平行列出南／西兩條河、邊界標題下名稱、南側邊界四題全部保留。三項恢復、零退步。

平均 1.393 → 1.247 秒；這個窄比較中，部分錯誤選擇在語意呼叫前被拒絕。沒有廣泛速度改善主張。執行前後程式雜湊不變，模型已停止，停止後 GPU 938 MiB。

- [凍結八題](../benchmarks/directions-20261023-cases.json)、[實際來源與 fixture freeze](../benchmarks/directions-20261023-freeze.json)
- [完整 paired 結果](../benchmarks/directions-20261023-paired.json)、[摘要](../benchmarks/directions-20261023-summary.json)

真實 wrong-source 控制頁的預期是棄答，因該頁沒有所問邊界證據。這不是修改原十二題的上游答案：原題仍以原 gold 評分，首次答案 4/12、joint 2/12 完全保留。八題比較提供來源頁，不能當成外網搜尋或未知題準確率。

## 其他檢查與限制

[28 項 CPU／實際 HTTP 檢查](../benchmarks/directions-20261023.json) **13/28 → 28/28**，包括原始錯誤 Candidate、同句平行河流、跨句／子句借用方位、方向在名稱內、標題與段落矛盾、四種基本方位。HTTP 端點刻意對逐字選擇一律回 supported，隔離獨立 guard 的效果，不代表模型能力。[程式](../eval/diagnose_directions.py)

保留 [CPU 15/15](../benchmarks/directions-20261023-regression.json)、[proof／HTTP 27/27](../benchmarks/directions-20261023-proofs.json)、[transfer 10/10 與 metamorphic 16/16](../benchmarks/directions-20261023-transfer.json)、[名錄 HTTP 11/11](../benchmarks/directions-20261023-records.json)。編譯與 whitespace 檢查通過。

明確的 West Bank 地名、不要求邊界的流向、多方位問題等不在本 guard 範圍，仍交給原流程；診斷的「通過」只表示沒有誤套用此檢查，並非認證那些段落能回答問題。字面檢查與最近方位綁定仍可能漏掉複雜語法或有效同義說法。沒有宣稱解決任意主體、否定、地圖或座標推論，也未驗證官方／AMD 評分。
