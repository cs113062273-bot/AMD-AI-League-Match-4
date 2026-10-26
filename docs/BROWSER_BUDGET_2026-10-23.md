# 2026-10-23：保留內容請求額度與主頁 redirect

案件題的實際 browser trace 用滿 20 次請求，當中包含分析腳本，內容 API 卻未取回。這提出了可重現的資源競爭問題，但不等於已證明該站唯一故障原因。

現在對 script／xhr／fetch 類型，提前拒絕三組明確分析服務 host：google-analytics.com、googletagmanager.com、doubleclick.net，包含其子網域。這些請求不進入 Fetcher，也不占 20 次內容抓取額度；新增 blocked_analytics 計數。僅用 host 邊界比對，不把名稱相似的其他網域誤擋，不改頁面 document 規則，也沒有一般性封鎖第三方腳本。

總請求、byte、browser 時間、禁止 POST／WebSocket／service worker／媒體與 DNS 私網保護都不提高或解除。仍可能有其他無用第三方流量，沒有宣稱一般反追蹤或完整內容優先排程。

## 重新導向問題

加入正向 redirect 保護案例時，舊版與最初 analytics-only 修改都失敗。原因是 Fetcher 已安全跟隨主頁 redirect，route 再送合成 302 給 Chromium 後，後者可能走向拒絕 proxy 而不重新進入 route，出現 ERR_SOCKET_NOT_CONNECTED。

主頁現在先由原 Guarded Fetcher 確認最終 URL／完整回應，再導覽到該 URL；主 document route 重用已驗證回應，避免第二次抓取或合成 redirect。這個預取在原六秒 browser timeout 內，不是新增無界 retry。來源仍回傳實際最終主頁 URL。子資源 redirect 等其他情況不屬於本次修正保證。

## 實際 Chromium 檢查

[五項 v2 比較](../benchmarks/browser-budget-20261023-v2.json)：**3/5 → 5/5**，crowded 與 redirect 兩項恢復，零退步。[程式](../eval/diagnose_browser_budget.py)

- 內容頁依序發出 21 個分析請求後，才抓取容量 JSON。舊版用滿 20 次額度，內容未顯示；修改後全部 21 個分析請求在 route 拒絕，只用主頁＋內容 API 兩個 Fetcher slot 就顯示正確文字。
- 普通非擁擠頁面仍正常。
- 重新導向後內容可顯示，來源 URL 為最終頁面。
- POST 仍不會進入 Fetcher。
- `google-analytics.com.example.org` 不會被當成分析服務而誤擋。

全部使用真實新開 headless Chromium 與實際 loopback HTTP。分析／外觀相似網域的回應在 Fetcher 邊界以受控回應提供；沒有對真實分析服務發送測試流量，也沒有公共網路依賴。這是資源／內容交付測量，不是模型正確率。

[初次 3/5 → 4/5 記錄](../benchmarks/browser-budget-20261023.json) 保留；其 redirect 失敗未隱藏。修正後另存 v2，不覆寫 pilot。

既有 [六項 browser 回歸](../benchmarks/browser-budget-20261023-regression.json) 全通過：一般頁、redirect、慢背景請求時的可讀內容、無限 JS 的逾時、獨立 CLI worker，以及私網目的地阻擋，無非預期 stderr。原 `benchmarks/browser-validation.json` 沒有覆寫。編譯與 whitespace 檢查通過。

## 實際 Oyez 觀察與後續入口

analytics-only 階段的[公開頁探測](../benchmarks/browser-budget-20261023-live.json) 雖擋住一次分析流量、未用滿請求額度，仍只有空殼內容，沒有案件事實；這證明排除流量不是該站完整解方。該次 capture hash 對應較早 browser 程式，不能冒充最終版端到端成功。

另從實際載入的 Oyez 應用程式觀察到 `OY_API_HOST` 與 Case resource 的 term／docket 路由，直接對其公開 GET 入口做一次有限探測，得到 HTTP 200、31,699 bytes，含兩個球隊所涉案件的 facts 欄。[API 探測](../benchmarks/browser-budget-20261023-api-probe.json)。沒有猜答案 URL、沒有使用 gold 值作 query，也沒有繞過挑戰。

本輪尚未把 API 接進 production adapter、重跑模型或改用此 API 計分；它是下一個可行來源。後續需驗證 case identity、HTML-in-JSON 文字、實際 citation URL 及非連續多名稱答案，不可僅因 API 可讀就宣稱答對。

最新完整十二題答案仍為 4/12、joint 2/12；本次沒有外網分數提升宣稱。沒有載入額外模型、重建 image、push 或提交競賽。
