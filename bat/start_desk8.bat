@echo off
chcp 65001 >nul
cd /d "%~dp0.."
setlocal EnableDelayedExpansion

REM ========================================
REM   龙虎监控系统 v5.1
REM ========================================
REM   桌台8 - 自动采集路单 + FLV推流
REM   端口: 9230
REM ========================================

set DESK_ID=8
set DEBUG_PORT=9230

echo ========================================
echo   龙虎监控系统 v5.1
echo   桌台: %DESK_ID%  端口: %DEBUG_PORT%
echo ========================================
echo.

echo [1/2] 清理临时文件...
set TEMP_DIR=temp\desk_%DESK_ID%
if exist "%TEMP_DIR%\logs\monitor\*" del /q "%TEMP_DIR%\logs\monitor\*" 2>nul
if exist "%TEMP_DIR%\screenshots\*.png" del /q "%TEMP_DIR%\screenshots\*.png" 2>nul
if exist "%TEMP_DIR%\screenshots\*.json" del /q "%TEMP_DIR%\screenshots\*.json" 2>nul

echo [2/2] 启动程序...
echo.

python main.py --desk %DESK_ID% --port %DEBUG_PORT%

pause
