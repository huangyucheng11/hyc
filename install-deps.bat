@echo off
rem =============================================================
rem  一次性环境安装：自动创建 .conda 环境并安装依赖
rem  换电脑 / 首次使用 时运行本文件
rem =============================================================
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

call "%~dp0_find-conda.bat"
if errorlevel 1 goto fail

echo.
echo === 使用的 conda: %OAS_CONDA_BAT%
echo.

if not exist "%~dp0.conda\python.exe" (
    echo [1/4] 创建 Python 3.10 环境到 .conda ...
    call "%OAS_CONDA_BAT%" create -p "%~dp0.conda" python=3.10 -y
    if errorlevel 1 goto fail
) else (
    echo [1/4] .conda 环境已存在，跳过创建
)

echo [2/4] 激活环境 ...
call "%OAS_CONDA_BAT%" activate "%~dp0.conda"
if errorlevel 1 goto fail

echo [3/4] 安装依赖（首次较慢，请耐心等待）...
python -m pip install --upgrade pip
python -m pip install -r OnmyojiAutoScript\requirements.txt
if errorlevel 1 goto fail
python -m pip install wheel==0.41.3 setuptools==69.5.1
if errorlevel 1 goto fail

echo [4/4] 校验依赖 ...
python -m pip check
if errorlevel 1 goto fail

echo.
echo ============================================
echo  安装完成。现在可以双击 launch-oas.bat 启动。
echo ============================================
pause
exit /b 0

:fail
echo.
echo ============================================
echo  安装失败，请把上面的报错信息完整记录下来。
echo ============================================
pause
exit /b 1
