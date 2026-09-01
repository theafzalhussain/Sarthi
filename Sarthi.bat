@echo off
REM ============================================================
REM  SAARTHI Launcher — double-click karo, bas.
REM  VS Code ki zaroorat nahi. Kahin se bhi chal jayega.
REM ============================================================

REM Is script ki apni location pe jao (jahan cli.py hai)
cd /d "%~dp0"

title SAARTHI - Personal AI Agent

REM Agar virtual env hai to use karo, warna global python
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cli.py %*
) else (
    python cli.py %*
)

REM Agar band ho jaye to window turant band na ho — error dikh jaye
echo.
echo ============================================================
echo  SAARTHI band ho gaya. Window band karne ke liye koi bhi key dabao.
echo ============================================================
pause >nul
