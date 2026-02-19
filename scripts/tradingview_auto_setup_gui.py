#!/usr/bin/env python3
"""
TradingView Auto Alert Setup GUI
- UI 기반 프로그램
- 와치리스트 자동 인식
- 클릭만으로 모든 종목에 알림 설정
"""

import sys
import json
from pathlib import Path
from typing import List, Optional
import threading
import time

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QLineEdit, QComboBox,
        QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
        QCheckBox, QSpinBox, QTabWidget, QFrame
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
    from PyQt5.QtGui import QFont, QColor, QIcon
    from PyQt5.QtCore import Qt
except ImportError:
    print("❌ PyQt5가 설치되지 않았습니다.")
    print("설치: pip install PyQt5")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
import structlog

logger = structlog.get_logger()


class AlertGenerator:
    """TradingView 알림 생성 엔진"""

    def __init__(self):
        self.webhook_secret = settings.webhook_secret
        self.webhook_url = "http://localhost:8000/webhook"
        self.alerts = []

    def generate_alert(self, ticker: str, action: str) -> dict:
        """알림 생성"""
        return {
            "secret": self.webhook_secret,
            "action": action.upper(),
            "ticker": ticker.upper(),
            "price": "{{close}}",
            "time": "{{timenow}}"
        }

    def generate_for_ticker(self, ticker: str) -> tuple[dict, dict]:
        """BUY/SELL 쌍 생성"""
        buy = self.generate_alert(ticker, "BUY")
        sell = self.generate_alert(ticker, "SELL")
        return buy, sell

    def generate_batch(self, tickers: List[str]) -> List[dict]:
        """일괄 생성"""
        alerts = []
        for ticker in tickers:
            buy, sell = self.generate_for_ticker(ticker)
            alerts.extend([buy, sell])
        self.alerts = alerts
        return alerts


class WorkerThread(QThread):
    """백그라운드 작업 스레드"""
    progress = pyqtSignal(str)  # 진행 상황 메시지
    finished = pyqtSignal(bool)  # 완료 신호

    def __init__(self, tickers: List[str]):
        super().__init__()
        self.tickers = tickers
        self.generator = AlertGenerator()

    def run(self):
        """백그라운드에서 실행"""
        try:
            self.progress.emit(f"🔄 {len(self.tickers)}개 종목에 대해 알림 생성 중...")
            time.sleep(1)

            alerts = self.generator.generate_batch(self.tickers)

            self.progress.emit(f"✅ {len(alerts)}개 알림 생성 완료!")
            self.progress.emit("📋 아래 JSON을 TradingView에 하나씩 복붙하세요.")

            # 생성된 알림 저장
            output_file = Path(__file__).parent.parent / "tradingview_alerts_batch.json"
            with open(output_file, "w") as f:
                json.dump(alerts, f, indent=2, ensure_ascii=False)

            self.progress.emit(f"💾 파일 저장: {output_file}")
            self.finished.emit(True)

        except Exception as e:
            self.progress.emit(f"❌ 오류: {str(e)}")
            self.finished.emit(False)


class TradingViewAutoSetupGUI(QMainWindow):
    """TradingView 알림 자동 설정 GUI"""

    def __init__(self):
        super().__init__()
        self.generator = AlertGenerator()
        self.selected_tickers: List[str] = []
        self.worker_thread: Optional[WorkerThread] = None

        self.initUI()

    def initUI(self):
        """UI 초기화"""
        self.setWindowTitle("🤖 TradingView Alert Auto Setup")
        self.setGeometry(100, 100, 1200, 800)

        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 탭 위젯
        tabs = QTabWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.addWidget(tabs)

        # Tab 1: 와치리스트
        tabs.addTab(self.create_watchlist_tab(), "📊 와치리스트")

        # Tab 2: 수동 추가
        tabs.addTab(self.create_manual_tab(), "✏️ 수동 추가")

        # Tab 3: 결과
        tabs.addTab(self.create_result_tab(), "📋 결과")

        # Tab 4: 설정
        tabs.addTab(self.create_settings_tab(), "⚙️ 설정")

    def create_watchlist_tab(self) -> QWidget:
        """와치리스트 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 제목
        title = QLabel("📊 TradingView 와치리스트 자동 인식")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # 설명
        desc = QLabel(
            "TradingView의 와치리스트에 있는 모든 종목을 자동으로 인식하고\n"
            "BUY/SELL 알림을 생성합니다."
        )
        layout.addWidget(desc)

        # 와치리스트 입력
        layout.addWidget(QLabel("📌 종목 입력 (쉼표로 구분):"))
        self.watchlist_input = QTextEdit()
        self.watchlist_input.setPlaceholderText(
            "예: BTCUSDT, ETHUSDT, AAPL, MSFT\n"
            "또는 한 줄에 하나씩"
        )
        self.watchlist_input.setMaximumHeight(150)
        layout.addWidget(self.watchlist_input)

        # 종목 목록
        layout.addWidget(QLabel("🔍 인식된 종목:"))
        self.ticker_list = QListWidget()
        layout.addWidget(self.ticker_list)

        # 버튼들
        button_layout = QHBoxLayout()

        btn_parse = QPushButton("📖 종목 분석")
        btn_parse.clicked.connect(self.parse_watchlist)
        button_layout.addWidget(btn_parse)

        btn_select_all = QPushButton("✓ 모두 선택")
        btn_select_all.clicked.connect(self.select_all_tickers)
        button_layout.addWidget(btn_select_all)

        btn_deselect = QPushButton("✗ 모두 해제")
        btn_deselect.clicked.connect(self.deselect_all_tickers)
        button_layout.addWidget(btn_deselect)

        btn_generate = QPushButton("🚀 알림 생성")
        btn_generate.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        btn_generate.clicked.connect(self.generate_alerts)
        button_layout.addWidget(btn_generate)

        layout.addLayout(button_layout)

        # 진행 상황
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch()
        return widget

    def create_manual_tab(self) -> QWidget:
        """수동 추가 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 제목
        title = QLabel("✏️ 수동으로 종목 추가")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # 종목 입력
        layout.addWidget(QLabel("종목 심볼:"))
        self.manual_ticker = QLineEdit()
        self.manual_ticker.setPlaceholderText("예: BTCUSDT, AAPL, MSFT")
        layout.addWidget(self.manual_ticker)

        # 동작 선택
        layout.addWidget(QLabel("동작:"))
        self.action_combo = QComboBox()
        self.action_combo.addItems(["BUY", "SELL", "BUY & SELL"])
        layout.addWidget(self.action_combo)

        # 미리보기
        layout.addWidget(QLabel("📋 JSON 미리보기:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(200)
        layout.addWidget(self.preview_text)

        # 버튼
        btn_preview = QPushButton("👁️ 미리보기")
        btn_preview.clicked.connect(self.show_preview)
        layout.addWidget(btn_preview)

        btn_copy = QPushButton("📋 클립보드에 복사")
        btn_copy.clicked.connect(self.copy_to_clipboard)
        layout.addWidget(btn_copy)

        layout.addStretch()
        return widget

    def create_result_tab(self) -> QWidget:
        """결과 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 제목
        title = QLabel("📋 생성된 알림")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # 결과 텍스트
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)

        # 버튼
        btn_copy_all = QPushButton("📋 모두 복사")
        btn_copy_all.clicked.connect(self.copy_all_results)
        layout.addWidget(btn_copy_all)

        btn_save = QPushButton("💾 파일로 저장")
        btn_save.clicked.connect(self.save_results)
        layout.addWidget(btn_save)

        return widget

    def create_settings_tab(self) -> QWidget:
        """설정 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 제목
        title = QLabel("⚙️ 설정")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # Webhook Secret
        layout.addWidget(QLabel("🔐 Webhook Secret:"))
        self.secret_input = QLineEdit()
        self.secret_input.setText(settings.webhook_secret)
        layout.addWidget(self.secret_input)

        # Webhook URL
        layout.addWidget(QLabel("🔗 Webhook URL:"))
        self.url_input = QLineEdit()
        self.url_input.setText("http://localhost:8000/webhook")
        layout.addWidget(self.url_input)

        # 정보
        info = QLabel(
            "💡 주의:\n"
            "- Webhook Secret은 .env 파일의 WEBHOOK_SECRET과 일치해야 합니다\n"
            "- Webhook URL은 당신의 봇 주소입니다\n"
            "- 리모트 배포 시 https://your-domain.com/webhook 형식"
        )
        layout.addWidget(info)

        # 검증 버튼
        btn_validate = QPushButton("🔍 설정 검증")
        btn_validate.clicked.connect(self.validate_settings)
        layout.addWidget(btn_validate)

        layout.addStretch()
        return widget

    def parse_watchlist(self):
        """와치리스트 파싱"""
        text = self.watchlist_input.toPlainText()

        if not text.strip():
            QMessageBox.warning(self, "경고", "종목을 입력해주세요!")
            return

        # 종목 파싱
        tickers = [t.strip().upper() for t in text.replace("\n", ",").split(",") if t.strip()]
        tickers = list(set(tickers))  # 중복 제거

        self.selected_tickers = tickers

        # UI 업데이트
        self.ticker_list.clear()
        for ticker in tickers:
            item = QListWidget.item(self.ticker_list, self.ticker_list.count())
            self.ticker_list.addItem(ticker)

        QMessageBox.information(self, "완료", f"✅ {len(tickers)}개 종목 인식됨")

    def select_all_tickers(self):
        """모두 선택"""
        for i in range(self.ticker_list.count()):
            self.ticker_list.item(i).setSelected(True)

    def deselect_all_tickers(self):
        """모두 해제"""
        for i in range(self.ticker_list.count()):
            self.ticker_list.item(i).setSelected(False)

    def generate_alerts(self):
        """알림 생성"""
        if not self.selected_tickers:
            QMessageBox.warning(self, "경고", "종목을 선택해주세요!")
            return

        # 워커 스레드 생성
        self.worker_thread = WorkerThread(self.selected_tickers)
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.finished.connect(self.on_generation_finished)
        self.worker_thread.start()

        self.progress_bar.setVisible(True)

    def update_progress(self, message: str):
        """진행 상황 업데이트"""
        self.result_text.append(message)

    def on_generation_finished(self, success: bool):
        """생성 완료"""
        if success:
            QMessageBox.information(
                self,
                "완료",
                "✅ 알림 생성 완료!\n\n"
                "'결과' 탭에서 JSON을 확인하세요.\n"
                "각 JSON을 TradingView에 복붙해주세요."
            )

            # 결과 탭으로 이동
            # self.tabs.setCurrentIndex(2)  # Tab 2 = 결과
        else:
            QMessageBox.critical(self, "오류", "❌ 알림 생성 중 오류 발생!")

        self.progress_bar.setVisible(False)

    def show_preview(self):
        """미리보기"""
        ticker = self.manual_ticker.text().strip().upper()
        action = self.action_combo.currentText()

        if not ticker:
            QMessageBox.warning(self, "경고", "종목을 입력해주세요!")
            return

        self.preview_text.clear()

        if action == "BUY & SELL":
            buy_alert = self.generator.generate_alert(ticker, "BUY")
            sell_alert = self.generator.generate_alert(ticker, "SELL")

            self.preview_text.append("=" * 50)
            self.preview_text.append(f"BUY Alert for {ticker}")
            self.preview_text.append("=" * 50)
            self.preview_text.append(json.dumps(buy_alert, indent=2))

            self.preview_text.append("\n")
            self.preview_text.append("=" * 50)
            self.preview_text.append(f"SELL Alert for {ticker}")
            self.preview_text.append("=" * 50)
            self.preview_text.append(json.dumps(sell_alert, indent=2))
        else:
            alert = self.generator.generate_alert(ticker, action)
            self.preview_text.append(json.dumps(alert, indent=2))

    def copy_to_clipboard(self):
        """클립보드 복사"""
        import pyperclip

        text = self.preview_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "경고", "먼저 미리보기를 생성하세요!")
            return

        try:
            pyperclip.copy(text)
            QMessageBox.information(self, "완료", "✅ 클립보드에 복사되었습니다!")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"복사 실패: {str(e)}")

    def copy_all_results(self):
        """모든 결과 복사"""
        import pyperclip

        text = self.result_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "경고", "먼저 알림을 생성하세요!")
            return

        try:
            pyperclip.copy(text)
            QMessageBox.information(self, "완료", "✅ 클립보드에 복사되었습니다!")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"복사 실패: {str(e)}")

    def save_results(self):
        """결과 파일 저장"""
        text = self.result_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "경고", "먼저 알림을 생성하세요!")
            return

        output_file = Path(__file__).parent.parent / "tradingview_alerts_result.json"
        try:
            with open(output_file, "w") as f:
                f.write(text)
            QMessageBox.information(self, "완료", f"✅ 저장됨: {output_file}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패: {str(e)}")

    def validate_settings(self):
        """설정 검증"""
        secret = self.secret_input.text()
        url = self.url_input.text()

        if not secret:
            QMessageBox.warning(self, "경고", "Webhook Secret을 입력해주세요!")
            return

        if not url:
            QMessageBox.warning(self, "경고", "Webhook URL을 입력해주세요!")
            return

        # .env와 비교
        if secret == settings.webhook_secret:
            msg = f"✅ Webhook Secret이 .env와 일치합니다!\n\n"
        else:
            msg = f"⚠️ Webhook Secret이 .env와 다릅니다!\n"
            msg += f"   .env: {settings.webhook_secret}\n"
            msg += f"   입력: {secret}\n\n"

        msg += f"Webhook URL: {url}"

        QMessageBox.information(self, "설정 확인", msg)


def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    window = TradingViewAutoSetupGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
