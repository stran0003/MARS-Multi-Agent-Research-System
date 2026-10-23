@echo off
setlocal
rem Let Windows PowerShell use its own modules when launched from PowerShell 7.
set "PSModulePath="
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0deploy\windows-native\Mars.ps1" -Action Menu %*
set "mars_exit=%ERRORLEVEL%"
pause
exit /b %mars_exit%
