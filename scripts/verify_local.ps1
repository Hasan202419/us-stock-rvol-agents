# Loyiha ildizidan (us-stock-rvol-agents):  .\scripts\verify_local.ps1
# To'liq navbat (pip + pytest + check_apis):   .\scripts\run_queue.ps1
# Yoki:  powershell -File .\scripts\verify_local.ps1
$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

Write-Host "== pytest (unit testlar) ==" -ForegroundColor Cyan
python -m pytest -q --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Host "pytest muvaffaqiyatsiz." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "== check_apis (tarmoq / kalitlar) ==" -ForegroundColor Cyan
python scripts\check_apis.py
exit $LASTEXITCODE
