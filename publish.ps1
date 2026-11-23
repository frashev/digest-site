$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Log($msg) { Write-Output ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) }

# 1. генерирай index.html
python build-index.py
if ($LASTEXITCODE -ne 0) { Log "BUILD-INDEX FAILED"; exit 1 }

# 2. commit само при промени
git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m ("site sync " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null
    Log "COMMIT: created"
} else {
    Log "COMMIT: none (no changes)"
}

# 3. без remote още няма какво да се качва
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Log "NO-REMOTE: repo not linked to GitHub yet"; exit 0 }

# 4. push иска валиден gh вход на този компютър
gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Log "PUSH-SKIPPED: gh not logged in (run gh auth login on this PC)"; exit 0 }

# 5. GitHub Pages — включи веднъж, после само чети (best effort, никога не проваля скрипта)
try {
    $pages = gh api "repos/frashev/digest-site/pages" --jq '.html_url' 2>$null
    if (-not $pages) {
        gh api "repos/frashev/digest-site/pages" -X POST -f "source[branch]=main" -f "source[path]=/" --jq '.html_url' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Log "PAGES: enabled" } else { Log "PAGES: enable failed (ignored)" }
    } else {
        Log ("PAGES: " + $pages)
    }
} catch { Log "PAGES: ensure failed (ignored)" }

# 6. push (с fallback за първи път без upstream)
git push
if ($LASTEXITCODE -ne 0) {
    git push -u origin main
    if ($LASTEXITCODE -ne 0) { Log "PUSH-FAILED: will retry next run"; exit 0 }
}
Log "PUSH: ok"
exit 0
