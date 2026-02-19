#!/usr/bin/env python3
"""
TradingView Alert Setup GUI - Ultra Simple Version
외부 의존성 전혀 없음 (Tkinter만 사용)
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json


class TradingViewGUI:
    """TradingView 알림 설정 GUI"""

    def __init__(self, root):
        self.root = root
        self.root.title("🤖 TradingView Alert Setup")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # 기본값
        self.webhook_secret = "MySecret123456"
        self.webhook_url = "http://localhost:8000/webhook"
        self.tickers = []
        self.alerts = []

        # 색상
        self.bg_color = "#f0f0f0"
        self.root.configure(bg=self.bg_color)

        # UI 생성
        self.create_ui()

    def create_ui(self):
        """UI 생성"""

        # 제목
        title_frame = tk.Frame(self.root, bg="#2196F3", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        title_label = tk.Label(
            title_frame,
            text="🤖 TradingView Alert Auto Setup",
            font=("Arial", 18, "bold"),
            fg="white",
            bg="#2196F3"
        )
        title_label.pack(pady=15)

        # 메인 프레임
        main_frame = ttk.Notebook(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: 와치리스트
        self.create_watchlist_tab(main_frame)

        # Tab 2: 수동 추가
        self.create_manual_tab(main_frame)

        # Tab 3: 결과
        self.create_result_tab(main_frame)

        # Tab 4: 설정
        self.create_settings_tab(main_frame)

    def create_watchlist_tab(self, notebook):
        """와치리스트 탭"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="📊 와치리스트")

        # 설명
        desc = tk.Label(
            frame,
            text="TradingView 와치리스트의 모든 종목을 입력하세요.",
            font=("Arial", 11),
            bg=self.bg_color
        )
        desc.pack(pady=10)

        # 입력 영역
        input_label = tk.Label(
            frame,
            text="종목 입력 (쉼표 또는 줄바꿈으로 구분):",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        )
        input_label.pack(anchor="w", padx=15, pady=5)

        self.watchlist_input = scrolledtext.ScrolledText(
            frame, height=8, width=80, font=("Arial", 10)
        )
        self.watchlist_input.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)
        self.watchlist_input.insert(tk.END, "예: BTCUSDT, ETHUSDT, AAPL, MSFT")

        # 종목 목록
        list_label = tk.Label(
            frame,
            text="🔍 인식된 종목:",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        )
        list_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.ticker_listbox = tk.Listbox(frame, height=6, font=("Arial", 10))
        self.ticker_listbox.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)

        # 버튼 프레임
        button_frame = tk.Frame(frame, bg=self.bg_color)
        button_frame.pack(padx=15, pady=10, fill=tk.X)

        btn_parse = tk.Button(
            button_frame,
            text="📖 종목 분석",
            font=("Arial", 10),
            bg="#2196F3",
            fg="white",
            padx=10,
            command=self.parse_watchlist
        )
        btn_parse.pack(side=tk.LEFT, padx=5)

        btn_select_all = tk.Button(
            button_frame,
            text="✓ 모두 선택",
            font=("Arial", 10),
            bg="#4CAF50",
            fg="white",
            padx=10,
            command=self.select_all
        )
        btn_select_all.pack(side=tk.LEFT, padx=5)

        btn_deselect = tk.Button(
            button_frame,
            text="✗ 모두 해제",
            font=("Arial", 10),
            bg="#f44336",
            fg="white",
            padx=10,
            command=self.deselect_all
        )
        btn_deselect.pack(side=tk.LEFT, padx=5)

        btn_generate = tk.Button(
            button_frame,
            text="🚀 알림 생성",
            font=("Arial", 11, "bold"),
            bg="#4CAF50",
            fg="white",
            padx=15,
            command=self.generate_alerts
        )
        btn_generate.pack(side=tk.RIGHT, padx=5)

    def create_manual_tab(self, notebook):
        """수동 추가 탭"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="✏️ 수동 추가")

        # 종목 입력
        tk.Label(
            frame,
            text="종목 심볼:",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        ).pack(anchor="w", padx=15, pady=10)

        self.manual_ticker = tk.Entry(frame, font=("Arial", 10), width=50)
        self.manual_ticker.pack(padx=15, pady=5, fill=tk.X)
        self.manual_ticker.insert(0, "BTCUSDT")

        # 동작 선택
        tk.Label(
            frame,
            text="동작 선택:",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        ).pack(anchor="w", padx=15, pady=(15, 5))

        self.action_var = tk.StringVar(value="BUY & SELL")

        for action in ["BUY", "SELL", "BUY & SELL"]:
            tk.Radiobutton(
                frame,
                text=action,
                variable=self.action_var,
                value=action,
                font=("Arial", 10),
                bg=self.bg_color
            ).pack(anchor="w", padx=30)

        # 미리보기
        tk.Label(
            frame,
            text="📋 JSON 미리보기:",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        ).pack(anchor="w", padx=15, pady=(15, 5))

        self.preview_text = scrolledtext.ScrolledText(
            frame,
            height=10,
            width=80,
            font=("Courier", 9)
        )
        self.preview_text.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)

        # 버튼
        button_frame = tk.Frame(frame, bg=self.bg_color)
        button_frame.pack(padx=15, pady=10, fill=tk.X)

        btn_preview = tk.Button(
            button_frame,
            text="👁️ 미리보기",
            font=("Arial", 10),
            bg="#2196F3",
            fg="white",
            command=self.show_preview
        )
        btn_preview.pack(side=tk.LEFT, padx=5)

        btn_copy = tk.Button(
            button_frame,
            text="📋 복사",
            font=("Arial", 10),
            bg="#4CAF50",
            fg="white",
            command=self.copy_preview
        )
        btn_copy.pack(side=tk.LEFT, padx=5)

    def create_result_tab(self, notebook):
        """결과 탭"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="📋 결과")

        # 결과 텍스트
        self.result_text = scrolledtext.ScrolledText(
            frame,
            height=25,
            width=100,
            font=("Courier", 9)
        )
        self.result_text.pack(padx=15, pady=15, fill=tk.BOTH, expand=True)

        # 버튼
        button_frame = tk.Frame(frame, bg=self.bg_color)
        button_frame.pack(padx=15, pady=10, fill=tk.X)

        btn_copy_all = tk.Button(
            button_frame,
            text="📋 모두 복사",
            font=("Arial", 10),
            bg="#2196F3",
            fg="white",
            command=self.copy_all
        )
        btn_copy_all.pack(side=tk.LEFT, padx=5)

        btn_save = tk.Button(
            button_frame,
            text="💾 파일 저장",
            font=("Arial", 10),
            bg="#FF9800",
            fg="white",
            command=self.save_file
        )
        btn_save.pack(side=tk.LEFT, padx=5)

    def create_settings_tab(self, notebook):
        """설정 탭"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="⚙️ 설정")

        # Webhook Secret
        tk.Label(
            frame,
            text="🔐 Webhook Secret:",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        ).pack(anchor="w", padx=15, pady=(15, 5))

        self.secret_input = tk.Entry(frame, font=("Arial", 10), width=50)
        self.secret_input.pack(padx=15, pady=5, fill=tk.X)
        self.secret_input.insert(0, self.webhook_secret)

        # Webhook URL
        tk.Label(
            frame,
            text="🔗 Webhook URL:",
            font=("Arial", 10, "bold"),
            bg=self.bg_color
        ).pack(anchor="w", padx=15, pady=(15, 5))

        self.url_input = tk.Entry(frame, font=("Arial", 10), width=50)
        self.url_input.pack(padx=15, pady=5, fill=tk.X)
        self.url_input.insert(0, self.webhook_url)

        # 정보
        info_text = """💡 주의:
- Webhook Secret은 .env 파일의 WEBHOOK_SECRET과 일치해야 합니다
- Webhook URL은 당신의 봇 주소입니다
- 리모트 배포 시 https://your-domain.com/webhook 형식"""

        info_label = tk.Label(
            frame,
            text=info_text,
            font=("Arial", 9),
            bg="#FFF3CD",
            justify=tk.LEFT
        )
        info_label.pack(padx=15, pady=15, fill=tk.X)

        # 검증 버튼
        btn_validate = tk.Button(
            frame,
            text="🔍 확인",
            font=("Arial", 10),
            bg="#2196F3",
            fg="white",
            command=self.validate_settings
        )
        btn_validate.pack(padx=15, pady=10)

    def parse_watchlist(self):
        """와치리스트 파싱"""
        text = self.watchlist_input.get("1.0", tk.END).strip()

        if not text or text == "예: BTCUSDT, ETHUSDT, AAPL, MSFT":
            messagebox.showwarning("경고", "종목을 입력해주세요!")
            return

        # 종목 파싱
        tickers = [t.strip().upper() for t in text.replace("\n", ",").split(",") if t.strip()]
        tickers = list(set(tickers))  # 중복 제거
        tickers.sort()

        self.tickers = tickers

        # 목록 업데이트
        self.ticker_listbox.delete(0, tk.END)
        for ticker in tickers:
            self.ticker_listbox.insert(tk.END, ticker)

        messagebox.showinfo("완료", f"✅ {len(tickers)}개 종목 인식됨")

    def select_all(self):
        """모두 선택"""
        self.ticker_listbox.selection_set(0, tk.END)

    def deselect_all(self):
        """모두 해제"""
        self.ticker_listbox.selection_clear(0, tk.END)

    def generate_alerts(self):
        """알림 생성"""
        selected_indices = self.ticker_listbox.curselection()

        if not selected_indices:
            messagebox.showwarning("경고", "종목을 선택해주세요!")
            return

        selected_tickers = [self.ticker_listbox.get(i) for i in selected_indices]

        # 웹훅 시크릿 업데이트
        self.webhook_secret = self.secret_input.get()
        self.webhook_url = self.url_input.get()

        # 알림 생성
        self.alerts = []
        result_text = "=" * 70 + "\n"
        result_text += f"📋 생성된 알림 ({len(selected_tickers) * 2}개)\n"
        result_text += "=" * 70 + "\n\n"

        for i, ticker in enumerate(selected_tickers, 1):
            # BUY 알림
            buy_alert = {
                "secret": self.webhook_secret,
                "action": "BUY",
                "ticker": ticker,
                "price": "{{close}}",
                "time": "{{timenow}}"
            }
            self.alerts.append(buy_alert)

            result_text += f"{i}️⃣  {ticker} - BUY\n"
            result_text += "-" * 70 + "\n"
            result_text += json.dumps(buy_alert, indent=2) + "\n\n"

            # SELL 알림
            sell_alert = {
                "secret": self.webhook_secret,
                "action": "SELL",
                "ticker": ticker,
                "price": "{{close}}",
                "time": "{{timenow}}"
            }
            self.alerts.append(sell_alert)

            result_text += f"{i}️⃣  {ticker} - SELL\n"
            result_text += "-" * 70 + "\n"
            result_text += json.dumps(sell_alert, indent=2) + "\n\n"

        # 결과 표시
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, result_text)

        messagebox.showinfo(
            "완료",
            f"✅ {len(selected_tickers) * 2}개 알림 생성 완료!\n\n"
            "'결과' 탭에서 JSON을 확인하세요.\n"
            "각 JSON을 TradingView에 복붙해주세요."
        )

    def show_preview(self):
        """미리보기"""
        ticker = self.manual_ticker.get().strip().upper()
        action = self.action_var.get()

        if not ticker:
            messagebox.showwarning("경고", "종목을 입력해주세요!")
            return

        self.preview_text.delete("1.0", tk.END)

        if action == "BUY & SELL":
            buy_alert = {
                "secret": self.secret_input.get(),
                "action": "BUY",
                "ticker": ticker,
                "price": "{{close}}",
                "time": "{{timenow}}"
            }
            sell_alert = {
                "secret": self.secret_input.get(),
                "action": "SELL",
                "ticker": ticker,
                "price": "{{close}}",
                "time": "{{timenow}}"
            }

            self.preview_text.insert(tk.END, "=" * 50 + "\n")
            self.preview_text.insert(tk.END, f"BUY Alert for {ticker}\n")
            self.preview_text.insert(tk.END, "=" * 50 + "\n")
            self.preview_text.insert(tk.END, json.dumps(buy_alert, indent=2) + "\n\n")

            self.preview_text.insert(tk.END, "=" * 50 + "\n")
            self.preview_text.insert(tk.END, f"SELL Alert for {ticker}\n")
            self.preview_text.insert(tk.END, "=" * 50 + "\n")
            self.preview_text.insert(tk.END, json.dumps(sell_alert, indent=2))
        else:
            alert = {
                "secret": self.secret_input.get(),
                "action": action,
                "ticker": ticker,
                "price": "{{close}}",
                "time": "{{timenow}}"
            }
            self.preview_text.insert(tk.END, json.dumps(alert, indent=2))

    def copy_preview(self):
        """미리보기 복사"""
        text = self.preview_text.get("1.0", tk.END)
        if not text.strip():
            messagebox.showwarning("경고", "먼저 미리보기를 생성하세요!")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("완료", "✅ 클립보드에 복사되었습니다!")

    def copy_all(self):
        """모든 결과 복사"""
        text = self.result_text.get("1.0", tk.END)
        if not text.strip():
            messagebox.showwarning("경고", "먼저 알림을 생성하세요!")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("완료", "✅ 클립보드에 복사되었습니다!")

    def save_file(self):
        """파일 저장"""
        if not self.alerts:
            messagebox.showwarning("경고", "먼저 알림을 생성하세요!")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="tradingview_alerts.json"
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.alerts, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("완료", f"✅ 저장됨:\n{file_path}")
        except Exception as e:
            messagebox.showerror("오류", f"저장 실패: {str(e)}")

    def validate_settings(self):
        """설정 검증"""
        secret = self.secret_input.get()
        url = self.url_input.get()

        if not secret:
            messagebox.showwarning("경고", "Webhook Secret을 입력해주세요!")
            return

        if not url:
            messagebox.showwarning("경고", "Webhook URL을 입력해주세요!")
            return

        msg = f"Webhook Secret: {secret}\n"
        msg += f"Webhook URL: {url}\n\n"
        msg += "✅ 설정이 준비되었습니다!"

        messagebox.showinfo("설정 확인", msg)


def main():
    """메인 함수"""
    root = tk.Tk()
    app = TradingViewGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
