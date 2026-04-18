@echo off
REM Pokescraper - Windows Batch Runner
REM Navigate to the pokescraper directory and run the CLI

cd /d "%~dp0"

echo.
echo ============================================================
echo   POKESCRAPER - TCGPlayer Card Scraper CLI
echo ============================================================
echo.

REM Check if .venv exists
if not exist ".venv" (
    echo [!] Virtual environment not found. Setting up...
    python -m venv .venv
    echo [+] Virtual environment created
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install/upgrade requirements if needed
echo [*] Checking dependencies...
pip install -q -r requirements.txt

REM Run the scraper
echo.
echo [*] Starting pokescraper CLI...
echo.
python src/main.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo [!] An error occurred. Press any key to exit...
    pause
)
