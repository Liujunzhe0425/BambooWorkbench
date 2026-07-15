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

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto module_venv
)

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
  "%~dp0..\..\.venv\Scripts\python.exe" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto repository_venv
)

"%SystemRoot%\System32\where.exe" python >nul 2>nul
if not errorlevel 1 (
  call python -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto path_python
)

"%SystemRoot%\System32\where.exe" py >nul 2>nul
if not errorlevel 1 (
  call py -3.12 -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto py_312
  call py -3 -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
  if not errorlevel 1 goto py_3
)

>&2 echo No available Python runtime provides Python 3.11 or newer and required dependency jsonschema.
exit /b 4

:explicit_python
if not exist "%BAMBOO_MODULE_PYTHON%" (
  >&2 echo BAMBOO_MODULE_PYTHON does not identify an available Python runtime.
  exit /b 4
)
call "%BAMBOO_MODULE_PYTHON%" -c "%PYTHON_RUNTIME_PROBE%" >nul 2>nul
if errorlevel 1 (
  >&2 echo BAMBOO_MODULE_PYTHON must provide Python 3.11 or newer and required dependency jsonschema.
  exit /b 4
)
"%BAMBOO_MODULE_PYTHON%" -m moisture.cli %*
exit /b %ERRORLEVEL%

:module_venv
"%~dp0.venv\Scripts\python.exe" -m moisture.cli %*
exit /b %ERRORLEVEL%

:repository_venv
"%~dp0..\..\.venv\Scripts\python.exe" -m moisture.cli %*
exit /b %ERRORLEVEL%

:path_python
python -m moisture.cli %*
exit /b %ERRORLEVEL%

:py_312
py -3.12 -m moisture.cli %*
exit /b %ERRORLEVEL%

:py_3
py -3 -m moisture.cli %*
exit /b %ERRORLEVEL%
