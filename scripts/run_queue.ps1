# Navbat (tartib bilan): pip -> pytest -> check_apis [-> Render deploy]
# Ishga tushirish:        .\scripts\run_queue.ps1
# Pip o'tkazib:          .\scripts\run_queue.ps1 -SkipPip
# Lokal + Render deploy: .\scripts\run_queue.ps1 -DeployRender
#   (`.env` da RENDER_DEPLOY_HOOK_URL yoki RENDER_API_KEY + RENDER_SERVICE_ID)
param(
    [switch]$SkipPip,
    [switch]$DeployRender
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

if (-not $SkipPip) {
    Write-Host "=== 1/4 · pip install (requirements.txt) ===" -ForegroundColor Cyan
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "pip muvaffaqiyatsiz." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host ""
} else {
    Write-Host "(1/4 pip o'tkazib yuborildi)" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "=== 2/4 · pytest (unit testlar) ===" -ForegroundColor Cyan
python -m pytest -q --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Host "pytest muvaffaqiyatsiz." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "=== 3/4 · check_apis (tarmoq / kalitlar) ===" -ForegroundColor Cyan
python scripts\check_apis.py
$code = $LASTEXITCODE

if ($DeployRender) {
    Write-Host ""
    Write-Host "=== 4/4 · Render deploy (trigger_render_deploy.py) ===" -ForegroundColor Cyan
    python scripts\trigger_render_deploy.py
    $d = $LASTEXITCODE
    if ($d -ne 0) {
        Write-Host "Render deploy chaqiruvi muvaffaqiyatsiz (`.env` da Hook yoki API+SERVICE_ID tekshiring)." -ForegroundColor Red
        exit $d
    }
}

Write-Host ""
Write-Host "=== Keyingi qadamlar ===" -ForegroundColor Yellow
if (-not $DeployRender) {
    Write-Host "  · Bulutga deploy: .\scripts\run_queue.ps1 -DeployRender  yoki  .\scripts\deploy_render.ps1"
}
Write-Host "  · Render env: Dashboard > Environment — kalit nomlari lokal .env bilan mos"
Write-Host "  · Telegram alert: TELEGRAM_ALERTS_ENABLED=true yoki TELEGRAM_ALERT_ON_SCAN=true"
Write-Host "  · Prop: .env da PROP_* (Streamlit > Qoidalar — Prop & Halol)"
Write-Host "  · Dashboard: streamlit run dashboard.py"
Write-Host ""

exit $code
