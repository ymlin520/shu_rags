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
$offices = @('教務處-課程與選課','教務處-學籍與註冊','教務處-成績與證明','教務處-畢業資格','教務處-學分抵免與跨域學習','教務處-研究生與學位考試','教務處-教師教學行政','教務處-開課與排課','教務處-招生及新生','教務處-系所與綜合','學務處生輔組','學務處課外組','學務處生涯組','學務處諮商中心','學務處衛保組','學務處宿舍中心','學務處原民中心','學務處軍訓室','性別平等教育委員會','性別所','性別平等教育中心','兩岸事務中心','國際事務中心','總務處','圖書資訊處-網路組','圖書資訊處-系統組','圖書資訊處-圖書資訊服務組','教學發展中心-企劃管考組','教學發展中心-教學資源組','秘書室','人事室','會計室','稽核室','公共事務室','社會資源發展中心','舍我紀念館','民意調查中心','世新電台','其他行政單位')
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
