@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%supercc_squad.py"

where python >nul 2>nul
if not errorlevel 1 (
  python "%SCRIPT_PATH%" %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if not errorlevel 1 (
  python3 "%SCRIPT_PATH%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%SCRIPT_PATH%" %*
  exit /b %ERRORLEVEL%
)

echo supercc-squad.cmd: python/python3/py is required to run supercc_squad.py 1>&2
exit /b 127
