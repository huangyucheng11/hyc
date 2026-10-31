@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
call "F:\DeepSeekAI\anaconda3\condabin\conda.bat" activate "%~dp0.conda"
if errorlevel 1 goto fail
cd /d "%~dp0OnmyojiAutoScript"
python -m module.device.local_emulators
python server.py --host 127.0.0.1 --port 22267 %*
if errorlevel 1 goto fail
exit /b 0
:fail
 echo Startup failed. See the error above.
pause
exit /b 1

