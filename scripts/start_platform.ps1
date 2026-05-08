param(
    [int]$Port = 8501,
    [switch]$WithTelegram
)

$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $root

Write-Host "== us-stock-rvol-agents local start ==" -ForegroundColor Cyan
Write-Host "Root: $root"
Write-Host "Dashboard: http://localhost:$Port"

if ($WithTelegram) {
    Write-Host "Telegram bot second PowerShell oynasida ishga tushadi." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$root'; python scripts\telegram_command_bot.py"
    )
}

python -m streamlit run dashboard.py --server.port $Port --server.address 0.0.0.0
