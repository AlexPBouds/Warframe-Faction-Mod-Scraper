$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
    if (-not (Test-Path -LiteralPath $python)) {
        python -m venv .venv
    }
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Could not create .venv. Install Python 3.10 or newer."
    }
}

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

& $python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "Warframe-Faction-Mod-Scraper" `
    --collect-all customtkinter `
    --collect-data matplotlib `
    app.py
if ($LASTEXITCODE -ne 0) {
    throw "Build failed."
}

Write-Host "Built dist\Warframe-Faction-Mod-Scraper.exe"
