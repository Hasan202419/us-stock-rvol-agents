# Loyiha ildizidagi .env fayliga ish stoli yorlig'i (.lnk) qo'shadi.
# Ishlatish: scripts\add_env_desktop_shortcut.bat yoki:
#   powershell -File scripts\add_env_desktop_shortcut.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"

if (-not (Test-Path -LiteralPath $envPath)) {
    Write-Host "`.env` topilmadi: $envPath" -ForegroundColor Yellow
    Write-Host "Avval .env yarating (.env.example dan nusxa yoki dashboard bir marta ishga tushiring)." -ForegroundColor Yellow
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $desktop) {
    Write-Host "Ish stoli papkasi topilmadi." -ForegroundColor Red
    exit 1
}

$shortcutPath = Join-Path $desktop "us-stock-rvol-agents.env.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $envPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "us-stock-rvol-agents — .env (loyiha bilan bir xil fayl)"
$shortcut.Save()

Write-Host "Yorlig' yaratildi: $shortcutPath" -ForegroundColor Green
Write-Host "Ish stolidan oching — haqiqiy fayl: $envPath"
