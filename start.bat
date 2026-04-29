@echo off
cd /d "%~dp0"
set APPDATA_CLIENT=%APPDATA%\VRChatOSCRemote\client.py
if exist "%APPDATA_CLIENT%" (
    start "" "%~dp0python\pythonw.exe" "%APPDATA_CLIENT%"
) else (
    start "" "%~dp0python\pythonw.exe" "%~dp0client.py"
)