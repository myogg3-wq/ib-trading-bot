# 로컬 복사본 정리 보고서

정리일: 2026-05-25

## 처리한 항목

- 문서 파일에서 실제 Telegram 토큰 형태의 값이 남아 있는지 검사했고, 남아 있던 값은 마스킹했습니다.
- 문서 파일에서 비밀번호 형태의 값이 남아 있는지 검사했고, 남아 있던 값은 마스킹했습니다.
- `CURRENT_STATUS.md`를 안전한 운영 상태 문서로 교체했습니다.
- 새 세션 혼선을 줄이기 위해 `README_FOR_CODEX.md`를 추가했습니다.
- 실전 실행 위치와 로컬 복사본의 역할을 분리해 적었습니다.
- 숨김 `.env.backup-*` 파일은 로컬 복사본에서 삭제했습니다.
- 로컬 KIS 토큰 캐시 `.runtime/kis_access_token.json`은 삭제했습니다.
- 현재 `.env`는 남겨두되 파일 권한을 소유자만 읽고 쓸 수 있도록 제한했습니다.
- `TROUBLESHOOTING.md`의 DB 비밀번호 예시는 실제 값처럼 보이지 않도록 placeholder로 고쳤습니다.
- `scripts/test_webhook.py`는 고정 문자열 대신 `WEBHOOK_URL`, `WEBHOOK_SECRET` 환경변수를 우선 사용하도록 정리했습니다.
- `scripts/test_webhook.py`는 기본적으로 로컬 URL만 허용하고, 실전/공개 웹훅 URL은 명시 확인 환경변수 없이는 실행을 막도록 했습니다.
- KIS-only 운영 방향에 맞춰 broker routing 테스트 기대값을 `kis` fallback으로 맞췄습니다.
- 전체 테스트 실행 시 웹 플랫폼 테스트가 실제 `output/platform/*.json` 상태 파일을 물지 않도록 테스트용 store 객체를 재설정했습니다.
- KIS 매도 처리 테스트가 실서버 시세 API를 호출하지 않도록 `get_quote_snapshot`을 mock하도록 고쳤습니다.
- KIS 테스트의 토큰 캐시 경로를 `tests/.tmp_kis_access_token.json`으로 돌리고 종료 시 삭제되도록 했습니다.
- 새 `.gitattributes`를 추가해 앞으로 텍스트 파일은 LF 기준으로 다루도록 했습니다.

## 건드리지 않은 항목

- 실전 VPS의 `.env` 값은 변경하지 않았습니다.
- 원본 폴더 `/Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot`는 변경하지 않았습니다.
- 로컬 대량 diff는 자동 되돌림하지 않았습니다. 이 변경 묶음에는 기존 KIS 전환 작업과 줄바꿈 변화가 섞여 있어, 일괄 revert 시 필요한 기능 작업까지 삭제될 수 있습니다.

## 검증한 항목

```bash
rg -l '[0-9]{8,10}:[A-Za-z0-9_-]{30,}' --glob '*.md' --glob '*.txt' --glob '!node_modules/**' --glob '!.venv/**' --glob '!output/**' .
rg -l -P '(?i)(비밀번호|password)\s*[:=]\s*(?!\[REDACTED\])\S' --glob '*.md' --glob '*.txt' --glob '!node_modules/**' --glob '!.venv/**' --glob '!output/**' .
find . -maxdepth 1 -name '.env*' -print
find . -maxdepth 3 \( -path './.runtime/*' -o -path './runtime/*' \) -type f -print
rg --hidden -l -P '[0-9]{8,10}:[A-Za-z0-9_-]{30,}' --glob '!node_modules/**' --glob '!.venv/**' --glob '!output/**' --glob '!.git/**' --glob '!.env' .
rg --hidden -l -P --glob '!node_modules/**' --glob '!.venv/**' --glob '!output/**' --glob '!.git/**' --glob '!.env' -- '-----BEGIN (RSA|DSA|EC|OPENSSH|PRIVATE) KEY-----' .
PYTHONPATH=. ./.venv/bin/python tests/test_hardening.py
PYTHONPATH=. ./.venv/bin/python tests/test_kis_domestic_support.py
PYTHONPATH=. ./.venv/bin/python -m py_compile app/gateway/webhook.py app/queue/order_queue.py app/queue/order_worker.py app/config.py tests/test_hardening.py
PYTHONPATH=. ./.venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=. ./.venv/bin/python - <<'PY'
import asyncio
import unittest

_orig = asyncio.BaseEventLoop.create_connection
async def guard(self, protocol_factory, host=None, port=None, *args, **kwargs):
    if host not in {None, "testserver", "localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(f"blocked network during tests: {host}:{port}")
    return await _orig(self, protocol_factory, host, port, *args, **kwargs)
asyncio.BaseEventLoop.create_connection = guard
suite = unittest.defaultTestLoader.discover("tests")
result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
WEBHOOK_URL=http://1.234.65.43/webhook PYTHONPATH=. ./.venv/bin/python scripts/test_webhook.py
git diff --check
```

## 다음 기준

- 앞으로 이 로컬 폴더에서 작업할 때는 `README_FOR_CODEX.md`를 먼저 확인합니다.
- 배포 대상 파일은 기능 변경 파일만 선별하고, 문서/줄바꿈 대량 변경과 섞지 않습니다.
- 민감정보는 문서에 쓰지 않고 `.env` 또는 별도 비밀 저장소에서만 관리합니다.
- 전체 `git diff --check`는 통과했습니다.
