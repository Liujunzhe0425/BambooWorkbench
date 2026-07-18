@echo off
setlocal
if defined BAMBOO_PYTHON (
  set "PYTHON_EXE=%BAMBOO_PYTHON%"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo {"type":"error","message":"Python 3.12 was not found"} 1>&2
    exit /b 4
  )
  set "PYTHON_EXE=python"
)
"%PYTHON_EXE%" "%~dp0src\boiling_module.py" %*
exit /b %ERRORLEVEL%
