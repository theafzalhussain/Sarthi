@echo off
REM SAARTHI / J.A.R.V.I.S. Windows launcher
setlocal
cd /d "%~dp0"
title SAARTHI / J.A.R.V.I.S. - Personal AI Agent

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cli.py %*
) else (
    python cli.py %*
)

set "SAARTHI_EXIT=%ERRORLEVEL%"
if not "%SAARTHI_EXIT%"=="0" (
    echo.
    echo [ERROR] SAARTHI exit code: %SAARTHI_EXIT%
    echo Window band karne ke liye koi bhi key dabao.
    pause >nul
)
exit /b %SAARTHI_EXIT%
