#Requires -Version 5.1
<#
.SYNOPSIS
    Loyihani GitHub ga yuboradi (faqat mahalliy kompyuterda).

.PARAMETER RemoteUrl
    Masalan: https://github.com/myuser/us-stock-rvol-agents.git  (SIZNING_USER yozmang!)

.PARAMETER GitUserName / GitUserEmail
    Repoga **faqat shu loyiha uchun** identifikator (global sozlama ixtiyoriy).

.EXAMPLE
    .\scripts\push_to_github.ps1 -RemoteUrl "https://github.com/hasan/us-stock-rvol-agents.git" `
      -GitUserName "Hasan" -GitUserEmail "hasan@example.com" -InitializeGit
#>
param(
    [Parameter(Mandatory = $true)][string]$RemoteUrl,
    [string]$CommitMessage = "chore: sync us-stock-rvol-agents",
    [string]$GitUserName,
    [string]$GitUserEmail,
    [switch]$InitializeGit
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

Write-Host "Loyiha ildizi: $root"

if ($RemoteUrl -match 'SIZNING_USER|SIZNING_REPO') {
    Write-Error "RemoteUrl hali namuna: GitHubdagi haqiqiy USER/REPO yozing. Masalan: https://github.com/o8324/us-stock-rvol-agents.git"
}

if (-not (Test-Path (Join-Path $root ".git"))) {
    if ($InitializeGit) {
        git init
    }
    else {
        Write-Error "`.git yo'q. -InitializeGit bering yoki `git init` qiling."
    }
}

if ($GitUserName -and $GitUserEmail) {
    git config user.name $GitUserName
    git config user.email $GitUserEmail
    Write-Host "Identitet (faqat bu repo): $($GitUserName) <$($GitUserEmail)>"
}
else {
    $gn = git config user.name
    $ge = git config user.email
    if ([string]::IsNullOrWhiteSpace($gn) -or [string]::IsNullOrWhiteSpace($ge)) {
        Write-Error @"
Git user.name / user.email yo'q.

Variant A — butun tizim uchun:
  git config --global user.email "siz@example.com"
  git config --global user.name "Ism Familiya"

Variant B — faqat shu skriptda:
  .\scripts\push_to_github.ps1 -RemoteUrl "..." -GitUserName "Ism" -GitUserEmail "siz@example.com"
"@
    }
}

$envTracked = @(git ls-files -- ".env")
if ($envTracked.Count -gt 0 -and $envTracked[0] -eq ".env") {
    Write-Error ".env repoda — git rm --cached .env && git commit -m 'stop tracking .env'"
}

git add -A
$stagedEnv = @(git diff --cached --name-only | Where-Object { $_ -match '(^|/)\.env$' })
if ($stagedEnv.Count -gt 0) {
    Write-Error ".env stagelangan — git reset HEAD .env"
}

$hasChanges = $false
git diff --quiet 2>$null
if ($LASTEXITCODE -ne 0) { $hasChanges = $true }
git diff --cached --quiet 2>$null
if ($LASTEXITCODE -ne 0) { $hasChanges = $true }

if (-not $hasChanges) {
    $head = git rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Commit yo'q va stage qilinadigan o'zgarish ham yo'q. Fayl qo'shing yoki identitet/commit muammosini tekshiring."
    }
    Write-Host "O'zgarish yo'q — mavjud commit bilan push qilinadi."
}
else {
    git commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) {
        Write-Error "git commit xato. Masalan: identitet, yoki bo'sh commit qoidalari — yuqoridagi xabarni o'qing."
    }
}

git branch -M main
if ($LASTEXITCODE -ne 0) {
    Write-Error "main branchga o'tkazib bo'lmadi (odatda commit yo'q bo'lsa)."
}

$remotes = git remote
if ($remotes -contains "origin") {
    git remote set-url origin $RemoteUrl
}
else {
    git remote add origin $RemoteUrl
}

Write-Host "Push: $RemoteUrl"
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Error "git push xato — URL to'g'rimi? GitHub login yoki PAT bilan autentifikatsiya qildingizmi?"
}

Write-Host "Tayyor. Renderda shu reponi ulashingiz mumkin."
