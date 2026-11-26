$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
function Log($msg) { Write-Output ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) }

# 1. генерирай index.html
python build-index.py
if ($LASTEXITCODE -ne 0) { Log "BUILD-INDEX FAILED"; exit 1 }

# 2. commit само publish артефакти (allowlist — не git add -A)
function Add-PublishArtifact($path) {
    if (Test-Path -LiteralPath $path) { git add -- $path }
}
$publishFiles = @(
    'index.html', 'news.html', 'events.html', 'vreme.html', 'search.html', 'search.json', 'feed.xml',
    'assistants.html', 'scout.html', 'podari.html', 'radar.html', 'cars.html', 'aiplan.html', 'week.html',
    'favicon.ico', 'favicon.svg', 'favicon-32.png', 'apple-touch-icon.png', 'icon-192.png', 'icon-512.png',
    'site.webmanifest', 'weather.html', 'assistants-content.html'
)
foreach ($f in $publishFiles) { Add-PublishArtifact $f }
foreach ($pattern in @('novini-*.html', 'digest-*.html', 'digest-week-*.html', 'digest-tonight-*.html', 'events-*.html')) {
    Get-ChildItem -File -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object { Add-PublishArtifact $_.Name }
}
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m ("site sync " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null
    Log "COMMIT: created"
} else {
    Log "COMMIT: none (no changes)"
}

# 3. без remote още няма какво да се качва
# (git remote връща празно и код 0 при липса на remote — за разлика от
# git remote get-url, който пише грешка и би прекъснал скрипта)
$remotes = git remote 2>$null
if (-not $remotes) { Log "NO-REMOTE: repo not linked to GitHub yet"; exit 0 }

# 4. GitHub Pages — включи веднъж, после само чети. Работи само ако gh е
# влязъл на този компютър; иначе се пропуска тихо (Pages се включва ръчно
# от Settings на репото). Никога не проваля скрипта и не спира push-а.
gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    try {
        $pages = gh api "repos/frashev/digest-site/pages" --jq '.html_url' 2>$null
        if (-not $pages) {
            gh api "repos/frashev/digest-site/pages" -X POST -f "source[branch]=main" -f "source[path]=/" --jq '.html_url' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { Log "PAGES: enabled" } else { Log "PAGES: enable failed (ignored)" }
        } else {
            Log ("PAGES: " + $pages)
        }
    } catch { Log "PAGES: ensure failed (ignored)" }
} else {
    Log "PAGES: skipped (gh not logged in — enable Pages from repo Settings)"
}

# 5. push през SSH ключа на този компютър (gh не е нужен)
git push
if ($LASTEXITCODE -ne 0) {
    git push -u origin main
    if ($LASTEXITCODE -ne 0) { Log "PUSH-FAILED: will retry next run"; exit 0 }
}
Log "PUSH: ok"
exit 0
