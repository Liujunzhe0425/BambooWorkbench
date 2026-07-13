@echo off
setlocal
python -m mock_modules.common.cli --module-id moisture %*
exit /b %ERRORLEVEL%
