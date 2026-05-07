#Requires -Version 5.1
<#
Bitta oqim: git commit + push va `python scripts/trigger_render_deploy.py` (`.env`dag RENDER hook/API).

Ishlatish (PowerShell, repo ichida):
  .\scripts\push_and_deploy_windows.ps1
  .\scripts\push_and_deploy_windows.ps1 -CommitMessage "fix: ..."
  .\scripts\push_and_deploy_windows.ps1 -DeployOnly     # pushsiz faqat Render trigger

LOG: state/push_deploy_last.log
#>
param(
    [string]$Branch = "",
    [string]$CommitMessage = "chore: sync from workstation",
    [switch]$DeployOnly
)

$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
$null = New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "state")
$LogPath = Join-Path $RepoRoot "state\push_deploy_last.log"

function Write-Log {
    param([string]$Msg)
    $line = "$(Get-Date -Format 'o') | $Msg"
    Add-Content -Path $LogPath -Value $line
    Write-Host $line
}

Write-Log "START repo=$RepoRoot"

if (-not $DeployOnly) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Log "ERROR: git topilmadi."
        exit 10
    }
    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        Write-Log "ERROR: .git yo'q — Cursor workspace nusxa bo'lishi mumkin; asosiy papkada ishga tushiring."
        exit 11
    }

    git add -A 2>&1 | ForEach-Object { Write-Log "git_add: $_" }
    $dirty = git status --porcelain 2>$null
    if (-not [string]::IsNullOrWhiteSpace($dirty)) {
        git commit -m $CommitMessage 2>&1 | ForEach-Object { Write-Log "git_commit: $_" }
        if ($LASTEXITCODE -ne 0) {
            Write-Log "ERROR: git commit muvaffaqiyatsiz (exit=$LASTEXITCODE)"
            exit 12
        }
    } else {
        Write-Log "git: o'zgarish yo'q"
    }

    $cur = (git branch --show-current 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = $cur }
    if ([string]::IsNullOrWhiteSpace($Branch)) {
        Write-Log "ERROR: branch nomi bermoqchi bo'lsangiz: -Branch main"
        exit 13
    }

    git push -u origin $Branch 2>&1 | ForEach-Object { Write-Log "git_push: $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: git push muvaffaqiyatsiz — remote/PAT tekshiring (exit=$LASTEXITCODE)"
        exit 14
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Log "ERROR: python topilmadi."
    exit 15
}

$trigger = Join-Path $RepoRoot "scripts\trigger_render_deploy.py"
& python $trigger 2>&1 | ForEach-Object { Write-Log "deploy: $_" }
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARNING: deploy skript exit=$LASTEXITCODE — .env RENDER_* yoki HTTPS hook tekshiring"
    exit $LASTEXITCODE
}

Write-Log "DONE"
exit 0
