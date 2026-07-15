@echo off
setlocal

if defined PYTHONPATH (
  set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%~dp0src"
)

if defined BAMBOO_MODULE_PYTHON goto host_python

"%SystemRoot%\System32\where.exe" py >nul 2>nul
if not errorlevel 1 goto py_launcher

"%SystemRoot%\System32\where.exe" python >nul 2>nul
if not errorlevel 1 goto python_launcher

>&2 echo Python 3.11 or newer is required to run the moisture module.
exit /b 4

:py_launcher
py -3 -m moisture.cli %*
exit /b %ERRORLEVEL%

:python_launcher
python -m moisture.cli %*
exit /b %ERRORLEVEL%

:host_python
if not exist "%BAMBOO_MODULE_PYTHON%" (
  >&2 echo BAMBOO_MODULE_PYTHON does not identify an available Python runtime.
  exit /b 4
)
"%BAMBOO_MODULE_PYTHON%" -m moisture.cli %*
exit /b %ERRORLEVEL%
