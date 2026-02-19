# ⚡ **TradingView 알림 설정 - 초간단 가이드 (2분)**

## 🎯 **지금 바로 하기**

### **Step 1: JSON 생성 (1분)**

```bash
python scripts/tradingview_automation.py --mode guide --symbol BTCUSDT --action BUY
```

화면에 나오는 **JSON 코드를 복붙할 준비**

---

### **Step 2: TradingView 열기**

```
https://www.tradingview.com/chart/?symbol=BTCUSDT
```

---

### **Step 3: 알림 추가**

1. 오른쪽 상단 벨 아이콘 클릭
2. "알림 추가" 클릭

---

### **Step 4: 조건 설정** (당신의 조건)

| 항목 | 예 |
|------|-----|
| 심볼 | BTCUSDT |
| 조건 | RSI < 30 (또는 당신의 조건) |
| 인터벌 | 1일 |

---

### **Step 5: "메시지" 탭 클릭**

텍스트 지우고 **Step 1에서 나온 JSON을 복붙**

```json
{
  "secret": "MySecret123456",
  "action": "BUY",
  "ticker": "BTCUSDT",
  "price": "{{close}}",
  "time": "{{timenow}}"
}
```

---

### **Step 6: "알림" 탭 클릭**

**웹훅 URL:**
```
http://localhost:8000/webhook
```

**체크박스:** ☑️ 웹훅 URL (필수!)

---

### **Step 7: "생성" 클릭**

✅ 완료!

---

## 🔄 **SELL도 같은 방식**

```bash
python scripts/tradingview_automation.py --mode guide --symbol BTCUSDT --action SELL
```

같은 단계 반복

---

## 🧪 **테스트**

```bash
python scripts/test_webhook.py
```

성공하면:
```
✅ All alerts processed successfully
```

---

## 📱 **Telegram 확인**

```
/queue      ← 대기 주문
/status     ← 봇 상태
/positions  ← 오픈 포지션
```

---

## 💡 **다른 심볼도 하려면**

```bash
python scripts/tradingview_automation.py --mode guide --symbol ETHUSDT --action BUY
python scripts/tradingview_automation.py --mode guide --symbol AAPL --action SELL
```

같은 방식 반복

---

## 📋 **일괄 생성 (많은 심볼)**

```bash
python scripts/tradingview_automation.py --mode batch --config scripts/tradingview_alerts_config.json
```

생성된 `tradingview_alerts_generated.json`에서 각 JSON을 TradingView에 하나씩 입력

---

**끝! 2분 안에 자동화 완료!** 🚀

