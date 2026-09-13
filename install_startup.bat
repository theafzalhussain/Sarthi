@echo off
title Install JARVIS to Windows Startup
cd /d "%~dp0"

echo ======================================================================
echo   Installing J.A.R.V.I.S. into Windows Startup
echo ======================================================================
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_VBS=%TEMP%\CreateJarvisShortcut.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%SHORTCUT_VBS%"
echo sLinkFile = "%STARTUP_DIR%\JARVIS_Background.lnk" >> "%SHORTCUT_VBS%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%SHORTCUT_VBS%"
echo oLink.TargetPath = "wscript.exe" >> "%SHORTCUT_VBS%"
echo oLink.Arguments = """%~dp0jarvis_background.vbs""" >> "%SHORTCUT_VBS%"
echo oLink.WorkingDirectory = "%~dp0" >> "%SHORTCUT_VBS%"
echo oLink.Description = "JARVIS Hands-Free Voice Assistant" >> "%SHORTCUT_VBS%"
echo oLink.Save >> "%SHORTCUT_VBS%"

cscript /nologo "%SHORTCUT_VBS%"
del "%SHORTCUT_VBS%"

echo [SUCCESS] J.A.R.V.I.S. is now installed to Windows Startup!
echo Whenever your laptop turns on, JARVIS will automatically listen
echo for "Hey Jarvis" in the background without opening any windows!
echo.
pause

