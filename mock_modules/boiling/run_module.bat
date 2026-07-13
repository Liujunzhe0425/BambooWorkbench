@echo off
setlocal
python -m mock_modules.common.cli --module-id boiling %*
exit /b %ERRORLEVEL%
