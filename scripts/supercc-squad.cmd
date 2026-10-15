@echo off
setlocal DisableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%supercc_squad.py"

where python >nul 2>nul
if not errorlevel 1 goto run_python

where python3 >nul 2>nul
if not errorlevel 1 goto run_python3

where py >nul 2>nul
if not errorlevel 1 goto run_py

echo supercc-squad.cmd: python/python3/py is required to run supercc_squad.py 1>&2
exit /b 127

:run_python
python "%SCRIPT_PATH%" %*
exit /b %ERRORLEVEL%

:run_python3
python3 "%SCRIPT_PATH%" %*
exit /b %ERRORLEVEL%

:run_py
py -3 "%SCRIPT_PATH%" %*
exit /b %ERRORLEVEL%
