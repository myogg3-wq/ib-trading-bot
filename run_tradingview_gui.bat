@echo off
REM TradingView Alert Setup GUI - Windows 배치 파일
REM Tkinter 기반 (Python 기본 라이브러리)

echo.
echo ============================================
echo 🤖 TradingView Alert Setup - Windows GUI
echo ============================================
echo.

REM Python 버전 확인
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python이 설치되지 않았습니다.
    pause
    exit /b 1
)

echo ✅ Python 확인됨
echo.

REM GUI 실행
echo 🚀 프로그램 시작 중...
python scripts/tradingview_gui_ultra_simple.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ 오류 발생!
    echo.
    pause
)
