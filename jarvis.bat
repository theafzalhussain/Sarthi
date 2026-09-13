@echo off
title J.A.R.V.I.S. - Advanced AI Assistant
cd /d "%~dp0"

echo ======================================================================
echo   Starting J.A.R.V.I.S. Core (Voice + Multimodal + Universal Web)
echo ======================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" jarvis.py %*
) else (
    python jarvis.py %*
)

if errorlevel 1 (
    echo.
    echo [JARVIS Exited with code %ERRORLEVEL%]
    pause
)
