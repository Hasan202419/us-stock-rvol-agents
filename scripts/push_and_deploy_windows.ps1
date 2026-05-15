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
    $badRemote = $false
    try {
        $originUrl = (git remote get-url origin 2>$null).Trim()
        if ($originUrl) {
            Write-Log "git remote origin = $originUrl"
            if ($originUrl -match '(?i)(YOUR_|PLACEHOLDER|example\.github\.io|your_login|your_repository)') {
                $badRemote = $true
            }
        }
    } catch { }

    if ($badRemote) {
        Write-Log "ERROR: 'origin' hali namuna URL — GitHubdagi HA QI REPO manziliga almashtiring:"
        Write-Log "  git remote set-url origin https://github.com/SIZNING_USER/us-stock-rvol-agents.git"
        Write-Log "Keyin GitHubda shu nomli repo yarating (yoki mavjud reponing URL ini qo'ying)."
        exit 16
    }
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

    Write-Log "git push via scripts/git_push_from_env.py (GITHUB_TOKEN from .env)"
    python (Join-Path $RepoRoot "scripts\git_push_from_env.py") --branch $Branch 2>&1 | ForEach-Object { Write-Log "git_push: $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: git push muvaffaqiyatsiz (exit=$LASTEXITCODE)"
        Write-Log ".env da GITHUB_TOKEN=ghp_... (repo scope) — https://github.com/settings/tokens"
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
