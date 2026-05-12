# Lokaldan Render Telegram worker env sinxronlash + tez tekshiruv.
# Talab: loyiha ildizida ishga tushiring; .env da RENDER_API_KEY, RENDER_WORKER_SERVICE_ID.
#
#   cd C:\Users\o8324\us-stock-rvol-agents
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync_render_telegram_env_and_smoke.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "=== ensure_render_telegram_worker.py ===" -ForegroundColor Cyan
python scripts\ensure_render_telegram_worker.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "=== render_worker_smoke.py ===" -ForegroundColor Cyan
python scripts\render_worker_smoke.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "=== check_apis.py (barcha ulangan API) ===" -ForegroundColor Cyan
python scripts\check_apis.py
exit $LASTEXITCODE
