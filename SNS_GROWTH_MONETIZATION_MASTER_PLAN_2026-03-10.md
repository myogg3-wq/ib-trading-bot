# SNS 홍보 + 수익다변화 마스터 플랜 (자동매매 연계)

작성일: 2026-03-10
대상: KIS 기반 자동매매 시스템 운영자
목표: 신호/체결 데이터를 활용해 홍보 자동화, 고객 유입, 유료화, 플랫폼화까지 단계적으로 실행

---

## 1) 최종 목표와 운영 원칙

### 최종 목표
1. 자동매매 신호를 실시간 콘텐츠로 전환해 SNS 유입을 만든다.
2. 무료 사용자 -> 유료 구독자 -> 플랫폼 사용자로 단계 전환한다.
3. 매매 수익 외에 구독/지표/교육/플랫폼 수익을 만든다.

### 절대 원칙
1. 거래 경로와 홍보 경로를 분리한다. (홍보 실패가 주문 실행에 영향 0)
2. 수익 과장/허위 성과 금지. (손실/실패도 같은 비중으로 공개)
3. 개인정보/계좌정보/API 키 노출 금지.
4. 규제 이슈는 출시 전 법률 검토. (본 문서는 사업/기술 계획이며 법률 자문 아님)

---

## 2) 현재 시스템 기반 확장 포인트

현재 사용 중인 핵심 흐름:
1. TradingView Webhook 수신 -> `app/gateway/webhook.py`
2. 주문 큐 처리 -> `app/queue/order_worker.py`
3. 체결/실패 기록 -> DB (`Trade`, `AlertLog`, `Position`)
4. 텔레그램 운영 -> `app/notifications/telegram_bot.py`

홍보 자동화는 위 흐름에 "이벤트 퍼블리싱 레이어"를 추가하면 된다:
1. 이벤트 생성: `signal_received`, `order_filled`, `order_failed`, `daily_report`
2. 콘텐츠 생성: 템플릿 + LLM 설명
3. 검수/승인: 자동 또는 수동 승인
4. 채널 게시: Telegram Channel, X, Threads, Instagram, YouTube Shorts 스크립트
5. 성과 추적: 클릭/전환/구독/해지

---

## 3) 수익모델 설계 (Product Ladder)

### Tier 0: 무료
1. 지연된 요약 신호 (예: 15~60분 지연)
2. 일일/주간 성과 요약
3. 전략 교육 콘텐츠 일부

목적: 신뢰 확보 + 유입 최대화

### Tier 1: 입문 유료 (월 구독)
1. 실시간 신호 알림
2. 종목별 진입/청산 근거 설명
3. 위험도 레이블

목적: 첫 결제 전환

### Tier 2: 고급 유료 (월 구독)
1. 실시간 신호 + 리스크 리포트 + 포트폴리오 요약
2. 종목군별 성과 리포트
3. 월 1회 운영 리포트 라이브

목적: ARPU 상승 + 해지율 감소

### Tier 3: 일회성/라이선스
1. 트레이딩뷰 지표 판매 (개인 라이선스)
2. 전략 템플릿/알림 템플릿 패키지
3. 온보딩 세팅 서비스

목적: 구독 외 매출원 확보

### Tier 4: 플랫폼
1. 신호 대시보드
2. 사용자별 워치리스트/필터
3. 결제/권한/리포트 자동화

목적: 스케일 가능한 SaaS 구조

---

## 4) 채널 전략 (콘텐츠 용도 분리)

### Telegram
1. 핵심 사용자 운영 채널
2. 긴 글 설명 + 리포트 + 공지
3. 유료/무료 채널 분리 운영

### X (트위터)
1. 빠른 확산 + 실시간 반응
2. 짧은 신호 카드 + 링크 유입

### Threads/Instagram
1. 브랜딩 + 초보 친화형 설명
2. 카드뉴스/짧은 요약

### YouTube Shorts/Reels
1. 신호/성과를 스토리텔링으로 재활용
2. 신뢰 형성용 상단 퍼널

---

## 5) 메시지 포맷 표준 (신호 발생 시)

모든 채널 공통 블록:
1. 액션: BUY/SELL, 티커, 체결/예약 상태
2. 근거: 전략 조건 2~3개 (규칙 기반)
3. 리스크: 손실 가능성/시장 상황
4. CTA: 무료 채널/대기리스트/유료 링크
5. 디스클레이머: 투자권유 아님, 손실 가능

예시 템플릿:
1. 제목: `[신호] BUY HERO 체결`
2. 본문:
   - 이유: 2주봉 추세 유지 + 조건 A/B 충족
   - 리스크: 변동성 확대 구간, 분할 대응 필요
   - 운영: 오늘 동일종목 추가매수 제한 적용
3. 하단: `성과와 리스크 공개는 고정 원칙입니다.`

---

## 6) 기술 설계 (실행형)

### 6-1. 신규 컴포넌트
1. `app/promo/event_bus.py`
   - 이벤트 발행/구독 인터페이스
2. `app/promo/content_generator.py`
   - 템플릿 + LLM 설명 생성
3. `app/promo/publisher.py`
   - 채널별 게시 작업
4. `app/promo/channel_clients/`
   - `telegram_channel.py`, `x_client.py`, `threads_client.py` 등
5. `app/promo/moderation.py`
   - 금칙어/과장표현/규정문구 검사
6. `app/promo/metrics.py`
   - 게시/클릭/전환 로깅

### 6-2. 기존 코드 연결 포인트
1. `/Users/sehee/Desktop/SUB_Factory/ib-trading-bot/app/gateway/webhook.py`
   - Webhook 수신 시 `signal_received` 이벤트 발행
2. `/Users/sehee/Desktop/SUB_Factory/ib-trading-bot/app/queue/order_worker.py`
   - 체결/실패 시 `order_filled`, `order_failed` 이벤트 발행
3. `/Users/sehee/Desktop/SUB_Factory/ib-trading-bot/app/notifications/telegram_bot.py`
   - `/promo_status`, `/promo_pause`, `/promo_resume`, `/promo_queue` 명령 추가
4. `/Users/sehee/Desktop/SUB_Factory/ib-trading-bot/app/scheduler.py`
   - 일일/주간 홍보 리포트 스케줄 등록

### 6-3. 데이터 모델 (신규 테이블)
1. `content_event`
   - id, event_type, ticker, action, payload_json, created_at
2. `content_draft`
   - id, event_id, channel, draft_text, status(draft/approved/rejected), reviewer, created_at
3. `content_post`
   - id, draft_id, channel, post_id, published_at, delivery_status, error_message
4. `funnel_lead`
   - id, source_channel, campaign, utm, joined_at
5. `subscription_event`
   - id, lead_id/user_id, plan, action(start/renew/cancel), amount, happened_at

### 6-4. 장애/안전 설계
1. 게시 재시도: 3회 + 지수백오프
2. 중복 방지: `event_id + channel` unique
3. 회로차단기: 채널 API 오류율 임계치 초과 시 자동 pause
4. 분리 보장: 거래 큐와 홍보 큐 완전 별도 Redis 키 사용

---

## 7) 운영 정책 (SOP)

### 일일 운영 (20~30분)
1. 전일 게시 수/도달/클릭 점검
2. 실패 게시 재처리 큐 점검
3. 과장/오해 유발 문구 샘플 점검
4. 당일 CTA 문구 1개만 실험

### 주간 운영 (60~90분)
1. 채널별 유입/전환 리포트 작성
2. 성과 좋은 콘텐츠 유형 2개 확장
3. 성과 낮은 유형 2개 중단
4. 다음주 A/B 실험 2개 확정

### 월간 운영 (2~3시간)
1. 가격/상품 구조 점검
2. 해지 사유 분석
3. 기능 로드맵 우선순위 재조정

---

## 8) KPI 체계 (숫자로 관리)

### 퍼널 KPI
1. 노출 -> 클릭률(CTR)
2. 클릭 -> 무료가입 전환율
3. 무료 -> 유료 전환율
4. 유료 유지율(30/60/90일)

### 품질 KPI
1. 게시 실패율
2. 규정 위반 탐지율
3. 신호 대비 게시 지연시간(p50/p95)

### 사업 KPI
1. MRR (월 반복매출)
2. ARPU
3. CAC 대비 LTV
4. 채널별 순이익

---

## 9) 90일 실행 로드맵

### Day 1~7 (기반 구축)
1. 이벤트/드래프트/포스트 테이블 생성
2. `event_bus`, `content_generator` 골격 구현
3. 텔레그램에 홍보 상태 명령 추가
4. 기본 템플릿 3종(신호, 체결, 리포트) 작성

완료 기준:
1. 신호 1건 발생 시 홍보 드래프트가 DB에 자동 생성
2. 승인 후 텔레그램 채널 1곳 게시 성공

### Day 8~21 (자동화 1차)
1. X/Threads 중 1개 채널 연동
2. 게시 재시도/중복방지 구현
3. UTM 링크 삽입 + 클릭 추적
4. 주간 리포트 자동 게시

완료 기준:
1. 3개 채널 중 2개 자동 게시 성공률 98% 이상
2. 게시 지연 p95 60초 이하

### Day 22~45 (전환 최적화)
1. 랜딩페이지 v1 (성과/전략/가입 CTA)
2. 무료/유료 상품 페이지 연결
3. A/B 테스트 4개 실행 (후킹 문구, CTA 위치, 포맷)

완료 기준:
1. 무료가입 전환율 목표치 달성
2. 유료 체험 전환 퍼널 구축 완료

### Day 46~90 (수익화 고도화)
1. 유료 플랜 2단계 도입
2. 지표 라이선스 판매 페이지 오픈
3. 월간 성과 대시보드 공개

완료 기준:
1. MRR 안정적 발생
2. 채널별 CAC/LTV 계산 가능

---

## 10) 팀/리소스 운영안

최소 인원:
1. 운영 총괄(대표): 상품/가격/콘텐츠 방향
2. 개발(현재 시스템 담당): 자동화/지표/API/데이터
3. 디자인/콘텐츠(파트타임 가능): 카드뉴스/영상 리폼

도구:
1. 콘텐츠 캘린더 (Notion/Linear)
2. 분석 (PostHog/GA4 + DB 대시보드)
3. 고객관리 (간단 CRM)

---

## 11) 리스크 레지스터

1. 리스크: 과장 광고/오인 유발
   - 대응: 자동 문구 검사 + 수동 승인 + 고정 디스클레이머
2. 리스크: 신호 오류 전파
   - 대응: 게시 전 이벤트 무결성 검증, 실패 시 자동 중단
3. 리스크: API 차단/Rate limit
   - 대응: 채널별 큐 분리 + 지수백오프 + 회로차단
4. 리스크: 운영 과부하
   - 대응: 템플릿화/재활용/우선순위 채널 2개 집중

---

## 12) 내일 바로 시작할 체크리스트

1. 신규 모듈/테이블 이름 확정
2. 채널 우선순위 2개 확정 (예: Telegram + X)
3. 게시 문구 템플릿 10개 초안 작성
4. 디스클레이머 고정 문구 확정
5. 무료/유료 상품 구성(가격/혜택) 1차안 확정
6. Day 1~7 개발 태스크를 이슈로 쪼개기
7. 첫 주 KPI 목표치 설정

---

## 13) 성공 판단 기준

1. 거래 시스템 안정성 유지 (홍보 기능 추가 후도 주문 경로 장애 0)
2. 유입 증가가 실제 전환으로 연결
3. 구독 유지율이 개선되고 해지 사유가 관리됨
4. 운영 시간이 줄어들고 반복 업무가 자동화됨
