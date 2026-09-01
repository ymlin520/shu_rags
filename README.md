# 校務 FAQ 智慧問答與工單系統（Windows 單機版）

可直接在 Windows 電腦執行的校務 FAQ 系統。包含語意搜尋、本機 AI 回答、自動建立與分派工單、處室後台、總管理後台、Email 通知、星級評分，以及工單結案後自動回寫知識庫。

## 主要功能

- FAQ 語意搜尋：Sentence Transformers 多語言向量模型。
- 本機 AI：Ollama `qwen2.5:3b`，FAQ 與問題不送至外部 AI API。
- 學生版：知識庫沒有答案時，一鍵匿名建立工單。
- AI 分派：依問題內容自動送至適合處室。
- 處室版：各處室使用專屬密碼，只看自己的工單，可回覆、結案、轉單及修改通知 Email。
- 管理員版：工單、處室統計、轉單數、處理時間、評分與 CSV 匯出。
- 寄信：新工單通知處室；結案後寄 Q、A 與 1～5 星評分連結。
- 知識成長：有效工單結案後，自動寫回 `data/faq.csv` 與本機向量庫。

## 系統需求

- Windows 10/11
- Python 3.11 以上（安裝時勾選 `Add Python to PATH`）
- [Ollama for Windows](https://ollama.com/download/windows)
- 第一次安裝需要網路，用來下載 Python 套件、Embedding 模型與 Ollama 模型。
- 不需要 Docker；向量資料庫儲存在專案的 `data/qdrant-local`。

## 下載後直接執行

在專案資料夾開啟 PowerShell，依序執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\start.ps1
```

首次安裝會自動建立 Python 環境、產生管理員與處室密碼、下載本機模型、匯入 FAQ，並建立不會提交至 GitHub 的本機設定檔。

啟動完成後：

- 學生版：<http://127.0.0.1:8001/?student=1>
- 處室版：<http://127.0.0.1:8001/office>
- 管理員版：<http://127.0.0.1:8001/admin>
- 健康檢查：<http://127.0.0.1:8001/api/health>

管理員密碼位於 `admin-token.txt`；處室密碼清單位於 `office-login-codes.txt`。兩者均已列入 `.gitignore`，不可上傳或公開。

停止服務：

```powershell
.\stop.ps1
```

## 更換 FAQ

編輯 `data/faq.csv`，使用 UTF-8 CSV，欄位為：

```text
id,category,question,answer,url,keywords
```

`id`、`question`、`answer` 必填，其餘可留空。修改後執行：

```powershell
.\stop.ps1
.\update_faq.ps1
.\start.ps1
```

## Email 設定

沒有設定 Email 時，其餘功能仍可正常使用。

### Gmail OAuth（建議）

1. 在 Google Cloud 建立「桌面應用程式」OAuth 用戶端，啟用 Gmail API。
2. 將下載的憑證命名為 `gmail-oauth-client.json` 放到專案根目錄。
3. 執行 `.\.venv\Scripts\python.exe .\authorize_gmail.py`。
4. 瀏覽器完成授權後會建立 `gmail-oauth-token.json`。

上述檔案均已列入 `.gitignore`，不得提交 GitHub。

### 收件地址

- 管理員可在管理後台設定各處室信箱。
- 各處室登入後只能修改自己的信箱。
- 單機測試版的學生評分通知地址放在 `default-email.txt`，預設為 `admin@example.edu.tw`，請改成自己的測試信箱。
- 未來串接會員系統時，可把結案信件收件人改為會員資料中的學生 Email。

## 暫時公開測試

可使用 Cloudflare Quick Tunnel 將 `http://127.0.0.1:8001` 暫時公開。Quick Tunnel 網址每次重啟可能改變，沒有永久上線保證。只公開 FastAPI 網站，不要公開 Ollama 或資料庫連接埠。

正式上線請使用自有網域、Cloudflare Named Tunnel、登入驗證、HTTPS、速率限制與正式會員權限系統。

## 資料與安全

`.gitignore` 已排除管理員與處室密碼、Gmail OAuth 憑證、工單資料庫、本機向量庫、Email 設定、臨時網址及執行紀錄。上傳前仍應執行 `git status`，確認沒有敏感檔案。

## 驗證

```powershell
.\.venv\Scripts\python.exe .\scripts\health_check.py
.\.venv\Scripts\python.exe .\scripts\test_search.py
```

## 授權與 FAQ 資料

請依 GitHub 專案需求加入適合的 LICENSE。FAQ 內容可能屬於學校資料，公開前請先確認發布權限與個資規範。
