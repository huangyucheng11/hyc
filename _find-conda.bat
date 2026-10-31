@echo off
rem =============================================================
rem  定位本机的 conda.bat，结果写入环境变量 OAS_CONDA_BAT
rem  优先级：conda-path.txt  >  PATH 中的 conda  >  常见安装目录
rem  由 start-oas.bat / install-deps.bat 调用，一般不需要手动运行
rem =============================================================
setlocal EnableExtensions
set "OAS_CONDA_BAT="

rem ---- 1) 项目根目录的 conda-path.txt（一行，写 conda.bat 的完整路径）----
if exist "%~dp0conda-path.txt" (
    set /p OAS_CONDA_BAT=<"%~dp0conda-path.txt"
    if defined OAS_CONDA_BAT set "OAS_CONDA_BAT=%OAS_CONDA_BAT:"=%"
    if defined OAS_CONDA_BAT if not exist "%OAS_CONDA_BAT%" set "OAS_CONDA_BAT="
)

rem ---- 2) PATH 里已有 conda ----
if not defined OAS_CONDA_BAT (
    for /f "delims=" %%i in ('where conda.bat 2^>nul') do (
        if not defined OAS_CONDA_BAT if exist "%%~i" set "OAS_CONDA_BAT=%%~i"
    )
)

rem ---- 3) 常见安装位置 ----
if not defined OAS_CONDA_BAT (
    for %%d in (
        "%USERPROFILE%\anaconda3"
        "%USERPROFILE%\miniconda3"
        "%LOCALAPPDATA%\anaconda3"
        "%LOCALAPPDATA%\miniconda3"
        "C:\ProgramData\Anaconda3"
        "C:\ProgramData\miniconda3"
        "C:\Anaconda3"
        "C:\miniconda3"
        "D:\anaconda3"
        "D:\miniconda3"
        "E:\anaconda3"
        "E:\miniconda3"
    ) do (
        if not defined OAS_CONDA_BAT if exist "%%~d\condabin\conda.bat" set "OAS_CONDA_BAT=%%~d\condabin\conda.bat"
    )
)

if not defined OAS_CONDA_BAT (
    echo.
    echo [错误] 没有找到 conda。
    echo.
    echo   请先安装 Miniconda 或 Anaconda：
    echo     https://docs.conda.io/en/latest/miniconda.html
    echo.
    echo   如果已经装了但装在非常规位置，请在项目根目录新建 conda-path.txt，
    echo   里面写一行 conda.bat 的完整路径，例如：
    echo     C:\ProgramData\miniconda3\condabin\conda.bat
    echo.
    exit /b 1
)

rem ---- 把变量带出 setlocal ----
endlocal & set "OAS_CONDA_BAT=%OAS_CONDA_BAT%"
exit /b 0
