@echo off
setlocal
if defined BAMBOO_MODULE_HOST (
  "%BAMBOO_MODULE_HOST%" --mock-module --module-id after_sales %*
) else (
  python -m mock_modules.common.cli --module-id after_sales %*
)
exit /b %ERRORLEVEL%
