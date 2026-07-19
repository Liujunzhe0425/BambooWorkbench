@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHON_RUNTIME_SENTINEL=BAMBOO_MOISTURE_RUNTIME_OK_42C91E7D"
set "PYTHON_RUNTIME_PROBE=import jsonschema, sys; sys.version_info >= (3, 11) or sys.exit(1); print('%PYTHON_RUNTIME_SENTINEL%')"

if defined PYTHONPATH (
  set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%~dp0src"
)

if defined BAMBOO_MODULE_EXECUTABLE goto packaged_executable
if exist "%~dp0runtime\BambooMoistureModule.exe" goto bundled_executable
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

:packaged_executable
if not exist "%BAMBOO_MODULE_EXECUTABLE%" goto packaged_executable_missing
"%BAMBOO_MODULE_EXECUTABLE%" %*
exit /b %ERRORLEVEL%

:packaged_executable_missing
>&2 echo BAMBOO_MODULE_EXECUTABLE does not identify the packaged moisture runtime.
exit /b 4

:bundled_executable
"%~dp0runtime\BambooMoistureModule.exe" %*
exit /b %ERRORLEVEL%

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
setlocal EnableDelayedExpansion
set "PYTHON_PROBE_RESULT="
set /a PYTHON_PROBE_LINES=0
for /f "usebackq delims=" %%P in (`call "%~1" -c "%PYTHON_RUNTIME_PROBE%" 2^>nul`) do (
  set /a PYTHON_PROBE_LINES+=1
  set "PYTHON_PROBE_RESULT=%%P"
)
if !PYTHON_PROBE_LINES! EQU 1 if "!PYTHON_PROBE_RESULT!"=="%PYTHON_RUNTIME_SENTINEL%" (
  endlocal
  exit /b 0
)
endlocal
exit /b 1
