@echo off
title Stop JARVIS Background Process
echo Stopping all running JARVIS background instances...

wmic process where "commandline like '%%jarvis.py%%'" call terminate >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1

echo.
echo [J.A.R.V.I.S. Systems Shut Down Successfully]
timeout /t 2 >nul

