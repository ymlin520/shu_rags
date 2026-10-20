# FAQ backend watchdog, started at boot by the scheduled task "shu_faq-backend".
# Keeps uvicorn serving 0.0.0.0:8001 (IIS proxies ai-faq.shu.edu.tw to it).
# If the port is already served (for example a manual restart), it only waits.
# To restart after code changes: stop the process listening on 8001; this script relaunches it within ~10 seconds.
$ErrorActionPreference = 'Continue'
$root = 'C:\shu_rags'
Set-Location -LiteralPath $root
$ollama = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Ollama\ollama.exe'
# 模型放在 C:\LLM-Model（qwen2.5:3b 回答、qwen3.5:9b 相關性檢查）。沒指定的話 Ollama 會去讀
# ~\.ollama\models，找不到模型，AI 回答與相關性過濾都會 404（2026-10-15 ~ 10-20 發生過）。
$env:OLLAMA_MODELS = 'C:\LLM-Model'

function Write-Watchdog([string]$text) {
  Add-Content -LiteralPath (Join-Path $root 'watchdog.log') -Value ('{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $text)
}

Write-Watchdog 'watchdog started'
while ($true) {
  if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 30
    continue
  }
  try { Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 | Out-Null }
  catch {
    if (Test-Path -LiteralPath $ollama) {
      Write-Watchdog 'starting ollama'
      Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
      Start-Sleep -Seconds 5
    }
  }
  $env:FAQ_ADMIN_TOKEN = (Get-Content -Raw -LiteralPath (Join-Path $root 'admin-token.txt')).Trim()
  $env:FAQ_DEFAULT_EMAIL = (Get-Content -Raw -LiteralPath (Join-Path $root 'default-email.txt')).Trim()
  Write-Watchdog 'starting uvicorn on 0.0.0.0:8001'
  & cmd.exe /c '.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 >> server.out.log 2>> server.err.log'
  Write-Watchdog "uvicorn exited with code $LASTEXITCODE"
  Start-Sleep -Seconds 10
}
