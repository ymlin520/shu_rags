$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw '找不到 Python。請先安裝 Python 3.11 以上，安裝時勾選 Add Python to PATH。'
}
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollama)) {
  throw '找不到 Ollama。請先從 https://ollama.com/download/windows 安裝。'
}
if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
  python -m venv .venv
}
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r '.\backend\requirements.txt'

function New-Secret([int]$Bytes = 24) {
  $buffer = New-Object byte[] $Bytes
  $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
  return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+','-').Replace('/','_')
}
if (-not (Test-Path '.\admin-token.txt')) { Set-Content '.\admin-token.txt' (New-Secret) -Encoding utf8 }
$offices = @('教務處註冊組','教務處課務組','學務處生活輔導組','學務處住宿服務組','國際處','總務處','資訊處','圖資處','系辦公室','其他行政單位')
if (-not (Test-Path '.\office-tokens.json')) {
  $tokens = [ordered]@{}
  foreach ($office in $offices) { $tokens[$office] = New-Secret 12 }
  $tokens | ConvertTo-Json | Set-Content '.\office-tokens.json' -Encoding utf8
  $tokens.GetEnumerator() | ForEach-Object { "$($_.Key)：$($_.Value)" } | Set-Content '.\office-login-codes.txt' -Encoding utf8
}
if (-not (Test-Path '.\mail-settings.json')) { Copy-Item '.\mail-settings.example.json' '.\mail-settings.json' }
if (-not (Test-Path '.\office-emails.json')) { Copy-Item '.\office-emails.example.json' '.\office-emails.json' }
if (-not (Test-Path '.\default-email.txt')) { Set-Content '.\default-email.txt' 'admin@example.edu.tw' -Encoding utf8 }

try { Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 | Out-Null }
catch { Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden; Start-Sleep -Seconds 4 }
& $ollama pull qwen2.5:3b
& '.\.venv\Scripts\python.exe' '.\scripts\import_faq.py'

Write-Host ''
Write-Host '安裝完成。請執行 .\start.ps1'
Write-Host '管理員密碼：' -NoNewline; Get-Content '.\admin-token.txt'
Write-Host '各處室密碼已寫入 office-login-codes.txt（請勿提交 GitHub）。'
