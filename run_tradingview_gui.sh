#!/bin/bash

# TradingView Alert Setup GUI - Mac/Linux 실행 스크립트

echo ""
echo "============================================"
echo "🤖 TradingView Alert Auto Setup GUI"
echo "============================================"
echo ""

# 필수 라이브러리 확인
echo "필수 라이브러리 확인 중..."

python3 -m pip show PyQt5 > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ PyQt5가 설치되지 않았습니다."
    echo ""
    echo "설치 중..."
    pip install PyQt5 pyperclip

    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ 설치 실패"
        exit 1
    fi
fi

echo "✅ 라이브러리 확인 완료"
echo ""

# GUI 실행
echo "🚀 GUI 프로그램 시작 중..."
python3 scripts/tradingview_auto_setup_gui.py

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 오류 발생!"
    echo ""
fi
