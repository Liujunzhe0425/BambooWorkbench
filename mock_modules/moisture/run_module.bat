@echo off
setlocal
if defined BAMBOO_MODULE_HOST (
  "%BAMBOO_MODULE_HOST%" --mock-module --module-id moisture %*
) else (
  python -m mock_modules.common.cli --module-id moisture %*
)
exit /b %ERRORLEVEL%
