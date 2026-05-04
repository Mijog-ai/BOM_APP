@echo off
echo ============================================================
echo   BOM Explorer ^| PyInstaller Build Script
echo ============================================================
echo.

REM ── 1. Pin to the project .venv so pyodbc/PyQt6 are visible ──
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: .venv not found at "%PY%".
    echo Create it first:  py -m venv .venv  ^&^&  .venv\Scripts\activate  ^&^&  pip install -r requirements_app.txt
    pause
    exit /b 1
)

REM ── 2. Install app-only requirements into the .venv ──────────
echo [1/4] Installing app requirements (no ML packages)...
"%PY%" -m pip install -r requirements_app.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)
echo       Done.

REM ── 3. Install PyInstaller into the .venv ────────────────────
echo [2/4] Checking PyInstaller...
"%PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo       Installing PyInstaller...
    "%PY%" -m pip install pyinstaller --quiet
)
echo       Done.

REM ── 4. Clean previous build ──────────────────────────────────
echo [3/4] Cleaning previous build artefacts...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
echo       Done.

REM ── 5. Build ─────────────────────────────────────────────────
echo [4/4] Building EXE (this may take a few minutes)...
"%PY%" -m PyInstaller build.spec
if errorlevel 1 (
    echo.
    echo ERROR: Build failed. Check the output above for details.
    pause
    exit /b 1
)

REM ── 6. Result ────────────────────────────────────────────────
echo.
if exist "dist\BOM_Explorer.exe" (
    echo ============================================================
    echo   BUILD SUCCESSFUL
    echo.
    echo   EXE location:
    echo     dist\BOM_Explorer.exe
    echo.
    echo   Copy this single file to distribute to other PCs.
    echo.
    echo   REQUIREMENT on target machines:
    echo     Microsoft ODBC Driver for SQL Server must be installed.
    echo     ^(Same driver as on this machine — check ODBC Data Sources^)
    echo ============================================================
) else (
    echo ERROR: EXE not found after build. Something went wrong.
)

pause
