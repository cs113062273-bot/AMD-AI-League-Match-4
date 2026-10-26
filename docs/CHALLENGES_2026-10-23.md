# 驗證頁辨識：CPU 上的來源解析修正

這一步只使用已保存的 HTTP 內容、CPU 解析與本機 HTTP 服務，沒有載入模型、使用 CUDA 或啟動瀏覽器。

## 問題與修正

第二組十二題的部分開發重跑中，`simpleqa-516` 實際取得兩個驗證頁：IEEE 回傳 HTTP 202、2060 bytes 的 AWS WAF 文件；PMC 回傳 HTTP 200、21431 bytes 的 reCAPTCHA 文件。兩者均沒有文章正文。舊解析器把它們標為動態網頁，仍留下 viewport 等 metadata 或「Checking your browser」段落，之後進入瀏覽器流程。記錄也確實包含 AWS challenge script 與 reCAPTCHA 資源請求。

新解析器在抽取 metadata、連結與正文前辨識這兩種已觀察到的文件，回傳 `challenge_aws_waf` 或 `challenge_recaptcha`。引擎沿用既有錯誤處理，跳過該頁，仍可搜尋替代來源。沒有執行或解答驗證程序。

規則刻意採用多個條件：AWS 必須同時具備 202、`challenge-container`、精確 `token.awswaf.com` 主機範圍下的 `/challenge.js`；reCAPTCHA 必須有對應標題及 Google 的 `/recaptcha/challengepage/` base URL。兩者都要求文字外殼不超過 500 字元，且沒有帶文字的 article 元素。單憑 HTTP 狀態、文件提到 CAPTCHA、背景驗證 widget 或相似網域都不會觸發。

這不是完整的防機器人頁面分類器；未涵蓋的版型仍可能進入一般解析流程。

## 驗證

[固定內容及實際本機 HTTP 診斷](../benchmarks/challenges-20261023.json)：同一批 25 個檢查由 16/25 變成 **25/25**，9 個改善、0 個退步。包含兩個原始 capture、202 正常文件、網域／路徑相似負例、帶 widget 的文章及一般 JS app。原始 capture 的 SHA256 已核對。

五個引擎檢查使用渲染器替身，全程沒有啟動 Chromium。兩個驗證頁各自的直接處理及替代來源流程都從呼叫一次渲染器改為零次；一般 JS app 仍會呼叫一次。替代來源測試前後都取得相同電話及來源，這裡的改善是避免無效渲染，不能稱為新增答對題目，也沒有測量實際瀏覽器節省的秒數。

既有 CPU 回歸保持通過：[代表性解析 15/15](../benchmarks/challenges-20261023-reader-regression.json)、[組合證據 27/27](../benchmarks/challenges-20261023-proof-regression.json)、[服務與來源 16/16](../benchmarks/challenges-20261023-p0-regression.json)、[Oyez 控制 24/24 與 HTTP 整合 4/4](../benchmarks/challenges-20261023-oyez-regression.json)。

尚未做新的模型或公開網路完整評估，因此不更新答案準確率。最新首次抽樣仍是 0/12 精確答案；部分開發重跑仍是 0/10，兩者各自保留。
