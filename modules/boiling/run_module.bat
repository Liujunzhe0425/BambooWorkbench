@echo off
setlocal
set "PORTABLE_RUNTIME=%~dp0runtime\boiling_module.exe"
if exist "%PORTABLE_RUNTIME%" goto run_portable
if defined BAMBOO_PYTHON goto run_configured_python

where python >nul 2>nul
if errorlevel 1 goto missing_runtime
set "PYTHON_EXE=python"
goto run_python

:run_configured_python
set "PYTHON_EXE=%BAMBOO_PYTHON%"

:run_python
"%PYTHON_EXE%" "%~dp0src\boiling_module.py" %*
exit /b %ERRORLEVEL%

:run_portable
"%PORTABLE_RUNTIME%" %*
exit /b %ERRORLEVEL%

:missing_runtime
echo {"type":"error","message":"Python 3.12 was not found"} 1>&2
exit /b 4
