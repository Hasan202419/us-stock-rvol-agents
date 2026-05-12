# .env.bak tarixi GitHub push protection sabab bo'lgan commitlardan olib tashlaydi, keyin force push.
# Ishga tushirish: PowerShell (Run as user) — loyiha ildizidan:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fix_secret_history.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$root = Get-Location

if (-not (Test-Path .git)) {
    Write-Error "Bu papkada .git yo'q: $root"
    exit 1
}

# Zaxira nomlarini endi kuzatmaslik
$gi = Join-Path $root ".gitignore"
$lines = @(".env.bak", "*.bak")
foreach ($l in $lines) {
    if (Test-Path $gi) {
        $c = Get-Content $gi -Raw -ErrorAction SilentlyContinue
        if ($c -notmatch [regex]::Escape($l)) {
            Add-Content -Path $gi -Value "`n$l"
            Write-Host "Qo‘shildi .gitignore: $l"
        }
    }
}

Write-Host "filter-branch: tarixdan .env.bak olib tashlanmoqda..."
git filter-branch --force --index-filter "git rm --cached --ignore-unmatch .env.bak" --prune-empty HEAD

Write-Host "reflog / gc..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

if (Test-Path .gitignore) {
    git add .gitignore
    git diff --cached --quiet
    if (-not $?) {
        git commit -m "chore: ignore .env backup files" 2>$null
    }
}

Write-Host "Tekshiruv: .env.bak tarixda qolganmi?"
git log --all --full-history --oneline -- .env.bak
if ($LASTEXITCODE -eq 0) {
    $log = git log --all --full-history --oneline -- .env.bak 2>$null
    if ($log) {
        Write-Warning "Hali .env.bak tarixda ko‘rinadi — qo‘lda tekshiring."
    }
}

Write-Host "Push (force-with-lease)..."
git push -u origin main --force-with-lease

Write-Host "Tayyor. GitHub sahifasini tekshiring."
