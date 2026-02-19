#!/usr/bin/env python3
"""
TradingView Alert Automation Setup Tool
자동으로 TradingView 알림을 설정하는 도구입니다.

사용법:
1. TradingView 차트에서 수동으로 알림 규칙을 생성
2. 이 스크립트가 알림 메시지와 웹훅을 자동으로 생성해줍니다
3. 또는 완전 자동화를 위해 Selenium을 사용하여 브라우저 자동화
"""

import json
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
import structlog

logger = structlog.get_logger()


class TradingViewAlertGenerator:
    """TradingView 알림 설정 자동 생성기"""

    def __init__(self):
        self.webhook_secret = settings.webhook_secret
        self.webhook_url = "http://localhost:8000/webhook"
        self.alerts = []

    def generate_buy_alert(
        self,
        ticker: str,
        strategy_name: str = "Default",
        additional_info: str = ""
    ) -> dict:
        """
        BUY 신호 알림 생성

        Args:
            ticker: 코인/주식 심볼 (예: BTCUSDT, AAPL)
            strategy_name: 전략 이름 (선택)
            additional_info: 추가 정보 (선택)
        """
        message = {
            "secret": self.webhook_secret,
            "action": "BUY",
            "ticker": ticker.upper(),
            "price": "{{close}}",
            "time": "{{timenow}}",
        }

        if additional_info:
            message["info"] = additional_info

        alert = {
            "type": "BUY",
            "ticker": ticker.upper(),
            "strategy": strategy_name,
            "message": message,
            "webhook_url": self.webhook_url,
            "webhook_method": "POST",
            "description": f"BUY Alert for {ticker.upper()} - {strategy_name}",
        }

        self.alerts.append(alert)
        return alert

    def generate_sell_alert(
        self,
        ticker: str,
        strategy_name: str = "Default",
        additional_info: str = ""
    ) -> dict:
        """
        SELL 신호 알림 생성

        Args:
            ticker: 코인/주식 심볼 (예: BTCUSDT, AAPL)
            strategy_name: 전략 이름 (선택)
            additional_info: 추가 정보 (선택)
        """
        message = {
            "secret": self.webhook_secret,
            "action": "SELL",
            "ticker": ticker.upper(),
            "price": "{{close}}",
            "time": "{{timenow}}",
        }

        if additional_info:
            message["info"] = additional_info

        alert = {
            "type": "SELL",
            "ticker": ticker.upper(),
            "strategy": strategy_name,
            "message": message,
            "webhook_url": self.webhook_url,
            "webhook_method": "POST",
            "description": f"SELL Alert for {ticker.upper()} - {strategy_name}",
        }

        self.alerts.append(alert)
        return alert

    def generate_alerts_for_ticker(
        self,
        ticker: str,
        strategy_name: str = "Default"
    ) -> tuple[dict, dict]:
        """
        특정 심볼에 대한 BUY/SELL 알림 쌍 생성

        Args:
            ticker: 코인/주식 심볼
            strategy_name: 전략 이름

        Returns:
            (BUY 알림, SELL 알림) 튜플
        """
        buy_alert = self.generate_buy_alert(ticker, strategy_name)
        sell_alert = self.generate_sell_alert(ticker, strategy_name)
        return buy_alert, sell_alert

    def generate_alerts_batch(self, tickers: list[str], strategy_name: str = "Default"):
        """
        여러 심볼에 대해 일괄 알림 생성

        Args:
            tickers: 심볼 리스트 (예: ['BTCUSDT', 'ETHUSDT', 'AAPL'])
            strategy_name: 전략 이름
        """
        for ticker in tickers:
            self.generate_alerts_for_ticker(ticker, strategy_name)

    def export_to_file(self, filename: str = "tradingview_alerts.json"):
        """
        생성된 알림을 JSON 파일로 저장

        Args:
            filename: 저장할 파일 이름
        """
        output_path = Path(__file__).parent.parent / filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.alerts, f, indent=2, ensure_ascii=False)

        logger.info(f"Alerts exported to {output_path}")
        return output_path

    def print_setup_instructions(self):
        """TradingView에서 설정해야 할 내용 출력"""
        print("\n" + "=" * 70)
        print("📋 TradingView 알림 설정 가이드")
        print("=" * 70)

        for i, alert in enumerate(self.alerts, 1):
            print(f"\n{i}️⃣  {alert['description']}")
            print("-" * 70)

            print("\n📌 TradingView에서 설정할 항목:")
            print(f"   알림 이름: {alert['description']}")

            print("\n📝 메시지 (Message) - 이것을 정확히 복붙:")
            print(json.dumps(alert["message"], indent=2, ensure_ascii=False))

            print("\n🔗 웹훅 URL (Webhook URL):")
            print(f"   {alert['webhook_url']}")

            print("\n☑️  체크해야 할 항목:")
            print("   ✓ 웹훅 URL 체크박스")
            print("   ✓ 이메일 알림 (선택)")
            print("   ✓ 토스트 알림 (선택)")

            print()

    def print_json_for_clipboard(self):
        """클립보드에 복붙할 JSON 메시지 출력"""
        print("\n" + "=" * 70)
        print("📋 TradingView 메시지 (복붙용)")
        print("=" * 70)

        for alert in self.alerts:
            print(f"\n{alert['type']} Alert for {alert['ticker']}:")
            print("-" * 70)
            print(json.dumps(alert["message"], indent=2, ensure_ascii=False))
            print()

    def get_alert_message(self, index: int) -> str:
        """특정 알림의 메시지를 JSON 문자열로 반환"""
        if index < len(self.alerts):
            return json.dumps(self.alerts[index]["message"], ensure_ascii=False)
        return ""

    def validate_webhook(self) -> bool:
        """웹훅 연결 확인"""
        import requests

        try:
            response = requests.get(f"{self.webhook_url.rsplit('/', 1)[0]}/health", timeout=5)
            if response.status_code == 200:
                logger.info("✅ Webhook server is healthy")
                return True
            else:
                logger.error(f"❌ Webhook server returned {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Cannot connect to webhook at {self.webhook_url}")
            return False
        except Exception as e:
            logger.error(f"❌ Webhook validation failed: {e}")
            return False


def main():
    """메인 실행 함수"""
    print("\n" + "=" * 70)
    print("🚀 TradingView Alert Automation Setup")
    print("=" * 70)

    # 설정 확인
    print(f"\n🔐 Webhook Secret: {settings.webhook_secret[:10]}...")
    print(f"🔗 Webhook URL: http://localhost:8000/webhook")

    # 생성기 초기화
    generator = TradingViewAlertGenerator()

    # 웹훅 검증
    print("\n🔍 웹훅 서버 확인 중...")
    if not generator.validate_webhook():
        print("\n⚠️  경고: 웹훅 서버에 연결할 수 없습니다")
        print("   다음 명령어로 봇을 시작하세요:")
        print("   docker-compose up -d")
        print()

    # 예제 알림 생성
    print("\n📝 예제 알림 생성 중...\n")

    # 단일 심볼 알림
    print("1️⃣  단일 심볼 알림 생성")
    generator.generate_alerts_for_ticker("BTCUSDT", "RSI Strategy")
    print("   ✓ BTCUSDT BUY/SELL 알림 생성됨")

    # 다중 심볼 일괄 생성
    print("\n2️⃣  다중 심볼 일괄 생성")
    tickers = ["ETHUSDT", "AAPL", "MSFT"]
    generator.generate_alerts_batch(tickers, "Multi-Ticker Strategy")
    print(f"   ✓ {len(tickers)}개 심볼에 대한 BUY/SELL 알림 생성됨")

    # 총 알림 개수
    total_alerts = len(generator.alerts)
    print(f"\n✅ 총 {total_alerts}개 알림 생성됨 (BUY + SELL)\n")

    # 설정 가이드 출력
    generator.print_setup_instructions()

    # JSON 메시지 출력 (복붙용)
    generator.print_json_for_clipboard()

    # 파일로 저장
    print("\n" + "=" * 70)
    print("💾 파일 저장")
    print("=" * 70)
    output_path = generator.export_to_file()
    print(f"\n✅ 알림 설정이 저장되었습니다:")
    print(f"   {output_path}")

    # 다음 단계
    print("\n" + "=" * 70)
    print("🎯 다음 단계")
    print("=" * 70)
    print("""
1. TradingView 차트 열기
2. "알림 추가" 클릭
3. 기본 설정:
   - 심볼: BTCUSDT 등
   - 조건: 당신의 전략 조건
   - 인터벌: 1일 등

4. "메시지" 탭에서:
   - 위의 JSON 메시지 복붙

5. "알림" 탭에서:
   - 웹훅 URL: http://localhost:8000/webhook
   - ☑️  웹훅 URL 체크박스 반드시 체크

6. "생성" 버튼 클릭

7. 설정 완료 후 테스트:
   python scripts/test_webhook.py
    """)

    print("\n" + "=" * 70)
    print("✨ 완료!")
    print("=" * 70)


def interactive_mode():
    """대화형 모드 - 사용자 입력으로 알림 생성"""
    print("\n" + "=" * 70)
    print("🎯 대화형 TradingView 알림 설정")
    print("=" * 70)

    generator = TradingViewAlertGenerator()

    while True:
        print("\n옵션:")
        print("1. BUY 알림 생성")
        print("2. SELL 알림 생성")
        print("3. BUY/SELL 쌍 생성")
        print("4. 일괄 생성 (여러 심볼)")
        print("5. 설정 가이드 보기")
        print("6. JSON 메시지 보기")
        print("7. 파일로 저장")
        print("8. 종료")

        choice = input("\n선택 (1-8): ").strip()

        if choice == "1":
            ticker = input("심볼 입력 (예: BTCUSDT): ").strip().upper()
            strategy = input("전략명 (기본값: Default): ").strip() or "Default"
            generator.generate_buy_alert(ticker, strategy)
            print(f"✅ {ticker} BUY 알림 생성됨")

        elif choice == "2":
            ticker = input("심볼 입력 (예: BTCUSDT): ").strip().upper()
            strategy = input("전략명 (기본값: Default): ").strip() or "Default"
            generator.generate_sell_alert(ticker, strategy)
            print(f"✅ {ticker} SELL 알림 생성됨")

        elif choice == "3":
            ticker = input("심볼 입력 (예: BTCUSDT): ").strip().upper()
            strategy = input("전략명 (기본값: Default): ").strip() or "Default"
            generator.generate_alerts_for_ticker(ticker, strategy)
            print(f"✅ {ticker} BUY/SELL 알림 쌍 생성됨")

        elif choice == "4":
            tickers_input = input("심볼 입력 (쉼표로 구분: BTCUSDT,ETHUSDT,AAPL): ").strip()
            tickers = [t.strip().upper() for t in tickers_input.split(",")]
            strategy = input("전략명 (기본값: Default): ").strip() or "Default"
            generator.generate_alerts_batch(tickers, strategy)
            print(f"✅ {len(tickers)}개 심볼 일괄 생성됨")

        elif choice == "5":
            generator.print_setup_instructions()

        elif choice == "6":
            generator.print_json_for_clipboard()

        elif choice == "7":
            filename = input("파일명 (기본값: tradingview_alerts.json): ").strip()
            if not filename:
                filename = "tradingview_alerts.json"
            generator.export_to_file(filename)
            print(f"✅ 파일 저장됨: {filename}")

        elif choice == "8":
            print("\n👋 종료합니다!")
            break

        else:
            print("❌ 잘못된 선택입니다")


if __name__ == "__main__":
    # 인자 확인
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_mode()
    else:
        main()
