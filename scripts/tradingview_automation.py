#!/usr/bin/env python3
"""
TradingView Alert Automation - Browser Automation Version
Selenium을 사용한 TradingView 알림 완전 자동화

설치:
    pip install selenium

사용법:
    python scripts/tradingview_automation.py --mode interactive
    또는
    python scripts/tradingview_automation.py --mode batch --config alerts.json
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional, List
import argparse

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("❌ Selenium이 설치되지 않았습니다.")
    print("설치: pip install selenium")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
import structlog

logger = structlog.get_logger()


class TradingViewAutomation:
    """TradingView 알림 자동화 도구"""

    def __init__(self, headless: bool = False):
        """
        Args:
            headless: 브라우저 UI 표시 여부 (True = 백그라운드 실행)
        """
        self.webhook_secret = settings.webhook_secret
        self.webhook_url = "http://localhost:8000/webhook"
        self.driver = None
        self.headless = headless
        self._setup_driver()

    def _setup_driver(self):
        """Chrome 드라이버 설정"""
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument("--headless")

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Chrome 드라이버 로드됨")
        except Exception as e:
            logger.error(f"Chrome 드라이버 로드 실패: {e}")
            print("💡 Chrome WebDriver 다운로드: https://chromedriver.chromium.org/")
            sys.exit(1)

    def navigate_to_tradingview(self):
        """TradingView로 이동"""
        print("\n🌐 TradingView로 이동 중...")
        self.driver.get("https://www.tradingview.com/")
        time.sleep(3)
        print("✅ TradingView 로드됨")

    def navigate_to_chart(self, symbol: str, timeframe: str = "D"):
        """특정 차트로 이동

        Args:
            symbol: 심볼 (예: BTCUSDT)
            timeframe: 타임프레임 (M = 1분, H = 1시간, D = 일봉, W = 주봉)
        """
        print(f"\n📊 {symbol} {timeframe} 차트로 이동 중...")

        url = f"https://www.tradingview.com/chart/?symbol={symbol}&interval={timeframe}"
        self.driver.get(url)
        time.sleep(5)  # 차트 로드 시간

        print(f"✅ {symbol} 차트 로드됨")

    def create_alert_manual(self, symbol: str, action: str = "BUY"):
        """
        수동으로 알림 생성 (사용자가 조건 설정)

        Args:
            symbol: 심볼
            action: BUY 또는 SELL
        """
        print(f"\n⚠️  수동 설정 모드")
        print(f"   심볼: {symbol}")
        print(f"   동작: {action}")
        print("\n다음을 수동으로 설정하세요:")
        print("1. 차트에서 조건을 설정하고 '알림 추가' 클릭")
        print("2. 다음 메시지를 메시지 탭에 복붙:")

        message = {
            "secret": self.webhook_secret,
            "action": action,
            "ticker": symbol.upper(),
            "price": "{{close}}",
            "time": "{{timenow}}"
        }

        print(json.dumps(message, indent=2, ensure_ascii=False))

        print("\n3. 웹훅 URL을 알림 탭에 입력:")
        print(f"   {self.webhook_url}")

        print("\n4. ☑️  웹훅 URL 체크박스 확인")
        print("5. '생성' 버튼 클릭")

        input("\n엔터를 눌러 계속...")

    def close(self):
        """브라우저 종료"""
        if self.driver:
            self.driver.quit()
            logger.info("브라우저 종료됨")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def generate_alert_config(symbol: str, action: str) -> dict:
    """알림 설정 생성"""
    return {
        "symbol": symbol.upper(),
        "action": action,
        "message": {
            "secret": settings.webhook_secret,
            "action": action,
            "ticker": symbol.upper(),
            "price": "{{close}}",
            "time": "{{timenow}}"
        },
        "webhook_url": "http://localhost:8000/webhook",
    }


def print_setup_guide(alert: dict):
    """알림 설정 가이드 출력"""
    print("\n" + "=" * 70)
    print(f"📋 {alert['symbol']} {alert['action']} 알림 설정 가이드")
    print("=" * 70)

    print("\n📌 Step 1: TradingView 차트 열기")
    print(f"   링크: https://www.tradingview.com/chart/?symbol={alert['symbol']}")

    print("\n📌 Step 2: 조건 설정 후 '알림 추가' 클릭")

    print("\n📌 Step 3: 메시지 탭에 다음 JSON 복붙")
    print("-" * 70)
    print(json.dumps(alert["message"], indent=2, ensure_ascii=False))
    print("-" * 70)

    print("\n📌 Step 4: 알림 탭에서 웹훅 설정")
    print(f"   웹훅 URL: {alert['webhook_url']}")

    print("\n📌 Step 5: 체크박스")
    print("   ☑️  웹훅 URL (필수!)")
    print("   ☑️  이메일 알림 (선택)")
    print("   ☑️  토스트 알림 (선택)")

    print("\n📌 Step 6: '생성' 버튼 클릭")

    print("\n" + "=" * 70)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="TradingView 알림 자동화"
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "batch", "guide"],
        default="guide",
        help="실행 모드"
    )
    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        help="심볼 (예: BTCUSDT, AAPL)"
    )
    parser.add_argument(
        "--action",
        choices=["BUY", "SELL"],
        default="BUY",
        help="동작"
    )
    parser.add_argument(
        "--config",
        help="설정 JSON 파일 경로"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="브라우저 헤드리스 모드"
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("🚀 TradingView Alert Automation")
    print("=" * 70)

    if args.mode == "guide":
        # 설정 가이드 모드
        alert = generate_alert_config(args.symbol, args.action)
        print_setup_guide(alert)

        # 다른 심볼도 생성
        print("\n💡 다른 심볼도 생성하려면:")
        print(f"   python scripts/tradingview_automation.py --mode guide --symbol ETHUSDT")

        # 일괄 생성 예제
        print("\n📋 일괄 생성 예제:")
        print("   symbols = ['BTCUSDT', 'ETHUSDT', 'AAPL']")
        for symbol in ["BTCUSDT", "ETHUSDT", "AAPL"]:
            for action in ["BUY", "SELL"]:
                alert = generate_alert_config(symbol, action)
                print(f"   ✓ {symbol} {action}")

    elif args.mode == "interactive":
        # 대화형 모드
        print("\n🎯 대화형 모드\n")

        while True:
            symbol = input("심볼 입력 (예: BTCUSDT) [Q: 종료]: ").strip().upper()
            if symbol == "Q":
                break

            for action in ["BUY", "SELL"]:
                alert = generate_alert_config(symbol, action)
                print_setup_guide(alert)

                response = input("다음 심볼로? (Y/N): ").strip().upper()
                if response != "Y":
                    break

    elif args.mode == "batch":
        # 일괄 생성 모드
        if not args.config:
            print("❌ --config 파일을 지정해주세요")
            print("예: python scripts/tradingview_automation.py --mode batch --config symbols.json")
            sys.exit(1)

        try:
            with open(args.config, "r") as f:
                config = json.load(f)

            symbols = config.get("symbols", [])
            actions = config.get("actions", ["BUY", "SELL"])

            print(f"\n📋 {len(symbols)} 심볼에 대해 일괄 생성\n")

            alerts = []
            for symbol in symbols:
                for action in actions:
                    alert = generate_alert_config(symbol, action)
                    alerts.append(alert)
                    print(f"✓ {symbol} {action}")

            # 결과 저장
            output_file = Path("tradingview_alerts_generated.json")
            with open(output_file, "w") as f:
                json.dump(alerts, f, indent=2, ensure_ascii=False)

            print(f"\n✅ {len(alerts)}개 알림 설정 생성됨")
            print(f"   저장: {output_file}")

            # 각 알림의 설정 가이드 출력
            for alert in alerts[:3]:  # 첫 3개만 출력
                print_setup_guide(alert)

            if len(alerts) > 3:
                print(f"\n... 그 외 {len(alerts) - 3}개 ...")

        except FileNotFoundError:
            print(f"❌ 설정 파일을 찾을 수 없습니다: {args.config}")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"❌ 설정 파일 형식이 잘못되었습니다: {args.config}")
            sys.exit(1)


if __name__ == "__main__":
    main()
