@echo off
title JARVIS Background Daemon
cd /d "%~dp0"

echo ======================================================================
echo   Launching J.A.R.V.I.S. in Silent Background Mode
echo ======================================================================
echo.
echo JARVIS is now running completely in the background!
echo You can close all windows.
echo Just say "Hey Jarvis" or "Jarvis" aloud anytime to give commands!
echo.
echo To stop JARVIS, run: stop_jarvis.bat
echo.

wscript jarvis_background.vbs
timeout /t 3 >nul

