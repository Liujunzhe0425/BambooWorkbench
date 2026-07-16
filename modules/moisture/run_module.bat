@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHON_RUNTIME_PROBE=import jsonschema, sys; raise SystemExit(sys.version_info < (3, 11))"

if defined PYTHONPATH (
  set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%~dp0src"
)

if defined BAMBOO_MODULE_PYTHON goto explicit_python
if defined VIRTUAL_ENV goto active_environment

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
  "%~dp0..\..\.venv\Scripts\python.exe" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto repository_venv
)

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto module_venv
)

>&2 echo No approved virtual environment provides Python 3.11 or newer and required dependency jsonschema.
exit /b 4

:explicit_python
if not exist "%BAMBOO_MODULE_PYTHON%" goto explicit_python_missing
call "%BAMBOO_MODULE_PYTHON%" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
if errorlevel 1 goto explicit_python_invalid
"%BAMBOO_MODULE_PYTHON%" -m moisture.cli %*
exit /b %ERRORLEVEL%

:explicit_python_missing
>&2 echo BAMBOO_MODULE_PYTHON does not identify an available Python runtime.
exit /b 4

:explicit_python_invalid
>&2 echo BAMBOO_MODULE_PYTHON must provide Python 3.11 or newer and required dependency jsonschema.
exit /b 4

:active_environment
if not exist "%VIRTUAL_ENV%\Scripts\python.exe" goto active_environment_missing
"%VIRTUAL_ENV%\Scripts\python.exe" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
if errorlevel 1 goto active_environment_invalid
"%VIRTUAL_ENV%\Scripts\python.exe" -m moisture.cli %*
exit /b %ERRORLEVEL%

:active_environment_missing
>&2 echo VIRTUAL_ENV does not identify an available Windows virtual environment.
exit /b 4

:active_environment_invalid
>&2 echo VIRTUAL_ENV must provide Python 3.11 or newer and required dependency jsonschema.
exit /b 4

:repository_venv
"%~dp0..\..\.venv\Scripts\python.exe" -m moisture.cli %*
exit /b %ERRORLEVEL%

:module_venv
"%~dp0.venv\Scripts\python.exe" -m moisture.cli %*
exit /b %ERRORLEVEL%
