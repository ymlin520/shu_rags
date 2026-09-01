$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path '.\backend.pid') {
  $servicePid = (Get-Content -Raw '.\backend.pid').Trim()
  if ($servicePid) { Stop-Process -Id $servicePid -ErrorAction SilentlyContinue }
  Remove-Item '.\backend.pid' -Force -ErrorAction SilentlyContinue
}
Write-Host 'FAQ 網站服務已停止。本機資料與工單均已保留。'
