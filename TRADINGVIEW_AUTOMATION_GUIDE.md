# 🤖 **TradingView 알림 자동화 가이드**

TradingView에서 알림을 쉽게 자동 설정하는 도구입니다.

---

## 🎯 **3가지 사용 방법**

### **방법 1: 가이드 모드** (가장 쉬움 - 추천)

TradingView에 설정할 내용을 자동으로 생성해줍니다.

#### 설치

```bash
pip install requests
```

#### 사용법

```bash
# 기본 (BTCUSDT BUY)
python scripts/tradingview_automation.py --mode guide

# 특정 심볼 (ETHUSDT SELL)
python scripts/tradingview_automation.py --mode guide --symbol ETHUSDT --action SELL

# 여러 심볼 한 번에 보기
python scripts/tradingview_automation.py --mode guide --symbol AAPL
python scripts/tradingview_automation.py --mode guide --symbol MSFT
```

#### 결과

```
========================================
📋 BTCUSDT BUY 알림 설정 가이드
========================================

📌 Step 1: TradingView 차트 열기
   링크: https://www.tradingview.com/chart/?symbol=BTCUSDT

📌 Step 2: 조건 설정 후 '알림 추가' 클릭

📌 Step 3: 메시지 탭에 다음 JSON 복붙
--------------------------------------
{
  "secret": "MySecret123456",
  "action": "BUY",
  "ticker": "BTCUSDT",
  "price": "{{close}}",
  "time": "{{timenow}}"
}
--------------------------------------

📌 Step 4: 알림 탭에서 웹훅 설정
   웹훅 URL: http://localhost:8000/webhook

📌 Step 5: 체크박스
   ☑️  웹훅 URL (필수!)
   ☑️  이메일 알림 (선택)
   ☑️  토스트 알림 (선택)

📌 Step 6: '생성' 버튼 클릭
```

---

### **방법 2: 대화형 모드** (자유로움)

사용자가 심볼과 동작을 입력하면서 알림을 생성합니다.

```bash
python scripts/setup_tradingview_alerts.py interactive
```

#### 메뉴

```
옵션:
1. BUY 알림 생성
2. SELL 알림 생성
3. BUY/SELL 쌍 생성
4. 일괄 생성 (여러 심볼)
5. 설정 가이드 보기
6. JSON 메시지 보기
7. 파일로 저장
8. 종료

선택 (1-8):
```

#### 예제

```
선택: 3
심볼 입력 (예: BTCUSDT): AAPL
전략명 (기본값: Default): Technical Analysis Strategy
✅ AAPL BUY/SELL 알림 쌍 생성됨

선택: 7
파일명 (기본값: tradingview_alerts.json): my_alerts.json
✅ 파일 저장됨: my_alerts.json
```

---

### **방법 3: 일괄 생성 모드** (자동화)

많은 심볼에 대해 일괄 생성합니다.

#### Step 1: 설정 파일 수정

`scripts/tradingview_alerts_config.json` 편집:

```json
{
  "symbols": [
    "BTCUSDT",
    "ETHUSDT",
    "AAPL",
    "MSFT",
    "GOOGL"
  ],
  "actions": ["BUY", "SELL"]
}
```

#### Step 2: 일괄 생성

```bash
python scripts/tradingview_automation.py --mode batch --config scripts/tradingview_alerts_config.json
```

#### 결과

```
✅ 10개 알림 설정 생성됨
   저장: tradingview_alerts_generated.json

📋 BTCUSDT BUY 알림 설정 가이드
...
(5개 심볼 × 2 동작 = 10개 알림)
```

생성된 파일을 열어서 각 알림의 JSON을 TradingView에 복붙하면 됩니다.

---

## 📋 **완전 자동화 (Browser Automation)**

Selenium을 사용하여 브라우저를 자동으로 조작합니다. (고급)

### 설치

```bash
pip install selenium

# ChromeDriver 다운로드
# https://chromedriver.chromium.org/
# 또는 다음 명령어 (Mac/Linux)
# brew install chromedriver
```

### 사용법

```bash
# 가이드 모드 (권장)
python scripts/tradingview_automation.py --mode guide --symbol BTCUSDT

# 대화형 모드
python scripts/tradingview_automation.py --mode interactive

# 일괄 모드
python scripts/tradingview_automation.py --mode batch --config scripts/tradingview_alerts_config.json

# 헤드리스 모드 (백그라운드)
python scripts/tradingview_automation.py --mode guide --headless
```

---

## 🔧 **TradingView 수동 설정** (한 번에 정리)

### Step 1: TradingView 차트 열기

```
https://www.tradingview.com/chart/?symbol=BTCUSDT
```

### Step 2: "알림 추가" 클릭

차트의 오른쪽 상단 벨 아이콘 → "알림 추가"

### Step 3: 기본 설정

| 항목 | 값 |
|------|-----|
| **심볼** | BTCUSDT |
| **조건** | 당신의 조건 |
| **인터벌** | 1일 (또는 선택) |

### Step 4: "메시지" 탭

아래 JSON을 복붙 (SECRET은 당신의 값으로):

```json
{
  "secret": "MySecret123456",
  "action": "BUY",
  "ticker": "BTCUSDT",
  "price": "{{close}}",
  "time": "{{timenow}}"
}
```

**또는 이 도구 사용:**

```bash
python scripts/tradingview_automation.py --mode guide --symbol BTCUSDT --action BUY
```

### Step 5: "알림" 탭

| 항목 | 값 |
|------|-----|
| **웹훅 URL** | http://localhost:8000/webhook |
| **☑️ 체크** | 웹훅 URL 반드시 체크! |

### Step 6: "생성" 버튼 클릭

완료!

---

## 🎯 **실제 사용 예제**

### 예제 1: 단일 심볼 BUY/SELL

```bash
python scripts/tradingview_automation.py --mode guide --symbol BTCUSDT --action BUY
python scripts/tradingview_automation.py --mode guide --symbol BTCUSDT --action SELL
```

각각 출력되는 JSON을 TradingView에 복붙

### 예제 2: 10개 심볼 자동 생성

```bash
python scripts/tradingview_automation.py --mode batch --config scripts/tradingview_alerts_config.json
```

생성 후 `tradingview_alerts_generated.json` 파일에서 각 알림의 JSON을 TradingView에 하나씩 입력

### 예제 3: 커스텀 설정

```bash
# 1. 설정 파일 생성
cat > my_symbols.json << 'EOF'
{
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "actions": ["BUY", "SELL"]
}
EOF

# 2. 일괄 생성
python scripts/tradingview_automation.py --mode batch --config my_symbols.json
```

---

## 📂 **생성된 파일**

### `setup_tradingview_alerts.py`

- 기본 JSON 생성 도구
- 대화형 모드 지원
- 파일 저장 가능

### `tradingview_automation.py`

- Browser automation 버전
- 세 가지 모드 지원 (guide, interactive, batch)
- JSON 설정 파일 지원

### `tradingview_alerts_config.json`

- 일괄 생성 설정 파일 예제
- 수정해서 사용 가능

---

## ✅ **체크리스트**

각 알림마다:

- [ ] JSON 메시지가 정확한가?
- [ ] secret이 .env와 일치하는가?
- [ ] 웹훅 URL이 `http://localhost:8000/webhook`인가?
- [ ] 웹훅 URL 체크박스가 체크되었는가?
- [ ] 최소 1개의 알림 방식(이메일/토스트/웹훅)이 선택되었는가?

---

## 🧪 **테스트**

설정 후:

```bash
# 웹훅 테스트
python scripts/test_webhook.py

# Telegram 확인
/queue    ← 대기 주문 보임
/status   ← 봇 상태 확인
```

---

## 🚀 **다음 단계**

1. ✅ 이 도구로 JSON 생성
2. ✅ TradingView 차트에서 조건 설정
3. ✅ "알림 추가" → 메시지 탭에 JSON 복붙
4. ✅ "알림" 탭 → 웹훅 URL 입력 + 체크
5. ✅ "생성" 클릭
6. ✅ 테스트: `python scripts/test_webhook.py`

**완료! 이제 자동 매매 시작!** 🎉

---

## 💡 **팁**

### 여러 타임프레임으로 설정하고 싶으면

각 타임프레임마다 다른 조건으로 알림을 만들면 됩니다:

```
BTCUSDT 1분봉 - RSI < 30 → BUY
BTCUSDT 1시간봉 - EMA 크로스 → BUY
BTCUSDT 일봉 - Support 이탈 → SELL
```

각각 다른 알림 규칙으로 설정하세요.

### 여러 전략을 동시에 모니터링

같은 심볼에 여러 조건으로 알림을 만들 수 있습니다:

```
BTCUSDT - Strategy A
BTCUSDT - Strategy B
BTCUSDT - Strategy C
```

모두 같은 웹훅 URL로 설정하면 됩니다.

### 복잡한 조건은 TradingView Pine Script에서 설정

이 도구는 JSON 생성만 하고, 실제 조건은 TradingView에서 설정합니다:

```pine
if close > ma50 and rsi < 30
    alertcondition(true, title="BUY Signal")
```

---

## 🆘 **문제 해결**

| 문제 | 해결 |
|------|------|
| "secret이 틀렸습니다" 에러 | .env의 WEBHOOK_SECRET 다시 확인 후 JSON에 입력 |
| 웹훅이 안 받아짐 | 웹훅 URL 체크박스 반드시 체크 |
| 주문이 실행 안 됨 | /status로 봇 상태 확인, Kill 상태인지 확인 |
| JSON 형식 에러 | 따옴표, 쉼표 등 정확히 맞는지 확인 |

---

## 📞 **지원**

더 도움이 필요하면:

1. `TROUBLESHOOTING.md` 참고
2. `scripts/test_webhook.py` 실행해서 웹훅 테스트
3. Telegram `/status` 확인

---

**이 도구를 사용하면 TradingView 알림 설정이 매우 간단해집니다!** ✨

