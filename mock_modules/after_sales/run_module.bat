@echo off
setlocal
python -m mock_modules.common.cli --module-id after_sales %*
exit /b %ERRORLEVEL%
