# 2026-10-23：名錄原始欄位提案，尚未納入正式程式

更新：GPU 空出後已執行原八題完整 4B 對照並納入程式，結果為 [4/8 → 6/8、0 退步](RECORD_FIELDS_2026-10-23.md)。下文保留提案凍結時的歷史狀態；目前不必重新套用此 patch。

既有真實名錄題已能選出 1984，但 semantic verifier 仍拒絕。原 HTML 同一 article 具有 `data-year` 和 `data-surname`，現行 reader 沒有把這些欄位提供給模型。

[提案 patch](../eval/proposals/recordfields-20261023.patch) 只保留能在該筆記錄可見文字中找到、長度受限的 data-* 屬性，附上 source_fields 供 selector/verifier 理解欄位用途。未對人名、答案、年份或獎項寫特殊規則，也沒有修改 verifier 判定標準。提案的 [27 項結構檢查](../benchmarks/recordfields-20261023-structural.json) 通過；程式與 fixture hash 在 [manifest](../benchmarks/recordfields-20261023-proposal.json)。

準備好的 [八題案例](../benchmarks/recordfields-20261023-cases.json) 包含既有真實名錄、其他人名／用途、錯姓名、錯獎項、隱藏屬性與可見年份不一致、同一人兩個衝突年份、錯事件。沒有根據模型結果修改這些新情境。[合成頁面](../fixtures/recordfields-20261023-synthetic.json) 已追蹤；真實頁面沿用先前的完整 capture，完整回播 fixture 位於本機 `research/recordfields-20261023/fixtures.json`。

本輪其他使用者 GPU 工作占用約 5.8 GiB，沒有足夠空間同時載入 bf16 4B。沒有動其他程序或降低既有 VRAM guard。**尚未執行八題完整 4B 對照，也未宣稱答案改善。提案已從 production worktree 移出，只保存 patch。**

`eval/diagnose_reader.py` 新增互斥的 `--compare-baseline` 選項，可在同一自有模型 session 先讀隔離歷史 package，再讀目前程式，保留兩組逐題結果、health 與 wins/losses，避免為兩個版本重複載入模型。原 `--baseline` 和單版本流程保留；語法及 CLI 檢查通過，paired 模式的實際 GPU 執行仍待上述 headroom。

繼續時先檢查目前 VRAM 與 8765 listener，確認有空間後，以 `git apply --check` 檢查 patch 再套用，執行 manifest 中的命令。若有新 loss，先分析／回退；不能因結構檢查通過就把提案當成準確率提升。
