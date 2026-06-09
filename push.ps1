# Push dashboard changes to GitHub
# Usage: .\push.ps1 "your commit message"
#        .\push.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($args.Count -gt 0) {
    & $py (Join-Path $root "scripts\push.py") @args
} else {
    & $py (Join-Path $root "scripts\push.py")
}
