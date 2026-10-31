@echo off
setlocal
cd /d "%~dp0"
call "F:\DeepSeekAI\anaconda3\condabin\conda.bat" activate "%~dp0.conda"
if errorlevel 1 goto fail
python -m pip install -r OnmyojiAutoScript\requirements.txt
if errorlevel 1 goto fail
python -m pip install wheel==0.41.3 setuptools==69.5.1
if errorlevel 1 goto fail
python -m pip check
if errorlevel 1 goto fail
pause
exit /b 0
:fail
pause
exit /b 1

