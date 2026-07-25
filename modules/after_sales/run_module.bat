@echo off
setlocal
set "MODULE_DIR=%~dp0"
set "PYTHONUTF8=1"

if defined PYTHON_EXE (
  "%PYTHON_EXE%" "%MODULE_DIR%src\after_sales_agent\cli.py" %*
  exit /b %ERRORLEVEL%
)

if exist "%MODULE_DIR%runtime\after_sales_agent.exe" (
  "%MODULE_DIR%runtime\after_sales_agent.exe" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
  python "%MODULE_DIR%src\after_sales_agent\cli.py" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%MODULE_DIR%src\after_sales_agent\cli.py" %*
  exit /b %ERRORLEVEL%
)

echo {"type":"error","message":"未找到 Python，请安装 Python 3.10 或更高版本，或设置 PYTHON_EXE。"} 1>&2
exit /b 4
