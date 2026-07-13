@echo off
setlocal
if defined BAMBOO_MODULE_HOST (
  "%BAMBOO_MODULE_HOST%" --mock-module --module-id boiling %*
) else (
  python -m mock_modules.common.cli --module-id boiling %*
)
exit /b %ERRORLEVEL%
