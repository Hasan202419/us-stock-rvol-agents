# Telegram worker (va ixtiyoriy WEB) uchun Render deploy navbati.
# `.env`: RENDER_DEPLOY_HOOK_URL yoki RENDER_API_KEY + RENDER_SERVICE_ID (+ ixtiyoriy RENDER_WORKER_SERVICE_ID)
# Ishlatish (loyiha ildizidan):
#   powershell -ExecutionPolicy Bypass -File .\scripts\deploy_render_worker.ps1

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

Write-Host "=== Render deploy (clear cache) ===" -ForegroundColor Cyan
python scripts\trigger_render_deploy.py --clear-cache
if ($LASTEXITCODE -ne 0) {
    Write-Host "Deploy xato. Tekshiring: RENDER_DEPLOY_HOOK_URL yoki RENDER_API_KEY + RENDER_SERVICE_ID" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "OK: deploy navbati qo'yildi." -ForegroundColor Green
