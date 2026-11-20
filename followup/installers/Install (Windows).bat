@echo off
REM ==================================================================
REM  Automated follow-up emails: Windows installer
REM  Double-click this file. It will:
REM    1. check that Python is installed (and try to install it if not)
REM    2. copy the program to %USERPROFILE%\FollowupEmails
REM    3. install the Python packages it needs
REM    4. start the setup wizard
REM  Running it again later is safe: it updates the program and keeps
REM  the business's jobs list, settings and Gmail connection.
REM ==================================================================
setlocal
title Follow-up emails setup
set "SRC=%~dp0"
set "DEST=%USERPROFILE%\FollowupEmails"
set "CHECK=import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"

echo Checking for Python...
set "PY="
py -3 -c "%CHECK%" >nul 2>nul && set "PY=py -3"
if defined PY goto have_python
python -c "%CHECK%" >nul 2>nul && set "PY=python"
if defined PY goto have_python

echo Python 3.10 or newer is needed. Installing it now (this can take a few minutes)...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
echo.
echo If Python installed successfully, CLOSE this window and double-click the installer again.
echo If it did not, install Python from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" during install), then run this installer again.
pause
exit /b 1

:have_python
echo Copying program files to %DEST% ...
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%SRC%." "%DEST%" /E /XD .venv logs /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto copy_failed

cd /d "%DEST%"
if exist ".venv\Scripts\python.exe" goto have_venv
echo Creating a private Python environment...
%PY% -m venv .venv
if errorlevel 1 goto venv_failed

:have_venv
echo Installing packages (first time takes a minute)...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pip_failed

".venv\Scripts\python.exe" setup_wizard.py
pause
exit /b 0

:copy_failed
echo Could not copy the program files to %DEST%.
pause
exit /b 1

:venv_failed
echo Could not create the Python environment.
pause
exit /b 1

:pip_failed
echo Installing packages failed. Check the internet connection and run the installer again.
pause
exit /b 1
