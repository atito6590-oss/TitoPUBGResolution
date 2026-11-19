@echo off
setlocal EnableDelayedExpansion
title Tito PUBG Resolution - Windows EXE Builder

echo ============================================================
echo   Tito PUBG Resolution - Standalone Windows EXE Builder
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ is not installed or not in PATH.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [2/4] Installing PySide6, Pillow, and PyInstaller...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/4] Generating multi-resolution PUBG Soldier Windows icon (.ico)...
python -m tito_pubg_resolution.icon_gen
if errorlevel 1 (
    echo [ERROR] Icon generation failed.
    pause
    exit /b 1
)

echo [4/4] Packaging standalone TitoPUBGResolution.exe...
pyinstaller --clean --noconfirm TitoPUBGResolution.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD SUCCESSFUL
echo   Output: dist\TitoPUBGResolution.exe
echo ============================================================
pause
