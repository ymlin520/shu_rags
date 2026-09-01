$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path '.\backend.pid') { throw '請先執行 .\stop.ps1，再更新 FAQ。' }
& '.\.venv\Scripts\python.exe' '.\scripts\import_faq.py'
if ($LASTEXITCODE -ne 0) { throw 'FAQ 匯入失敗。' }
Write-Host 'FAQ 更新完成，請執行 .\start.ps1。'
