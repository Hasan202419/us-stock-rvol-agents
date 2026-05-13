# Trade plan + /plan o'zgarishlarini commit + push (+ ixtiyoriy Render deploy).
#   powershell -ExecutionPolicy Bypass -File .\scripts\commit_analyst_trade_plan.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\commit_analyst_trade_plan.ps1 -SkipDeploy
# Env: RENDER_API_KEY + RENDER_SERVICE_ID (+ RENDER_WORKER_SERVICE_ID) yoki Deploy Hook URL lar.

param([switch]$SkipDeploy)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

$paths = @(
    "agents/trade_plan_format.py",
    "agents/chatgpt_analyst_agent.py",
    "agents/scan_pipeline.py",
    "agents/logger_agent.py",
    "scripts/telegram_command_bot.py",
    "scripts/ensure_render_telegram_worker.py",
    "dashboard.py",
    "README.md",
    ".env.example",
    "tests/test_trade_plan_format.py",
    "tests/test_platform_and_telegram_reliability.py"
)

git add @paths
git status -sb
$msg = "feat: analyst trade_plan JSON, /plan Telegram, dashboard expander, IGNITION docs"
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Hech narsa stage qilinmagan — commit o'tkazildi." -ForegroundColor Yellow
} else {
    git commit -m $msg
    git push origin HEAD
    Write-Host "OK: push tugadi." -ForegroundColor Green
}

if (-not $SkipDeploy) {
    Write-Host "=== Render deploy ===" -ForegroundColor Cyan
    python scripts\trigger_render_deploy.py --clear-cache
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Deploy chaqiruvi xato yoki sozlanmagan. Qo'lda: .\scripts\deploy_render_worker.ps1" -ForegroundColor Yellow
    }
}

Write-Host "Env sinxron (ixtiyoriy): python scripts\ensure_render_telegram_worker.py" -ForegroundColor Gray
