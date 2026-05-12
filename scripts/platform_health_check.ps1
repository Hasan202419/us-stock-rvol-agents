# Loyiha: unit testlar + barcha .env asosidagi API jonli tekshiruv.
#
#   cd C:\Users\o8324\us-stock-rvol-agents
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\platform_health_check.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "=== pytest ===" -ForegroundColor Cyan
python -m pytest -q --tb=line
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "=== check_apis.py ===" -ForegroundColor Cyan
python scripts\check_apis.py
exit $LASTEXITCODE
