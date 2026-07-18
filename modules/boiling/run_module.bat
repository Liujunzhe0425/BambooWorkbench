@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 (
  echo {"type":"error","message":"Python 3.12 was not found"} 1>&2
  exit /b 4
)
python "%~dp0src\boiling_module.py" %*
exit /b %ERRORLEVEL%
