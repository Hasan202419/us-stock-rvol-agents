# Babir skrining + Telegram UX — commit, push, Render deploy
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "=== pytest (telegram + scan) ===" -ForegroundColor Cyan
python -m pytest tests/test_scan_pipeline_and_telegram_cmd.py tests/test_scalp_daytrade_levels.py tests/test_trade_plan_format.py -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "`n=== git add ===" -ForegroundColor Cyan
git add `
  dashboard.py `
  scripts/telegram_command_bot.py `
  agents/scan_pipeline.py `
  agents/strategy_agent.py `
  render.yaml `
  .env.example `
  tests/test_scan_pipeline_and_telegram_cmd.py `
  scripts/ensure_render_telegram_worker.py

$status = git status --short
if (-not $status) {
    Write-Host "Commit uchun o'zgarish yo'q." -ForegroundColor Yellow
} else {
    Write-Host $status
    git commit -m @"
fix: restore Babir watchlist auto-push; dashboard and Telegram UX

- Auto-push includes kuzatuv ro'yxati by default (Babir screening)
- Dashboard splits pass signals vs watchlist; daily RSI/ATR in table
- Telegram reply keyboard and clearer scan message sections
- render.yaml: TELEGRAM_AUTO_PUSH_ENABLED and related worker env defaults
"@
}

Write-Host "`n=== git push ===" -ForegroundColor Cyan
git push -u origin HEAD

Write-Host "`n=== Render env sync (worker) ===" -ForegroundColor Cyan
python scripts/ensure_render_telegram_worker.py

Write-Host "`n=== Render deploy ===" -ForegroundColor Cyan
python scripts/trigger_render_deploy.py

Write-Host "`nOK" -ForegroundColor Green
git log -1 --oneline
git status -sb
