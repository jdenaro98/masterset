# Pokescraper - PowerShell Runner
# Navigate to the pokescraper directory and run the CLI

param(
    [switch]$Reset = $false,
    [switch]$NoVenv = $false
)

# Get the script directory
$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  POKESCRAPER - TCGPlayer Card Scraper CLI" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Virtual environment setup
$venvPath = ".\.venv"

if ($Reset) {
    Write-Host "[*] Resetting virtual environment..." -ForegroundColor Yellow
    if (Test-Path $venvPath) {
        Remove-Item -Recurse -Force $venvPath
    }
}

if (-not $NoVenv) {
    if (-not (Test-Path $venvPath)) {
        Write-Host "[*] Creating virtual environment..." -ForegroundColor Yellow
        python -m venv $venvPath
        Write-Host "[+] Virtual environment created" -ForegroundColor Green
    }

    # Activate virtual environment
    & "$venvPath\Scripts\Activate.ps1"
    Write-Host "[+] Virtual environment activated" -ForegroundColor Green
}

# Install requirements
Write-Host "[*] Checking dependencies..." -ForegroundColor Yellow
pip install -q -r requirements.txt
Write-Host "[+] Dependencies ready" -ForegroundColor Green

# Run the scraper
Write-Host ""
Write-Host "[*] Starting pokescraper CLI..." -ForegroundColor Yellow
Write-Host ""

python src/main.py

# Exit code
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[!] An error occurred (exit code: $LASTEXITCODE)" -ForegroundColor Red
}
