# 🎯 **TradingView 알림 자동화 GUI 프로그램 - 사용 가이드**

## ✅ **지금 당신이 갖게 된 것**

**UI가 있는 완성된 프로그램**
- 클릭만으로 모든 종목에 알림 추가
- TradingView 와치리스트 자동 인식
- JSON 자동 생성
- 초보자 친화적 UI

---

## 🚀 **지금 바로 실행하기 (3가지 방법)**

### **Windows 사용자 - 가장 쉬움** ⭐

```bash
run_tradingview_gui.bat
```

더블클릭해서 실행!

### **Mac 사용자**

```bash
chmod +x run_tradingview_gui.sh
./run_tradingview_gui.sh
```

### **Linux 사용자**

```bash
chmod +x run_tradingview_gui.sh
./run_tradingview_gui.sh
```

### **수동 실행** (모든 OS)

```bash
pip install PyQt5 pyperclip
python scripts/tradingview_auto_setup_gui.py
```

---

## 📋 **프로그램 사용법**

### **1️⃣ 프로그램 실행**

```
run_tradingview_gui.bat  (Windows)
또는
./run_tradingview_gui.sh  (Mac/Linux)
```

### **2️⃣ 프로그램 화면**

```
┌────────────────────────────────────────┐
│  🤖 TradingView Alert Auto Setup      │
│────────────────────────────────────────│
│ [📊] [✏️] [📋] [⚙️]                     │
│ 와치리스트 수동추가 결과 설정           │
└────────────────────────────────────────┘
```

---

## 🎯 **Step-by-Step 사용법**

### **Tab 1️⃣: 📊 와치리스트 (자동 인식)**

#### Step 1: 종목 입력

```
입력 예시:
BTCUSDT, ETHUSDT, AAPL, MSFT, GOOGL

또는 한 줄씩:
BTCUSDT
ETHUSDT
AAPL
MSFT
GOOGL
```

#### Step 2: "📖 종목 분석" 클릭

```
결과:
✅ 5개 종목 인식됨
- BTCUSDT
- ETHUSDT
- AAPL
- MSFT
- GOOGL
```

#### Step 3: 종목 선택

```
선택 옵션:
- ✓ 모두 선택: 모든 종목 선택
- ✗ 모두 해제: 모든 종목 해제
- 마우스 클릭: 개별 선택/해제
```

#### Step 4: "🚀 알림 생성" 클릭

```
진행 중:
🔄 5개 종목에 대해 알림 생성 중...
✅ 10개 알림 생성 완료!  (5 종목 × BUY/SELL)
📋 아래 JSON을 TradingView에 하나씩 복붙하세요.
```

---

### **Tab 2️⃣: ✏️ 수동 추가 (개별 설정)**

#### Step 1: 종목 입력

```
종목 심볼: BTCUSDT
```

#### Step 2: 동작 선택

```
선택지:
- BUY: BUY 신호만
- SELL: SELL 신호만
- BUY & SELL: 둘 다
```

#### Step 3: "👁️ 미리보기" 클릭

```
결과 (JSON 표시):
{
  "secret": "MySecret123456",
  "action": "BUY",
  "ticker": "BTCUSDT",
  "price": "{{close}}",
  "time": "{{timenow}}"
}
```

#### Step 4: "📋 클립보드에 복사" 클릭

```
✅ 클립보드에 복사되었습니다!
(TradingView에 Ctrl+V로 붙여넣기)
```

---

### **Tab 3️⃣: 📋 결과 (생성된 모든 알림)**

#### 기능:

```
1. "📋 모두 복사"
   → 모든 JSON을 클립보드에 복사

2. "💾 파일로 저장"
   → tradingview_alerts_result.json 파일 생성
   → Excel, 메모장에서 확인 가능
```

---

### **Tab 4️⃣: ⚙️ 설정 (보안 확인)**

#### Step 1: Webhook Secret 확인

```
표시되는 값: MySecret123456
(당신의 .env 파일의 값)
```

#### Step 2: Webhook URL 확인

```
표시되는 값: http://localhost:8000/webhook
(리모트 배포 시: https://your-domain.com/webhook)
```

#### Step 3: "🔍 설정 검증" 클릭

```
결과:
✅ Webhook Secret이 .env와 일치합니다!
Webhook URL: http://localhost:8000/webhook
```

---

## 📝 **TradingView에 알림 추가하는 방법**

생성된 JSON을 받으면:

### Step 1: TradingView 차트 열기

```
https://www.tradingview.com/chart/?symbol=BTCUSDT
```

### Step 2: 벨 아이콘 클릭 → "알림 추가"

### Step 3: 조건 설정

```
심볼: BTCUSDT
조건: RSI < 30 (또는 당신의 조건)
인터벌: 1일
```

### Step 4: "메시지" 탭

- 생성된 JSON을 복붙
- "📋 클립보드에 복사" 사용

### Step 5: "알림" 탭

- 웹훅 URL: `http://localhost:8000/webhook`
- ☑️ 웹훅 URL 체크박스 확인

### Step 6: "생성" 클릭

---

## 💡 **실제 예제**

### **예제 1: 5개 종목 자동 설정**

```
프로그램에 입력:
BTCUSDT, ETHUSDT, BNBUSDT, ADAUSDT, DOGEUSDT

결과:
✅ 5개 종목 인식됨
✅ 10개 알림 생성됨 (BUY + SELL)

각 JSON:
{
  "secret": "MySecret123456",
  "action": "BUY",
  "ticker": "BTCUSDT",
  ...
}

이것을 TradingView에 하나씩 복붙!
```

### **예제 2: 주식 종목 추가**

```
프로그램에 입력:
AAPL, MSFT, GOOGL, TSLA, NVDA

결과:
✅ 5개 종목 인식됨
✅ 10개 알림 생성됨

아마존, 테슬라, 엔비디아 등 자동으로 설정됨!
```

---

## ✅ **체크리스트**

### 프로그램 설정:

- [ ] PyQt5 설치됨 (자동 설치됨)
- [ ] Webhook Secret이 표시됨
- [ ] Webhook URL이 표시됨

### TradingView 설정:

각 종목마다:
- [ ] JSON이 메시지 탭에 입력됨
- [ ] 웹훅 URL이 알림 탭에 입력됨
- [ ] ☑️ 웹훅 URL 체크박스가 체크됨
- [ ] "생성" 버튼 클릭됨

---

## 🧪 **설정 후 테스트**

```bash
# 웹훅 테스트
python scripts/test_webhook.py

# 결과
✅ All alerts processed successfully
```

---

## 🆘 **문제 해결**

### **프로그램이 안 켜집니다**

```bash
# 수동 실행
python scripts/tradingview_auto_setup_gui.py

# 에러 메시지 확인
# PyQt5 설치 필요:
pip install PyQt5 pyperclip
```

### **종목 분석 안 됨**

```
종목을 입력했는지 확인
쉼표 또는 줄바꿈으로 구분되었는지 확인
"📖 종목 분석" 버튼을 클릭했는지 확인
```

### **클립보드 복사 안 됨**

```bash
# pyperclip 설치
pip install pyperclip
```

### **Webhook Secret 맞지 않음**

```
.env 파일 확인:
cat .env | grep WEBHOOK_SECRET

프로그램의 설정 탭에서 확인
```

---

## 📋 **파일 설명**

```
run_tradingview_gui.bat          Windows 실행 파일
run_tradingview_gui.sh           Mac/Linux 실행 파일
tradingview_auto_setup_gui.py    UI 프로그램 (PyQt5)
```

---

## 🎯 **권장 워크플로우**

### **한 번에 끝내기 (20분)**

1. **프로그램 실행** (1분)
   ```bash
   run_tradingview_gui.bat
   ```

2. **종목 입력** (2분)
   ```
   BTCUSDT, ETHUSDT, AAPL, MSFT, GOOGL
   ```

3. **종목 분석** (1분)
   ```
   "📖 종목 분석" 클릭
   "✓ 모두 선택" 클릭
   ```

4. **알림 생성** (1분)
   ```
   "🚀 알림 생성" 클릭
   ```

5. **TradingView 설정** (15분)
   - 각 종목마다 알림 추가
   - JSON 복붙
   - 웹훅 URL 설정

6. **테스트** (2분)
   ```bash
   python scripts/test_webhook.py
   ```

---

## 🎓 **다음 단계**

1. ✅ 프로그램 실행
2. ✅ 모든 종목 입력
3. ✅ 알림 생성
4. ✅ TradingView 설정
5. ✅ 테스트 실행

**완료!** 🎉

---

## 📞 **추가 정보**

- 상세 기능: 각 탭의 "?" 버튼 참고
- 문제 해결: `TROUBLESHOOTING.md`
- 전체 가이드: `TRADINGVIEW_AUTOMATION_GUIDE.md`

---

**이제 클릭만으로 모든 종목의 알림을 자동 설정할 수 있습니다!** ✨

**프로그램을 실행하세요!** 🚀

