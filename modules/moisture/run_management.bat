@echo off
setlocal
call "%~dp0run_module.bat" %*
exit /b %ERRORLEVEL%
