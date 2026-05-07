# Render REST API kaliti tekshiruvi (PowerShellda to'g'ri usul).
#
# CMD da `^` qator davomi ishlaydi; PowerShellda asosan ISHLAMAYDI — bitta qator yoki `cmd /c`, yoki pastdagi skript.
#
# Ishlatish (.env yuklanadi, RENDER_API_KEY odatda shu yerda):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_render_api.ps1
#
# Yoki muhitda:
#   $env:RENDER_API_KEY = "rnd_..."
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_render_api.ps1
#
# Curl bitta qator (PowerShell):
#   curl.exe -sS -i "https://api.render.com/v1/services?limit=1" -H "Accept: application/json" -H "Authorization: Bearer $env:RENDER_API_KEY"

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $root ".env"
if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $pair = $_.Split('=', 2)
        if ($pair.Count -eq 2) {
            $name = $pair[0].Trim()
            $val = $pair[1].Trim().Trim('"').Trim("'")
            if ($name) { Set-Item -Path "Env:$name" -Value $val }
        }
    }
}

$key = [string]$env:RENDER_API_KEY
if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host "RENDER_API_KEY bo'sh.`nMasalan:`n  `$env:RENDER_API_KEY = 'rnd_...'`nyoki `.env` faylda RENDER_API_KEY=rnd_..." -ForegroundColor Red
    exit 1
}

$key = $key.Trim()
$uri = "https://api.render.com/v1/services?limit=5"
$headers = @{
    Accept        = "application/json"
    Authorization = "Bearer $key"
}

try {
    $resp = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -ErrorAction Stop
    Write-Host "OK: Render API 200 javob berdi.`n" -ForegroundColor Green
    $resp | ConvertTo-Json -Depth 6
}
catch {
    Write-Host "Xato: $($_.Exception.Message)" -ForegroundColor Red
    $wrapped = $_.Exception
    while ($wrapped.InnerException) { $wrapped = $wrapped.InnerException }
    Write-Host $wrapped.Message -ForegroundColor Red
    if ($_.Exception.Response) {
        try {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            Write-Host $reader.ReadToEnd() -ForegroundColor Yellow
        }
        catch { }
    }
    exit 1
}
