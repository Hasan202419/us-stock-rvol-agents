# Telegram: skan xabaridan "Universe / Top / TELEGRAM_BOT_REPLY_TOP_N" qatorini olib tashlash + push.
#   powershell -ExecutionPolicy Bypass -File .\scripts\push_telegram_scan_message_cleanup.ps1
# Faqat bu skriptni repoga qo'shish:
#   powershell -ExecutionPolicy Bypass -File .\scripts\push_telegram_scan_message_cleanup.ps1 -TrackSelfOnly

param([switch]$TrackSelfOnly)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

if ($TrackSelfOnly) {
    git add scripts/push_telegram_scan_message_cleanup.ps1
    git status -sb
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Hech narsa stage qilinmadi." -ForegroundColor Yellow
        exit 0
    }
    git commit -m "chore: track push_telegram_scan_message_cleanup.ps1"
    git push origin HEAD
    Write-Host "OK: skript repoga kiritildi." -ForegroundColor Green
    exit 0
}

$files = @(
    "scripts/telegram_command_bot.py",
    "scripts/deploy_render_worker.ps1",
    "scripts/commit_analyst_trade_plan.ps1",
    "scripts/push_telegram_scan_message_cleanup.ps1"
)
git add $files
git status -sb
git diff --cached --stat
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Stage bo'sh — o'zgarish yo'q yoki fayllar topilmadi." -ForegroundColor Yellow
    exit 0
}
git commit -m "fix(telegram): skan xabaridan Universe/Top meta qatorini olib tashlash"
git push origin HEAD

Write-Host "OK: push tugadi. Deploy: python scripts\trigger_render_deploy.py --clear-cache" -ForegroundColor Green
