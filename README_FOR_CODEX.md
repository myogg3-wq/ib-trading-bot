# Codex 작업 기준

이 폴더를 새 세션에서 열었을 때 먼저 확인할 기준입니다.

## 폴더 역할

- 현재 폴더: `/Users/sehee/Desktop/자동투자_시스템/ib-trading-bot`
- 역할: 자동투자 시스템의 로컬 작업 복사본
- 실전 실행 위치: VPS `/root/ib-trading-bot`
- 원본 보관 위치: `/Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot`

## 운영 판단 기준

로컬 Mac에서 아래 항목이 없어도 곧바로 실전 장애는 아닙니다.

- `8000`, `5432`, `6379` 포트 리스닝
- `docker`, `psql`, `redis-cli` 로컬 설치
- 로컬 Python 전역 의존성

실전 상태는 VPS에서 확인합니다.

```bash
curl -fsS http://1.234.65.43/health
ssh root@1.234.65.43 'cd /root/ib-trading-bot && docker compose ps'
```

## 최근 핵심 변경

2026-05-25에 TradingView 웹훅 타임아웃 완화를 위해 아래 구조로 개선했습니다.

- 웹훅 수신 시 주문 큐 적재를 먼저 수행하고 빠르게 응답합니다.
- DB 감사 기록과 Telegram 수신 알림은 백그라운드로 처리합니다.
- Redis idempotency guard로 같은 알러트의 중복 큐 적재를 막습니다.

관련 파일:

- `app/gateway/webhook.py`
- `app/queue/order_queue.py`
- `app/queue/order_worker.py`
- `app/config.py`
- `.env.example`
- `tests/test_hardening.py`

## 보안 규칙

- 문서에 실제 토큰, 웹훅 시크릿, VPS 비밀번호, 계좌번호를 적지 않습니다.
- `.env` 값은 화면 출력이나 보고서에 그대로 노출하지 않습니다.
- `.env.backup-*`와 `.runtime/kis_access_token.json` 같은 로컬 비밀 백업/캐시는 복사본에 보관하지 않습니다.
- TradingView 알러트 실패분을 재전송하기 전에는 중복 주문 가능성을 먼저 확인합니다.

## 테스트 기준

로컬 전역 Python이 아니라 프로젝트 가상환경을 우선 사용합니다.

```bash
PYTHONPATH=. ./.venv/bin/python tests/test_hardening.py
PYTHONPATH=. ./.venv/bin/python tests/test_kis_domestic_support.py
```

전체 테스트는 기존 웹 플랫폼 테스트 데이터/브로커 fallback 기대값과 충돌할 수 있으므로, 실패 시 원인을 분리해서 봅니다.
