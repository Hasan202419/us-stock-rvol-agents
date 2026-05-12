# Faqat Render deploy navbatiga qo'yish (REST yoki Deploy Hook — .env dan).
# Ishlatish:  .\scripts\deploy_render.ps1
# Opsiyen:    .\scripts\deploy_render.ps1 -ClearCache
param(
    [switch]$ClearCache
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

$pyArgs = @("scripts\trigger_render_deploy.py")
if ($ClearCache) { $pyArgs += "--clear-cache" }

Write-Host "=== Render deploy (trigger_render_deploy.py) ===" -ForegroundColor Cyan
python @pyArgs
exit $LASTEXITCODE
