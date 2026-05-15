# Qolgan barcha o'zgarishlarni commit + push + Render deploy (ixtiyoriy).
# Ishlatish: powershell -ExecutionPolicy Bypass -File scripts\commit_all_remaining.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "=== pytest ===" -ForegroundColor Cyan
python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "`n=== git add (qolgan fayllar) ===" -ForegroundColor Cyan
git add `
  agents/finviz_elite_export.py `
  src/config/settings.py `
  src/providers/zoya_client.py `
  docs/generated/.gitkeep `
  docs/CANONICAL_SPEC_V1.md `
  docs/GAP_ANALYSIS_V1.md `
  docs/RELEASE_RUNBOOK_RENDER.md `
  docs/RISK_GOVERNANCE_ACCEPTANCE.md `
  docs/STAGE_A_STABILITY_PACKAGE.md `
  docs/prompts/

$status = git status --short
if (-not $status) {
    Write-Host "Commit uchun o'zgarish yo'q — hammasi allaqachon commit qilingan." -ForegroundColor Yellow
} else {
    Write-Host $status
    git commit -m @"
docs: spec, runbook, prompts; chore: zoya settings and finviz export

- Add project documentation (canonical spec, gap analysis, Render runbook)
- Zoya client and settings tweaks for halal gate
- Finviz elite export adjustments
"@
}

Write-Host "`n=== git push ===" -ForegroundColor Cyan
git push origin main

if (Test-Path "scripts/trigger_render_deploy.py") {
    Write-Host "`n=== Render deploy ===" -ForegroundColor Cyan
    python scripts/trigger_render_deploy.py
}

Write-Host "`nOK: tugadi. git log -1:" -ForegroundColor Green
git log -1 --oneline
git status -sb
