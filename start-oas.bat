@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

rem ---- 定位 conda（自动适配不同电脑）----
call "%~dp0_find-conda.bat"
if errorlevel 1 goto noenv

if not exist "%~dp0.conda\python.exe" goto noenv

call "%OAS_CONDA_BAT%" activate "%~dp0.conda"
if errorlevel 1 goto fail

cd /d "%~dp0OnmyojiAutoScript"
python -m module.device.local_emulators
python server.py --host 127.0.0.1 --port 22267 %*
if errorlevel 1 goto fail
exit /b 0

:noenv
echo.
echo [错误] 运行环境还没准备好，无法启动。
echo.
echo   情况一：没有找到 conda
echo     请安装 Miniconda，或在项目根目录建 conda-path.txt 写一行 conda.bat 的完整路径。
echo.
echo   情况二：没有找到 .conda 环境
echo     请先双击运行一次 install-deps.bat，它会自动创建环境并安装依赖。
echo.
pause
exit /b 1

:fail
echo Startup failed. See the error above.
pause
exit /b 1
