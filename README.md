# 校務 FAQ 智慧問答與工單系統

這是一套可在 Windows 電腦自行部署的校務 FAQ、地端 AI 與跨處室工單系統。系統先從本機 FAQ 知識庫搜尋相關內容，再由本機 Ollama 模型整理成繁體中文回答；若資料不足，學生可匿名建立工單，由 AI 自動判斷承辦處室。

處室回覆結案後，系統會寄送包含問題、回答及星級評分連結的通知信，並把有效 Q&A 自動寫回 FAQ CSV 與向量知識庫。

> 本專案是 Windows 單機／原型驗證版。正式上線前，建議串接學校會員系統、正式網域、權限控管、備份及資安機制。

![學生前台](docs/images/01-student-front.png)

*學生前台 `/`：左上角品牌方塊、側欄分類與對話紀錄、右側對話區與詢問單入口。
版面、文案、顏色、圖片全部可在 `/design` 後台調整，不需要改程式碼。*

## 目錄

- [更新紀錄](#更新紀錄)（2026-09-10 起的調整與 FAQ 資料異動）
- [功能總覽](#功能總覽)
- [畫面與功能說明](docs/UI-GUIDE.md)（逐項截圖說明）
- [系統架構](#系統架構)
- [使用技術](#使用技術)
- [系統需求](#系統需求)
- [快速開始](#快速開始)（安裝、啟動、密碼位置、停止）
- [FAQ CSV](#faq-csv)
- [常見問題管理後台](#常見問題管理後台)（匯入試算表、逐筆編輯）
- [工單流程](#工單流程)
- [Email 設定](#email-設定)
- [Cloudflare 臨時公開](#cloudflare-臨時公開)
- [資料位置與備份](#資料位置與備份)
- [專案結構](#專案結構)
- [API 摘要](#api-摘要)
- [健康檢查](#健康檢查)
- [常見問題](#常見問題)
- [安全注意事項](#安全注意事項)
- [授權與資料權利](#授權與資料權利)

### 三行版快速開始

```powershell
git clone https://github.com/yufan-code/rags.git
cd rags
Set-ExecutionPolicy -Scope Process Bypass; .\setup.ps1; .\start.ps1
```

需先安裝 Python 3.11+ 與 [Ollama for Windows](https://ollama.com/download/windows)。首次安裝需下載模型，約數分鐘。完成後瀏覽器會自動開啟 <http://127.0.0.1:8001>，管理員密碼寫在 `admin-token.txt`。

## 更新紀錄

### 2026-09-15

- **用詞統一為「詢問單」**：學生前台、處室後台 `/office`、總管理員後台 `/admin`、外觀後台欄位、寄給處室的通知信、寄給學生的結案信，以及 API 錯誤訊息，原本的「需求單」全部改為「詢問單」。資料庫裡已存在的處理紀錄（例如「建立服務需求單」）屬歷史資料，保留原文字；之後新產生的紀錄都寫「詢問單」。
- **前台提示文字可在後台修改**：外觀後台 `/design` 新增兩組文案欄位。
  - 「查無答案提示」：查無答案時 AI 的回覆、提示卡的標題／說明／確認按鈕、送出後的處理中文字。
  - 「Email 視窗」：送出詢問單前填寫 Email 的視窗小標、標題、說明、欄位名稱與按鈕。
  - 原本寫死在 `frontend/app.js`、`frontend/index.html` 的文字改為讀取設定，後台沒填時使用原本的文字。
- **新增使用說明頁 `/guide`**（`frontend/guide.html`，截圖在 `frontend/guide/`）：圖文說明學生如何提問、查無答案時如何提交詢問單，以及處室如何登入回覆、如何轉單。前台首頁不提供連結，需直接輸入網址；處室畫面使用範例資料，不含真實學生提問。

### 2026-09-14（FAQ 資料異動）

- 於常見問題管理後台刪除 1 題：`TICKET-T-20260901-0003`「宿舍房間發現漏水，晚上要聯絡哪個單位？」（由已結案詢問單自動轉入知識庫的題目）。`data/faq.csv` 由 175 題變為 174 題。刪除前的完整資料備份在 `data/faq-backups/faq-20260914-085736.csv`（備份資料夾不提交 GitHub）。

### 2026-09-11

- **匯入預覽提醒**：同一份試算表重複的題目只匯入第一次出現的那列；依編號對到題目不同的舊題會標「編號衝突」並預設不勾選；要新增的題目若與舊題答案一字不差，或題目語意相似度達 0.85，標「相似提醒」，0.72～0.85 則列出「相關舊題」供參考。
- **匯入結果報告**：匯入後逐筆列出新增、更新（改了哪些欄位）、內容無變更、略過及原因；題目列表可選「最近更新在前」。
- **服務常駐與自動重啟**：新增 `scripts/faq_watchdog.ps1` 與 Windows 排程工作 `shu_faq-backend`（開機即執行、不需登入）。8001 沒有服務時約 30 秒內自動重新啟動 uvicorn。詳見[常駐與自動重啟](#6-常駐與自動重啟)。

### 2026-09-10

- **FAQ 新增兩個系統欄位**：`updated_at`（更新時間）與 `update_note`（更新內容），在新增、匯入或後台編輯時自動寫入，例如「匯入更新：主責單位（空白 → 總務處）」；常見問題管理後台列表多了這兩欄。
- **匯入規則調整**：依題目文字對應既有題目並更新原本那筆，不再重複新增；試算表自己編的 1、2、3 不再覆蓋既有的 `Q001`；分類沿用知識庫既有寫法（例如「教室與設備」存成「七、教室與設備」）；「依據／來源連結」被換行切斷的網址會接回，其餘說明文字併入關鍵字；試算表空白或只差空白換行的欄位保留原值。另修正沒給編號時會從 `Q001` 重新配號而覆蓋舊題的問題。
- **FAQ 資料**：總務處試算表重新匯入，更新 10 題（`Q112`、`Q117`、`Q118`、`Q162`、`Q163` 補上主責單位「總務處」；`Q173`～`Q177` 將依據說明併入關鍵字）。當天 16:13 一次匯入誤蓋的 `Q001`～`Q005` 已從備份還原，總務處那 5 題改放在 `Q173`～`Q177`。

## 功能總覽

### 學生端

- 側欄分類直接讀取 `data/faq.csv` 的實際分類（`GET /api/categories`），點選分類後在對話區列出該類常見問題，不需自行輸入。
- 也可以直接用自然語句搜尋 FAQ。
- 本機 AI 只根據搜尋到的 FAQ 整理回答。
- 可查看來源 FAQ、相似度及官方連結。
- 知識庫沒有答案時，一鍵匿名建立工單，不需姓名或 Email。
- 可查看工單狀態、承辦處室及處理紀錄。
- 結案後可給 1～5 星評分及補充意見。
- 1～2 星會自動重新開啟工單，交回原處室確認。

![學生前台手機版](docs/images/02-student-mobile.png)

*同一頁在手機（390×844）的樣子：寬度 900px 以下改為單欄，側欄收合成上方橫向捲動
的分類列，右下角出現「＋」浮動新對話鈕。*

### 處室端

- 每個處室使用不同的專屬密碼登入，只能查看自己的工單。
- 可依待處理、處理中及已解決篩選。
- 可輸入回答、結案或轉派其他處室。
- 只有實際轉派才計入轉單數；學生開單與 AI 初始分派不計入。
- 可自行修改本處室通知 Email，不能修改其他處室。
- 工單轉派後，新處室會收到包含工單連結及該處室密碼的通知信。

![處室登入](docs/images/04-office-login.png)

*處室端 `/office`：所有處室共用同一入口，各自輸入專屬密碼，登入後只看得到自己的詢問單。*

### 總管理員端

- 查看所有處室、所有狀態的工單。
- 查看提問數、實際轉單數、轉單率、結案數及平均處理時間。
- 查看各處室工單量、處理時間、評分及全校星級分布。
- 查看待處理、逾時及低分重新開啟的工單。
- 可修改工單狀態、回答、承辦人及承辦處室。
- 可設定各處室通知信箱，以及一個或多個學生回覆完成通知信箱。
- 可新增、移除學生通知收件人、測試寄信及匯出 CSV。
- 可從 Google 試算表、CSV／Excel 檔或直接貼上匯入常見問題，匯入前先預覽新增與覆蓋的筆數。
- 可在後台逐筆檢視、搜尋、修改或刪除常見問題，存檔後前台與 AI 立即使用新資料。

![管理後台登入](docs/images/05-admin-login.png)

*總管理員後台 `/admin`：未登入時只有營運數據總覽的外框，輸入管理密碼後才載入詢問單資料。
右上角可切換統計區間、跳到常見問題管理、匯出 CSV。*

![常見問題管理登入](docs/images/06-faq-admin-login.png)

*常見問題管理 `/faq-admin`：與總管理員同一組密碼。可匯入 CSV、逐題編輯與刪除，
存檔後會重新計算向量索引。*

### 外觀設定端

![外觀後台登入](docs/images/03-design-login.png)

*外觀後台 `/design` 登入畫面。「記住密碼，下次直接進入」預設勾選：勾選會把密碼存進
該台電腦瀏覽器的 `localStorage`，不勾則只存 `sessionStorage`（關掉分頁就忘記）。
登入後右上角有「登出」可清除。公用電腦請不要勾。*

- 進入 `/design` 可用管理員密碼登入，不需改程式碼就能調整學生端外觀。
- 可調整配色、字體、字級、圓角、按鈕與對話框樣式。
- 可改寫學生端所有介面文案（標題、歡迎語、按鈕、工單視窗欄位名稱，以及「查無答案提示」卡片與送出前的「Email 視窗」等）。
- 可自訂側欄分類與範例問題清單。
- 可加入自訂 CSS；儲存前會先過濾 `@import` 與 `</style>` 等危險寫法。
- 可上傳圖片替換網站 Logo、頁面背景圖，以及對話框兩側的 AI／使用者頭像
  （PNG／JPG／GIF／WEBP／SVG，單檔 3 MB 以內，存於 `data/design-assets/`，
  以 `/media/<檔名>` 提供）。
- 可直接編輯 8 支原始 CSS 檔，含系統自動產生的 `site-theme.css`；
  改壞了隨時按「還原原始檔」救回來。
- 登入可勾選「記住密碼」，右上角提供「登出」清除。
- 支援即時預覽，滿意再儲存；也可一鍵還原預設值。
- 設定寫入 `data/site-config.json`，由 `/site-theme.css` 動態套用。
- 每個畫面的逐項說明與截圖見 [docs/UI-GUIDE.md](docs/UI-GUIDE.md)。

### Email 與知識庫成長

- 新工單自動寄至 AI 判斷的承辦處室。
- 處室信件包含問題、工單連結、後台連結及該處室專屬密碼。
- 結案後寄出 Q、A 及 1～5 星評分連結。
- 單機版預設將學生評分信寄到 `default-email.txt`，管理員可在後台新增或移除多個通知信箱。
- 已解決且有回答的工單會自動新增或更新 `data/faq.csv` 與向量庫。
- 同一工單使用固定 FAQ ID，重複同步不會建立重複資料。

## 系統架構

```text
學生／處室／管理員瀏覽器
            │
            ▼
FastAPI（127.0.0.1:8001）
    ├─ Sentence Transformers 多語言 Embedding
    ├─ Qdrant Local 本機向量庫
    ├─ Ollama qwen2.5:3b（回答與工單分派）
    ├─ SQLite（工單、事件、評分與統計）
    ├─ site-config.json（前台外觀與文案）
    └─ Gmail OAuth／SMTP（通知信）
```

FAQ、工單及向量資料預設只存於執行系統的 Windows 電腦。不需要 Docker，也不需公開 Ollama 或資料庫連接埠。

## 使用技術

- Python 3.11+
- FastAPI / Uvicorn
- Sentence Transformers
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Qdrant Client Local Mode
- Ollama `qwen2.5:3b`
- SQLite
- Gmail API OAuth 2.0 或 SMTP
- HTML、CSS、Vanilla JavaScript
- 選用 Cloudflare Tunnel

## 系統需求

- Windows 10 或 Windows 11
- Python 3.11 以上，安裝時勾選 `Add Python to PATH`
- [Ollama for Windows](https://ollama.com/download/windows)
- 建議至少 8 GB RAM
- 第一次安裝需要網路下載 Python 套件、Embedding 模型及 Ollama 模型
- 約需數 GB 磁碟空間，實際大小取決於模型與 FAQ 數量

## 快速開始

### 1. 下載專案

```powershell
git clone https://github.com/yufan-code/rags.git
cd rags
```

也可以在 GitHub 選擇 `Code` → `Download ZIP`，解壓縮後在專案資料夾開啟 PowerShell。

### 2. 第一次安裝

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

安裝程式會自動：

1. 建立 `.venv` Python 虛擬環境。
2. 安裝 `backend/requirements.txt` 套件。
3. 產生管理員密碼及 10 個處室專屬密碼。
4. 建立本機 Email 設定範本。
5. 啟動 Ollama 並下載 `qwen2.5:3b`。
6. 下載多語言 Embedding 模型。
7. 將 `data/faq.csv` 匯入本機向量庫。

第一次執行可能需要數分鐘，請等待模型下載及 FAQ Embedding 完成。

### 3. 啟動

```powershell
.\start.ps1
```

| 入口 | 網址 | 用途 |
|---|---|---|
| 學生版 | <http://127.0.0.1:8001/?student=1> | FAQ、建立工單、查看結果 |
| 處室版 | <http://127.0.0.1:8001/office> | 處室回覆、結案及轉單 |
| 管理員版 | <http://127.0.0.1:8001/admin> | 全校工單、統計及設定 |
| 外觀設定 | <http://127.0.0.1:8001/design> | 學生端配色、文案與分類設定 |
| 使用說明 | <http://127.0.0.1:8001/guide> | 學生與處室的圖文操作說明（前台首頁不提供連結） |
| 健康檢查 | <http://127.0.0.1:8001/api/health> | FAQ、向量庫與 Ollama 狀態 |
| API 文件 | <http://127.0.0.1:8001/docs> | FastAPI Swagger 文件 |

### 4. 密碼位置

- 管理員密碼：`admin-token.txt`
- 處室密碼清單：`office-login-codes.txt`
- 程式使用的處室密碼：`office-tokens.json`
- 外觀設定頁密碼：管理員密碼即可登入；系統也會自動產生一組專用密碼於 `theme-admin-token.txt`

這些檔案由安裝程式產生並已加入 `.gitignore`，不可上傳或公開。

### 5. 停止

```powershell
.\stop.ps1
```

停止服務不會刪除 FAQ、工單、評分或設定。

### 6. 常駐與自動重啟

正式機（ai-faq.shu.edu.tw）由 Windows 排程工作 `shu_faq-backend` 執行 `scripts/faq_watchdog.ps1`：

- 開機時就執行，不需要有人登入（排程登入類型為 S4U；建立或修改開機觸發需要系統管理員權限）。
- 每 30 秒檢查 8001 埠，沒有服務時會讀取密碼檔、必要時先啟動 Ollama，再以 `--host 0.0.0.0` 啟動 uvicorn；日誌接續寫入 `server.out.log`、`server.err.log`，看門狗本身的紀錄在 `watchdog.log`。
- **改完 Python 程式要重啟時**：結束佔用 8001 埠的程序即可，看門狗約 30 秒內會自動重新啟動。

```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8001 -State Listen).OwningProcess -Force
```

- **要真正停止服務時**，先停用排程，否則 `stop.ps1` 停掉後會被看門狗自動拉起來：

```powershell
Disable-ScheduledTask -TaskName shu_faq-backend
Stop-ScheduledTask -TaskName shu_faq-backend
```

恢復時執行 `Enable-ScheduledTask -TaskName shu_faq-backend` 與 `Start-ScheduledTask -TaskName shu_faq-backend`。

## FAQ CSV

FAQ 來源是 `data/faq.csv`，請使用 UTF-8 或 UTF-8 with BOM。

```csv
id,category,question,answer,url,keywords,office,email,updated_at,update_note
Q001,選課相關,如何加退選課程？,請登入選課系統辦理加退選,https://example.edu.tw/course,加退選 選課 教務處,教務處,course@example.edu.tw,2026-09-10 16:36,匯入更新：主責單位（空白 → 教務處）
```

| 欄位 | 必填 | 說明 |
|---|---:|---|
| `id` | 是 | 唯一且固定的資料 ID |
| `category` | 否 | 前台分類及搜尋資訊 |
| `question` | 是 | FAQ 問題 |
| `answer` | 是 | 正式回答 |
| `url` | 否 | 官方公告或原始資料連結 |
| `keywords` | 否 | 處室、同義詞及補充關鍵字；留空會自動填入「分類＋主責單位」 |
| `office` | 否 | 主責單位 |
| `email` | 否 | 該題的承辦信箱 |
| `updated_at` | 系統 | 最後更新時間（台灣時間），新增、匯入或後台編輯時自動寫入 |
| `update_note` | 系統 | 最後一次改了什麼，例如「匯入新增」「匯入更新：主責單位（空白 → 總務處）」「重新匯入，內容無變更」「後台編輯：建議答案」 |

`updated_at`、`update_note` 由系統維護，不需要也不會從試算表匯入。

平常請直接用「常見問題管理」後台維護，不需要停機。若手動改過 CSV，再執行：

```powershell
.\stop.ps1
.\update_faq.ps1
.\start.ps1
```

這會重建 FAQ 向量資料，不會刪除工單 SQLite 資料。

## 常見問題管理後台

網址 <http://127.0.0.1:8001/faq-admin>，用管理員密碼登入（與工單後台同一組，也可從工單後台上方的「常見問題管理」進入）。

### 匯入

三種來源都會先做預覽，確認後才寫入：

1. **Google 試算表網址**：貼上編輯網址即可，系統會自動轉成 CSV 匯出網址並讀取網址中 `gid` 指定的工作表。試算表需設為「知道連結的任何人皆可檢視」。
2. **上傳檔案**：`.csv`、`.tsv`、`.xlsx`。
3. **直接貼上**：在試算表整片複製後貼上（含標題列）。

標題列會自動對應欄位，中英文皆可：

| 試算表標題 | 對應欄位 |
|---|---|
| 問題編號／編號／序號／`id` | `id` |
| 分類／類別／`category` | `category` |
| 問題／題目／`question` | `question` |
| 建議答案／答案／回答／`answer` | `answer` |
| 依據／來源連結、網址、`url` | `url` |
| 主責單位／承辦單位／處室 | `office` |
| 信箱／電子信箱／`email` | `email` |
| 關鍵字／`keywords` | `keywords` |

只有「問題」與「建議答案」是必填，缺這兩欄的列會在預覽中標成「略過」。

每一列會依下列順序決定是更新舊題還是新增：

1. 問題編號是後台匯出的固定 ID（例如 `Q012`、`AUTO-…`）且知識庫有這一筆 → 更新那一筆。
2. 題目文字與知識庫某一題相同（忽略空白、換行與標點）→ 更新那一筆。
3. 都不符合 → 新增，編號接在目前最大的 `Q` 號之後。試算表自己編的 1、2、3 不會被當成既有的 `Q001`、`Q002`。

更新舊題時，試算表空白的欄位、或只差空白換行的欄位會保留原本內容；分類沿用知識庫既有寫法；「依據／來源連結」若混有說明文字與被換行切斷的網址，網址會接回放進 `url`，其餘文字併入關鍵字。

預覽會先提醒需要人工判斷的列：

- **略過**：沒有答案，或與同一份表前面的列題目重複（只匯入第一次出現的那列）。
- **編號衝突**：編號對到的舊題題目不同，匯入會把它蓋掉，預設不勾選。
- **相似提醒**：要新增的題目與舊題答案一字不差，或題目語意相似度達 0.85。
- **相關舊題**：語意相似度 0.72～0.85 的舊題，僅供參考。

預覽表可逐列勾選，並選擇匯入模式：

- **合併更新**（預設）：同編號或同一題會更新原本那筆，並記錄更新時間與更新內容；沒出現在這份資料的舊題目保留。
- **完全取代**：清空知識庫，只留下這次匯入的資料。

匯入完成後會顯示逐筆結果報告（更新／新增／無變更／略過與原因），題目列表可選「最近更新在前」查看剛改過的題目。每次匯入前會自動備份舊的 `data/faq.csv` 到 `data/faq-backups/`，保留最近 20 份。

### 編輯與刪除

清單支援關鍵字搜尋、分類與主責單位篩選、分頁。點「編輯」可修改全部欄位，也可以「＋ 新增一筆」或刪除。存檔後同時更新 `data/faq.csv` 與向量庫，前台搜尋與 AI 回答立即使用新內容，不需要重啟。

「重建向量」會用目前 CSV 重算全部向量，資料異常時使用。

## 工單流程

```text
學生提問
  ├─ 找到 FAQ → 顯示 AI 整理回答與來源
  └─ 找不到 FAQ → 匿名建立工單
                      │
                      ▼
                  AI 判斷處室
                      │
                      ▼
       寄信給處室（問題＋連結＋處室密碼）
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
      處室回覆結案           不屬於本處室
          │                       └─ 轉單並通知新處室
          ▼
寄出 Q&A 與評分連結 → 1～5 星評分
          │
          ├─ 3～5 星：保留結案
          └─ 1～2 星：自動重新開啟
          │
          ▼
Q&A 自動寫回 FAQ CSV 與向量知識庫
```

## Email 設定

未設定 Email 時，FAQ、AI 與工單仍可使用，但通知信會顯示寄送失敗。

### Gmail OAuth 2.0（建議）

1. 在 Google Cloud Console 建立專案。
2. 啟用 Gmail API。
3. 設定 OAuth 同意畫面。
4. 建立「桌面應用程式」OAuth 用戶端。
5. 將下載的 JSON 命名為 `gmail-oauth-client.json`，放在專案根目錄。
6. 執行：

```powershell
.\.venv\Scripts\python.exe .\authorize_gmail.py
```

7. 在瀏覽器完成授權，系統會建立 `gmail-oauth-token.json`。
8. 重新啟動 FAQ 系統。

OAuth 憑證與權杖已加入 `.gitignore`，不得提交 GitHub。

### SMTP

也可在管理員後台設定 SMTP 伺服器、連接埠、寄件帳號與應用程式密碼。Gmail 若使用 SMTP，通常需要先啟用兩步驟驗證並建立應用程式密碼。

### 收件地址

- 管理員可設定所有處室 Email。
- 處室登入後只能修改自己的通知地址。
- 管理員可在「學生回覆完成通知信箱」新增多個收件地址；處室結案時會同時寄送 Q、A 與評分連結。
- 初始範例是 `office-emails.example.json`。
- 實際設定寫入 `office-emails.json`，不會提交 GitHub。
- `default-email.txt` 是第一次啟動時的學生通知預設地址；之後可直接在管理員後台維護通知清單。
- 未來串接會員系統後，可改用會員資料中的學生 Email。

## Cloudflare 臨時公開

確認本機 `127.0.0.1:8001` 正常後，安裝 `cloudflared` 並執行：

```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```

終端機會顯示隨機 `https://*.trycloudflare.com` 網址。Quick Tunnel 只適合臨時展示：網址每次可能改變、關閉程式後失效，而且沒有正常運作時間保證。電腦、FastAPI、Ollama 及 Tunnel 都必須保持執行。

正式環境應使用自有網域、Cloudflare Named Tunnel、會員登入、速率限制及正式備份。不要公開 Ollama 或本機資料庫連接埠。

## 資料位置與備份

| 路徑 | 內容 | 提交 GitHub |
|---|---|---:|
| `data/faq.csv` | FAQ 原始資料 | 是 |
| `data/qdrant-local/` | FAQ 向量索引 | 否，可重建 |
| `data/analytics.db` | 工單、事件、評分及統計 | 否 |
| `admin-token.txt` | 管理員密碼 | 否 |
| `office-tokens.json` | 處室密碼 | 否 |
| `office-emails.json` | 實際通知信箱 | 否 |
| `gmail-oauth-client.json` | OAuth 用戶端憑證 | 否 |
| `gmail-oauth-token.json` | Gmail OAuth 權杖 | 否 |
| `default-email.txt` | 單機評分測試信箱 | 否 |
| `data/site-config.json` | 前台外觀與文案設定 | 否 |
| `theme-admin-token.txt` | 外觀設定頁密碼 | 否 |

建議停止服務後備份 `data/faq.csv`、`data/analytics.db`、Email 設定與必要憑證。`data/qdrant-local` 可不備份，因為能從 FAQ CSV 重新建立。

## 專案結構

```text
rags/
├─ backend/
│  ├─ main.py                 FastAPI 路由與權限
│  ├─ analytics.py            SQLite 工單、評分與統計
│  ├─ embedding.py            多語言 Embedding
│  ├─ qdrant_service.py       本機向量庫
│  ├─ llm_service.py          Ollama 回答與處室分派
│  ├─ mail_service.py         Gmail／SMTP 通知
│  ├─ knowledge_service.py    已解決工單回寫 FAQ 與分類清單
│  ├─ faq_service.py          FAQ 匯入、編輯與向量同步
│  └─ theme_service.py        前台外觀與文案設定
├─ frontend/                  學生、處室及管理員頁面
│  ├─ guide.html              使用說明頁 /guide
│  └─ guide/                  使用說明頁的截圖
├─ scripts/                   匯入、搜尋及健康檢查
│  └─ faq_watchdog.ps1        常駐看門狗（排程 shu_faq-backend 執行）
├─ data/faq.csv               FAQ 來源
├─ setup.ps1                  首次安裝
├─ start.ps1                  啟動
├─ stop.ps1                   停止
└─ update_faq.ps1             重建向量庫
```

## API 摘要

完整文件：<http://127.0.0.1:8001/docs>

![外觀 API](docs/images/07-api-design.png)

*Swagger UI 的外觀設定 API 區段。不需登入即可查看介面定義，實際呼叫需帶
`X-Design-Token` 標頭。其中 `POST/DELETE /api/design/asset/{kind}` 是圖片上傳與移除，
`kind` 可為 `logo` / `page_bg` / `avatar_ai` / `avatar_user`。*

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/health` | FAQ 數量、向量庫及 Ollama 狀態 |
| `GET` | `/api/categories` | 側欄分類與各類代表問題（參數 `limit`，1～20） |
| `POST` | `/api/search` | FAQ 語意搜尋 |
| `POST` | `/api/ask` | 搜尋後由 Ollama 整理回答 |
| `POST` | `/api/tickets` | 建立並分派工單 |
| `GET` | `/api/tickets/{ticket_no}` | 使用存取碼查看學生工單 |
| `POST` | `/api/tickets/{ticket_no}/rating` | 提交星級評分 |
| `GET` | `/api/office/tickets` | 處室工單清單 |
| `PATCH` | `/api/office/tickets/{ticket_no}` | 處室回覆、結案或轉派 |
| `GET` | `/api/site-config` | 前台文案與外觀設定（公開） |
| `GET` | `/api/design/config` | 外觀設定與可調欄位清單 |
| `PUT` | `/api/design/config` | 儲存外觀與文案設定 |
| `POST` | `/api/design/preview.css` | 產生預覽 CSS，不寫入檔案 |
| `POST` | `/api/design/reset` | 還原預設外觀 |
| `GET` | `/api/admin/stats` | 管理統計 |
| `GET` | `/api/admin/tickets.csv` | 匯出工單 CSV |
| `GET` | `/api/admin/faqs` | 所有常見問題與統計 |
| `POST` | `/api/admin/faqs` | 新增一筆常見問題 |
| `PUT` | `/api/admin/faqs/{id}` | 修改指定常見問題 |
| `DELETE` | `/api/admin/faqs/{id}` | 刪除常見問題（含向量） |
| `POST` | `/api/admin/faqs/preview` | 解析試算表／檔案／貼上內容並比對，不寫入 |
| `POST` | `/api/admin/faqs/import` | 匯入預覽確認過的資料（`merge` 或 `replace`） |
| `POST` | `/api/admin/faqs/reindex` | 依現有 CSV 重建全部向量 |
| `GET` | `/api/admin/faqs.csv` | 匯出常見問題 CSV |
| `GET` | `/api/admin/faqs/template.csv` | 下載匯入欄位範本 |

## 健康檢查

先啟動系統，再執行：

```powershell
.\.venv\Scripts\python.exe .\scripts\health_check.py
.\.venv\Scripts\python.exe .\scripts\test_search.py
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

正常結果應包含 `status: ok`、FAQ `points` 大於 0，以及 `llm.connected`、`llm.available` 為 `true`。

## 常見問題

### PowerShell 禁止執行指令碼

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### 找不到 Python

重新安裝 Python 3.11 以上並勾選 `Add Python to PATH`，再重新開啟 PowerShell。

### Ollama 無法連線

```powershell
ollama serve
ollama pull qwen2.5:3b
```

### FAQ 數量為 0 或搜尋不到

```powershell
.\stop.ps1
.\update_faq.ps1
.\start.ps1
```

### 8001 連接埠被占用

```powershell
Get-NetTCPConnection -LocalPort 8001
```

關閉占用連接埠的舊程序後再執行 `start.ps1`。

### Gmail 沒收到信

- 確認 OAuth 或 SMTP 設定成功。
- 查看垃圾郵件與促銷分類。
- 確認處室 Email 不是範例地址。
- 確認 `default-email.txt` 已改成測試信箱。
- 在管理後台查看寄送狀態與錯誤。

### 結案後沒有進入知識庫

- 工單必須為「已解決」。
- 回覆不可空白。
- 工單事件應顯示「已將本工單 Q&A 寫入知識庫」。
- 確認 `data/faq.csv` 可寫入且磁碟空間足夠。

## 安全注意事項

- **服務綁定 `0.0.0.0`**，同一區網的其他電腦可直接連到這台機器的 8001 埠（Cloudflare Tunnel 本身走 `127.0.0.1:8001`，不受此設定影響）。
  本系統沒有正式登入機制，區網若不可信，請把 `start.ps1` 的 `--host` 改為 `127.0.0.1`，並改用 Cloudflare Tunnel 對外。
  另請確認 Windows 防火牆對 8001 埠的規則符合預期。
- 不要提交 `.gitignore` 已排除的密碼、OAuth、資料庫及 Email 設定。
- 不要把管理員或處室密碼提供給學生。
- 工單連結包含存取碼，不應公開分享。
- 正式環境應串接學校 SSO／會員系統及正式 RBAC 權限。
- 正式公開前應加入 HTTPS、速率限制、稽核紀錄、備份及弱點掃描。
- FAQ 與工單可能含個資，應遵守校方規範及相關法令。

## 後續可擴充

- 串接學校 SSO、LDAP 或會員系統。
- 自動取得學生 Email，取代固定測試信箱。
- 正式 RBAC 權限及處室帳號管理。
- PostgreSQL 或其他正式資料庫。
- 自有網域與 Cloudflare Named Tunnel。
- 附件、SLA、催辦與通知排程。
- FAQ 審核流程，避免未審核回答直接公開。

## GitHub 上傳前檢查

```powershell
git status
git ls-files
```

確認沒有追蹤：`admin-token.txt`、`office-tokens.json`、`office-login-codes.txt`、`各處室與後台連結密碼.txt`、Gmail OAuth JSON、`data/analytics.db`、`data/qdrant-local/` 或 `public-url.txt`。以上皆已列入 `.gitignore`。

## 授權與資料權利

本專案尚未預設 LICENSE。若要讓其他人自由使用、修改或散布，請加入 MIT、Apache-2.0 或其他適合的授權。

`data/faq.csv` 可能包含學校規章、聯絡方式或其他校務資料。公開前請確認發布權限、內容正確性、個資規範及更新責任。
