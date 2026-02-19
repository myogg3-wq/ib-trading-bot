# TradingView 180개 종목 알람 설정 가이드

## 3가지 방법 비교

| 방법 | 설정 시간 | 필요 알람 수 | 최소 플랜 | 난이도 |
|------|-----------|-------------|-----------|--------|
| **A. Pine 스크리너** | 30분 | **5개** | Essential ($15) | 중 |
| **B. 워치리스트 알람** | 10분 | **2개** | Expert ($240) | 하 |
| **C. TVAM 확장 프로그램** | 20분 | **180개** | Premium ($50) | 하 |

---

## 방법 A: Pine Script 스크리너 (가장 추천)

### 왜 추천?
- 알람 5개로 180종목 전부 커버
- 저렴한 플랜에서도 가능
- 종목 추가/삭제가 스크립트 설정에서 바로 가능

### 설정 절차

#### 1단계: Pine Script 추가
1. TradingView 차트 열기 (아무 종목이나)
2. Pine Editor 열기 (하단 탭)
3. `multi_ticker_screener.pine` 코드 복사-붙여넣기
4. **중요**: `getBuyCondition`과 `getSellCondition` 함수를
   당신의 매수/매도 조건으로 교체
5. "Add to chart" 클릭

#### 2단계: 종목 입력 (배치 1)
1. 차트에 추가된 인디케이터 설정(톱니바퀴) 클릭
2. Ticker 01 ~ 36에 첫 36개 종목 입력
3. Webhook Secret에 당신의 시크릿 입력
4. 확인

#### 3단계: 알람 생성 (배치 1)
1. 알람 버튼 (Alt+A)
2. Condition: "Multi-Ticker Bot [Batch 1]"
3. Trigger: "Any alert() function call"
4. Webhook URL: `https://your_domain.com/webhook`
5. Message: `{{message}}`   ← 이것만! 스크립트가 JSON을 자동 생성
6. Alert name: "Batch 1"
7. Create

#### 4단계: 배치 2~5 반복
1. 같은 스크립트를 차트에 다시 추가
2. 이름을 "Batch 2"로 변경
3. Ticker 01~36에 다음 36개 종목 입력
4. 알람 생성 (위와 동일)
5. Batch 3, 4, 5도 반복

#### 최종 결과:
```
차트에 인디케이터 5개
알람 5개 (각 배치당 1개)
180개 종목 전부 커버
Webhook은 전부 같은 URL
```

---

## 방법 B: 워치리스트 알람 (가장 간단하지만 비쌈)

### 설정 절차

#### 1단계: 워치리스트 생성
1. TradingView 오른쪽 패널 → Watchlist
2. "+" → "Create new list" → "Trading Bot Tickers"
3. 180개 종목 전부 추가
   (검색창에 티커 입력 → Add)

#### 2단계: 워치리스트 알람 생성
1. 차트에 당신의 인디케이터/전략 적용
2. 알람 생성 (Alt+A)
3. Symbol 부분에서 "Watchlist" 선택 → "Trading Bot Tickers"
4. Condition: 당신의 인디케이터 조건
5. Webhook URL: `https://your_domain.com/webhook`
6. Message:
```json
{"secret":"YOUR_SECRET","action":"BUY","ticker":"{{ticker}}","price":"{{close}}","alert_id":"{{alert_id}}"}
```
7. Create

#### 주의사항:
- Expert 플랜 필요 ($240/월) — 워치리스트 알람이 10개
- 알람이 2개월 후 만료 → 재생성 필요
- BUY/SELL 조건별로 별도 알람 필요할 수 있음

---

## 방법 C: TVAlertsManager (Chrome 확장)

### 설정 절차

#### 1단계: 설치
1. Chrome Web Store에서 "TVAlertsManager" 검색 → 설치
2. Google Sheets 연결

#### 2단계: 스프레드시트 작성
Google Sheet에 180행 작성:

| Ticker | Condition | Webhook URL | Message |
|--------|-----------|-------------|---------|
| AAPL | Your Indicator | https://your.com/webhook | {"secret":"...","action":"BUY","ticker":"AAPL",...} |
| MSFT | Your Indicator | https://your.com/webhook | {"secret":"...","action":"BUY","ticker":"MSFT",...} |
| ... | ... | ... | ... |

#### 3단계: 일괄 생성
1. TradingView 차트 열기
2. TVAlertsManager 확장 아이콘 클릭
3. "Load Alerts" → 스프레드시트에서 자동 생성

#### 주의사항:
- Premium 플랜 필요 (180개 개별 알람)
- 무료 티어: 월 100건 제한

---

## 당신의 기존 인디케이터가 있는 경우

이미 만든 지표가 있다면 Pine Script 스크리너(방법 A)의
매수/매도 조건 부분만 교체하면 됩니다:

```pine
// ===== YOUR TRADING LOGIC HERE =====
// 이 부분을 당신의 매수/매도 조건으로 교체

getBuyCondition(src) =>
    // 당신의 매수 조건
    // 예: 골든크로스
    sma20 = ta.sma(src, 20)
    sma50 = ta.sma(src, 50)
    ta.crossover(sma20, sma50)

getSellCondition(src) =>
    // 당신의 매도 조건
    // 예: 데드크로스
    sma20 = ta.sma(src, 20)
    sma50 = ta.sma(src, 50)
    ta.crossunder(sma20, sma50)
```

혹은 기존 인디케이터의 핵심 로직을 이 스크리너 안에 통합하세요.

---

## 종목 추가/삭제 시

### Pine Script 스크리너(방법 A):
- 스크립트 설정에서 티커 변경 → 자동 반영
- 36개 이하로 줄면 Enable 체크 해제
- 36개 초과하면 새 배치(인스턴스) 추가

### 워치리스트 알람(방법 B):
- 워치리스트에 종목 추가/삭제 → 자동 반영

### TVAlertsManager(방법 C):
- 스프레드시트 수정 → "Load Alerts" 다시 실행
