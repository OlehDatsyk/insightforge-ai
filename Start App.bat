@echo off
setlocal enabledelayedexpansion
title InsightForge AI - Startup
cd /d "%~dp0"

echo ===========================================================
echo   InsightForge AI - Starting Up (Was made by Oleh Datsyk)
echo ===========================================================
echo.

REM --- Sanity check: make sure the ZIP was actually extracted -------------------
if not exist "app.py" (
    echo [ERROR] app.py was not found in this folder.
    echo Make sure you fully extracted the ZIP file first, then run this
    echo script from inside the extracted folder ^(not from inside the .zip^).
    pause
    exit /b 1
)

REM --- Check Python is installed ---------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on your PATH.
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    echo and make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)

REM --- Create virtual environment if missing or broken -------------------------
REM (A venv copied from another folder/PC has hardcoded absolute paths baked
REM  into venv\Scripts\activate.bat and pyvenv.cfg, so it silently stops
REM  working once the project is moved or shared. We detect that and rebuild.)
set "NEED_VENV=0"
if not exist "venv\Scripts\python.exe" set "NEED_VENV=1"
if "!NEED_VENV!"=="0" (
    "venv\Scripts\python.exe" -c "1" >nul 2>nul
    if errorlevel 1 set "NEED_VENV=1"
)

if "!NEED_VENV!"=="1" (
    echo [1/5] Creating a fresh virtual environment for this computer...
    if exist "venv\" rmdir /s /q "venv"
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/5] Virtual environment already exists, skipping creation.
)

REM --- Activate virtual environment ---------------------------------------------
echo [2/5] Activating virtual environment...
call "venv\Scripts\activate.bat"

REM --- Install dependencies ------------------------------------------------------
echo [3/5] Installing dependencies from requirements.txt...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies. See the messages above.
    pause
    exit /b 1
)

REM --- Verify .env file exists ----------------------------------------------------
echo [4/5] Checking environment configuration...
if not exist ".env" (
    if exist ".env.example" (
        echo [WARNING] No .env file found. Creating one from .env.example...
        copy ".env.example" ".env" >nul
        echo.
        echo   ^>^>^> IMPORTANT: Open the new .env file and add at least ONE
        echo       AI provider key ^(OPENAI_API_KEY, ANTHROPIC_API_KEY, or
        echo       GEMINI_API_KEY^) before using the research features. ^<^<^<
        echo.
    ) else (
        echo [WARNING] No .env file found. Create one and add at least one
        echo AI provider API key ^(OpenAI, Anthropic, or Gemini^).
    )
)

REM --- Launch the server in its own window ---------------------------------------
echo [5/5] Launching InsightForge AI...
echo.
start "InsightForge AI Server" cmd /k "cd /d "%~dp0" && call venv\Scripts\activate.bat && uvicorn app:app --host 127.0.0.1 --port 8000 --reload"

REM --- Wait for the server to respond, then open it in Chrome --------------------
set "HEALTH_URL=http://localhost:8000/api/health"
set "URL=http://localhost:8000"
echo Waiting for the server to start...
set "UP=0"
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
    if !errorlevel! equ 0 (
        set "UP=1"
        goto :serverup
    )
    timeout /t 1 /nobreak >nul
)
:serverup

echo.
echo ============================================
if "!UP!"=="1" (
    echo   The app is running at: %URL%
) else (
    echo   Still starting... once ready, open: %URL%
)
echo ============================================
echo.

REM Try to open the link specifically in Google Chrome; fall back to the
REM system default browser if Chrome isn't installed.
set "CHROME_PATH="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_PATH if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_PATH if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if defined CHROME_PATH (
    start "" "%CHROME_PATH%" "%URL%"
) else (
    echo Google Chrome was not found, opening your default browser instead.
    start "" "%URL%"
)

echo A separate window titled "InsightForge AI Server" is now running the
echo server and showing its logs. Keep that window open while you use the
echo app, and press CTRL+C in it ^(or just close it^) when you're done.
echo.
pause
