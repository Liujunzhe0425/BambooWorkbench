@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHON_RUNTIME_SENTINEL=BAMBOO_MOISTURE_RUNTIME_OK_42C91E7D"
set "PYTHON_RUNTIME_PROBE=import jsonschema, sys; assert (3, 11).__le__(sys.version_info[:2]); print('%PYTHON_RUNTIME_SENTINEL%')"

if defined PYTHONPATH (
  set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%~dp0src"
)

if defined BAMBOO_MODULE_PYTHON goto explicit_python
if defined VIRTUAL_ENV goto active_environment

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
  call :probe_python "%~dp0..\..\.venv\Scripts\python.exe"
  if not errorlevel 1 goto repository_venv
)

if exist "%~dp0.venv\Scripts\python.exe" (
  call :probe_python "%~dp0.venv\Scripts\python.exe"
  if not errorlevel 1 goto module_venv
)

>&2 echo No approved virtual environment provides Python 3.11 or newer and required dependency jsonschema.
exit /b 4

:explicit_python
if not exist "%BAMBOO_MODULE_PYTHON%" goto explicit_python_missing
call :probe_python "%BAMBOO_MODULE_PYTHON%"
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
call :probe_python "%VIRTUAL_ENV%\Scripts\python.exe"
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

:probe_python
set "PYTHON_PROBE_OUTPUT=%TEMP%\bamboo-moisture-probe-%RANDOM%-%RANDOM%.out"
set "PYTHON_PROBE_EXPECTED=%TEMP%\bamboo-moisture-probe-%RANDOM%-%RANDOM%.expected"
>"%PYTHON_PROBE_EXPECTED%" echo %PYTHON_RUNTIME_SENTINEL%
call "%~1" -c "%PYTHON_RUNTIME_PROBE%" >"%PYTHON_PROBE_OUTPUT%" 2>nul
if errorlevel 1 goto probe_python_failed
"%SystemRoot%\System32\fc.exe" /b "%PYTHON_PROBE_OUTPUT%" "%PYTHON_PROBE_EXPECTED%" >nul 2>nul
if errorlevel 1 goto probe_python_failed
del /q "%PYTHON_PROBE_OUTPUT%" "%PYTHON_PROBE_EXPECTED%" >nul 2>nul
exit /b 0

:probe_python_failed
del /q "%PYTHON_PROBE_OUTPUT%" "%PYTHON_PROBE_EXPECTED%" >nul 2>nul
exit /b 1
