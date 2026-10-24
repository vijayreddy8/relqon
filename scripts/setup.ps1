$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv .venv
    } else {
        throw "Python 3.10+ was not found. Install Python and enable it in PATH, then rerun this script."
    }
}

$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }

& $venvPython -m pip install -e ".[test]"
if ($LASTEXITCODE -ne 0) { throw "Relqon installation failed. Review the pip error above." }

Write-Host ""
Write-Host "Relqon setup completed."
Write-Host "Run: .\.venv\Scripts\relqon.exe run ."
Write-Host "Help: .\.venv\Scripts\relqon.exe --help"
