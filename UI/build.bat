@echo off
REM ════════════════════════════════════════════════════════════
REM  西安汇丰-京博工业焊缝检测系统 v5 — PyInstaller 打包脚本
REM ════════════════════════════════════════════════════════════

echo [1/3] 激活 conda 环境...
call conda activate oldshen
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 无法激活 oldshen 环境，请确认 conda 环境存在
    exit /b 1
)

echo [2/3] 清理旧的构建文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] 开始打包...
cd /d C:\Users\11137\Desktop
pyinstaller UI\weld_inspection.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ════════════════════════════════════════════════
    echo  打包成功！
    echo  输出目录: dist\西安汇丰-京博工业焊缝检测系统 v5\
    echo ════════════════════════════════════════════════
) else (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
)

pause
