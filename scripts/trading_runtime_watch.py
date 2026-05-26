#!/usr/bin/env python3
"""Host-side automation that checks the trading stack and alerts Telegram on anomalies."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "runtime"
STATE_FILE = STATE_DIR / "trading_runtime_watch_state.json"
EXPECTED_SERVICES = {
    "api": None,
    "worker": None,
    "telegram": None,
    "db": "healthy",
    "redis": "healthy",
}
DOCKER_BIN = "/usr/bin/docker" if Path("/usr/bin/docker").exists() else "docker"
PROBE_SERVICE = "telegram"
PROBE_SCRIPT = "scripts/trading_runtime_probe.py"


def run_cmd(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def load_env_file() -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.exists():
        return env
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def send_telegram(text: str) -> None:
    env = load_env_file()
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("telegram_bot_token")
    chat_id = env.get("TELEGRAM_CHAT_ID") or env.get("telegram_chat_id")
    if not token or not chat_id:
        raise RuntimeError("Telegram bot token/chat_id not found in .env")

    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram send failed with HTTP {resp.status}")


def read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"last_status": "unknown", "last_issue_hash": None, "last_notified_at": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_status": "unknown", "last_issue_hash": None, "last_notified_at": None}


def write_state(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def get_service_statuses() -> tuple[dict[str, dict[str, Any]], list[str]]:
    proc = run_cmd([DOCKER_BIN, "compose", "ps", "--format", "json"], timeout=30)
    if proc.returncode != 0:
        return {}, [f"docker compose ps 실패: {proc.stderr.strip() or proc.stdout.strip() or '알 수 없는 오류'}"]

    statuses: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        service = row.get("Service")
        if service:
            statuses[service] = row

    for service, expected_health in EXPECTED_SERVICES.items():
        row = statuses.get(service)
        if not row:
            issues.append(f"서비스 누락: {service}")
            continue
        if row.get("State") != "running":
            issues.append(f"서비스 비정상: {service} 상태={row.get('State')}")
        health = str(row.get("Health") or "").strip()
        if expected_health and health != expected_health:
            issues.append(f"서비스 헬스 비정상: {service} health={health or '-'}")

    return statuses, issues


def get_api_health_issue() -> str | None:
    last_issue: str | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as resp:
                if resp.status != 200:
                    last_issue = f"API /health 응답 비정상: HTTP {resp.status}"
                else:
                    body = resp.read().decode("utf-8", "replace")
                    if 'healthy' not in body.lower():
                        last_issue = f"API /health 본문 비정상: {body[:120]}"
                    else:
                        return None
        except Exception as exc:
            last_issue = f"API /health 호출 실패: {exc}"

        if attempt < 3:
            time.sleep(1)

    return f"{last_issue} (3회 재시도 후 실패)" if last_issue else None


def get_queue_lengths() -> tuple[dict[str, int], list[str]]:
    issues: list[str] = []
    lengths: dict[str, int] = {}
    queue_map = {
        "buy": "orders:buy",
        "sell": "orders:sell",
        "processing": "orders:processing",
        "pending": "orders:pending",
    }
    for key, redis_key in queue_map.items():
        proc = run_cmd([DOCKER_BIN, "exec", "ib-trading-bot-redis-1", "redis-cli", "LLEN", redis_key], timeout=15)
        if proc.returncode != 0:
            issues.append(f"Redis 큐 조회 실패: {redis_key} ({proc.stderr.strip() or proc.stdout.strip()})")
            lengths[key] = -1
            continue
        try:
            lengths[key] = int(proc.stdout.strip() or 0)
        except ValueError:
            lengths[key] = -1
            issues.append(f"Redis 큐 길이 파싱 실패: {redis_key} -> {proc.stdout.strip()!r}")
    return lengths, issues


def get_recent_conflict_count() -> tuple[int, str | None]:
    proc = run_cmd([DOCKER_BIN, "compose", "logs", "--since=90m", "telegram"], timeout=30)
    if proc.returncode != 0:
        return 0, f"telegram 로그 조회 실패: {proc.stderr.strip() or proc.stdout.strip()}"
    text = proc.stdout
    return text.count("telegram.error.Conflict"), None


def run_probe() -> tuple[dict[str, Any] | None, str | None]:
    probe_code = (ROOT / PROBE_SCRIPT).read_text()
    proc = run_cmd([DOCKER_BIN, "compose", "exec", "-T", PROBE_SERVICE, "python", "-c", probe_code], timeout=90)
    if proc.returncode != 0:
        return None, proc.stderr.strip() or proc.stdout.strip() or "probe 실행 실패"

    stdout = proc.stdout.strip()
    if not stdout:
        return None, "probe 출력이 비어 있습니다"

    last_line = stdout.splitlines()[-1]
    try:
        return json.loads(last_line), None
    except json.JSONDecodeError:
        return None, f"probe JSON 파싱 실패: {last_line[:200]}"


def format_krw_from_usd(usd_amount: float, usdkrw_rate: float) -> str:
    if usdkrw_rate <= 0:
        return f"${float(usd_amount or 0.0):,.2f}"
    return f"{float(usd_amount or 0.0) * usdkrw_rate:,.0f}원"


def format_krw(value: Any) -> str:
    try:
        return f"{float(value or 0.0):,.0f}원"
    except Exception:
        return "0원"


def simplify_failure_reason(error: str) -> str:
    text = str(error or "").strip()
    if not text:
        return "원인 미상"
    if "현금" in text or "cash" in text.lower() or "insufficient" in text.lower():
        return "현금 부족"
    if "미체결" in text or "취소" in text:
        return "미체결 후 취소"
    if "유효 가격" in text or "가격" in text or "quote" in text.lower():
        return "가격 조회 실패"
    if "server disconnected" in text.lower() or "500" in text or "timeout" in text.lower():
        return "KIS 일시 오류"
    if "보유 포지션" in text or "보유" in text:
        return "보유수량 없음"
    return text[:60]


def format_failed_trade_samples(samples: list[dict[str, Any]], *, max_items: int = 5) -> str:
    parts: list[str] = []
    for item in samples[:max_items]:
        side = str(item.get("side") or "?").upper()
        ticker = str(item.get("ticker") or "?").upper()
        reason = simplify_failure_reason(str(item.get("error") or ""))
        parts.append(f"{side} {ticker}({reason})")
    if len(samples) > max_items:
        parts.append("...")
    return ", ".join(parts) if parts else "상세 없음"


def humanize_issue(issue: str) -> str:
    text = str(issue or "").strip()
    if not text:
        return ""
    if text.startswith("BUY 대기 주문 대비 현금 부족 예상:"):
        return text.replace("BUY 대기 주문 대비 현금 부족 예상:", "현금 부족:")
    if text.startswith("최근 6시간 실제 주문 실패"):
        return text.replace("최근 6시간 실제 주문 실패", "주문 실패")
    if text.startswith("DB/KIS 보유종목 불일치"):
        return text.replace("DB/KIS 보유종목 불일치", "보유종목 불일치")
    if text.startswith("매도 신호 후 아직 보유 중인 종목"):
        return text.replace("매도 신호 후 아직 보유 중인 종목", "매도 누락 의심")
    if text.startswith("KIS 잔고 조회 실패"):
        return "한국투자 잔고 조회 실패"
    if text.startswith("API /health"):
        return "서버 상태 확인 실패"
    if text.startswith("해당 시장 장중인데 pending 큐가 남아 있음"):
        return text.replace("해당 시장 장중인데 pending 큐가 남아 있음", "장중 대기 주문 남음")
    return text


def build_summary(*, services: dict[str, dict[str, Any]], queue_lengths: dict[str, int], probe: dict[str, Any] | None) -> list[str]:
    service_bits = []
    for service in EXPECTED_SERVICES:
        row = services.get(service)
        if not row:
            service_bits.append(f"{service}=없음")
            continue
        health = str(row.get("Health") or "").strip()
        suffix = f"/{health}" if health else ""
        service_bits.append(f"{service}={row.get('State')}{suffix}")

    queue_line = f"큐 buy={queue_lengths.get('buy')} sell={queue_lengths.get('sell')} processing={queue_lengths.get('processing')} pending={queue_lengths.get('pending')}"
    lines = [" | ".join(service_bits), queue_line]

    if probe:
        poller = probe.get("poller") or {}
        lines.append(
            f"시장={probe.get('market', {}).get('status', '-')} | 텔레그램 폴러={poller.get('status', '-')} | TTL={poller.get('ttl', '-') }초"
        )
        symbol_suffix = " (종목대조 생략)" if probe.get("kis_symbol_check_skipped") else ""
        lines.append(
            f"DB/KIS 보유종목={probe.get('db_open_tickers', '-')} / {probe.get('kis_open_tickers', '-')}{symbol_suffix} | 최근6시간 주문실패={probe.get('failed_trades_last_6h', '-') }건"
        )
        cash_coverage = probe.get("pending_buy_cash_coverage") or {}
        if cash_coverage.get("shortage"):
            rate = float(cash_coverage.get("usdkrw_rate") or 0.0)
            shortage_text = format_krw_from_usd(float(cash_coverage.get("shortage_usd") or 0.0), rate)
            lines.append(
                f"현금부족예상=BUY {cash_coverage.get('coverable_order_count', 0)}/{cash_coverage.get('order_count', 0)}건 가능 | 부족 {shortage_text}"
            )
    return lines


def evaluate_issues(*, service_issues: list[str], api_issue: str | None, queue_issues: list[str], queue_lengths: dict[str, int], conflict_count: int, probe: dict[str, Any] | None, probe_error: str | None) -> list[str]:
    issues = list(service_issues)
    if api_issue:
        issues.append(api_issue)
    issues.extend(queue_issues)

    if conflict_count >= 5:
        issues.append(f"최근 90분 텔레그램 polling conflict 감지: {conflict_count}회")

    if probe_error:
        issues.append(f"앱 내부 probe 실패: {probe_error}")
        return issues

    assert probe is not None
    poller = probe.get("poller") or {}
    if poller.get("status") != "정상":
        issues.append(f"텔레그램 폴러 상태 비정상: {poller.get('status')}")

    mismatch_symbols = probe.get("position_mismatch_symbols") or []
    if mismatch_symbols and not probe.get("kis_symbol_check_skipped"):
        preview = ", ".join(mismatch_symbols[:8])
        if len(mismatch_symbols) > 8:
            preview += ", ..."
        issues.append(f"DB/KIS 보유종목 불일치 {len(mismatch_symbols)}개: {preview}")

    if probe.get("kis_error"):
        issues.append(f"KIS 잔고 조회 실패: {probe['kis_error']}")

    missed_sells = int(probe.get("missed_sell_candidates") or 0)
    if missed_sells > 0:
        samples = probe.get("missed_sell_samples") or []
        preview = ", ".join(str(item.get("ticker")) for item in samples[:8] if item.get("ticker"))
        suffix = f": {preview}" if preview else ""
        issues.append(f"매도 신호 후 아직 보유 중인 종목 {missed_sells}개{suffix}")

    stale_pending = int(probe.get("stale_pending_alerts") or 0)
    if stale_pending > 0:
        issues.append(f"대기 주문 만료 기준 초과 알림 {stale_pending}건")

    failed_trades = int(probe.get("failed_trades_last_6h") or 0)
    if failed_trades > 0:
        samples = probe.get("failed_trade_samples") or []
        issues.append(
            f"최근 6시간 실제 주문 실패 {failed_trades}건: "
            f"{format_failed_trade_samples(samples)}"
        )

    cash_coverage = probe.get("pending_buy_cash_coverage") or {}
    if cash_coverage.get("shortage"):
        rate = float(cash_coverage.get("usdkrw_rate") or 0.0)
        shortage_text = format_krw_from_usd(float(cash_coverage.get("shortage_usd") or 0.0), rate)
        required_text = format_krw_from_usd(float(cash_coverage.get("required_usd") or 0.0), rate)
        available_text = format_krw_from_usd(float(cash_coverage.get("available_after_reserve_usd") or 0.0), rate)
        issues.append(
            "BUY 대기 주문 대비 현금 부족 예상: "
            f"{cash_coverage.get('coverable_order_count', 0)}/{cash_coverage.get('order_count', 0)}건 가능, "
            f"필요 {required_text}, 가용 {available_text}, 부족 {shortage_text}"
        )

    processing_queue = int(queue_lengths.get("processing", 0) or 0)
    active_queue = int(queue_lengths.get("buy", 0) or 0) + int(queue_lengths.get("sell", 0) or 0)
    if processing_queue > 15:
        issues.append(f"처리중 큐가 과도함: {processing_queue}건")
    if active_queue > 60:
        issues.append(f"활성 주문 큐 적체: {active_queue}건")

    pending_oldest = probe.get("pending_oldest_minutes")
    if isinstance(pending_oldest, (int, float)) and pending_oldest > 120:
        probe_queue = probe.get("queue") or {}
        markets = probe.get("markets") or {}
        if markets:
            open_pending_parts: list[str] = []
            if int(probe_queue.get("pending_us", 0) or 0) > 0 and str((markets.get("US") or {}).get("status")) == "OPEN":
                open_pending_parts.append(f"미국 {int(probe_queue.get('pending_us', 0) or 0)}건")
            if int(probe_queue.get("pending_krx", 0) or 0) > 0 and str((markets.get("KRX") or {}).get("status")) == "OPEN":
                open_pending_parts.append(f"한국 {int(probe_queue.get('pending_krx', 0) or 0)}건")
            asia_pending = int(probe_queue.get("pending_asia", 0) or 0)
            asia_open = any(
                str((markets.get(market_key) or {}).get("status")) == "OPEN"
                for market_key in ("HKEX", "SSE", "SZSE", "TSE")
            )
            if asia_pending > 0 and asia_open:
                open_pending_parts.append(f"아시아 {asia_pending}건")
            unknown_pending = int(probe_queue.get("pending_unknown", 0) or 0)
            if unknown_pending > 0 and str((markets.get("US") or {}).get("status")) == "OPEN":
                open_pending_parts.append(f"미분류 {unknown_pending}건")

            if open_pending_parts:
                issues.append(
                    "해당 시장 장중인데 pending 큐가 남아 있음: "
                    f"{', '.join(open_pending_parts)} (최고 {pending_oldest}분)"
                )
        else:
            pending_queue = int(queue_lengths.get("pending", 0) or 0)
            market_status = str((probe.get("market") or {}).get("status") or "")
            if market_status == "OPEN" and pending_queue > 0:
                issues.append(f"장중인데 pending 큐가 {pending_queue}건 남아 있음 (최고 {pending_oldest}분)")

    return issues


def issue_fingerprint(issues: list[str]) -> str:
    normalized = "\n".join(sorted(issues))
    return hashlib.sha256(normalized.encode()).hexdigest()


def build_issue_message(*, issues: list[str], summary_lines: list[str], probe: dict[str, Any] | None = None) -> str:
    lines = ["자동 점검: 확인 필요"]

    cash_coverage = (probe or {}).get("pending_buy_cash_coverage") or {}
    if cash_coverage.get("shortage"):
        lines.append(
            "현금 부족: "
            f"BUY 대기 {cash_coverage.get('order_count', 0)}건 중 "
            f"{cash_coverage.get('coverable_order_count', 0)}건 가능"
        )
        shortage_krw = cash_coverage.get("shortage_krw")
        if shortage_krw is not None:
            lines.append(f"부족 금액: {format_krw(shortage_krw)}")
        lines.append("조치: 한국투자에 현금을 더 넣으면 됩니다.")
        return "\n".join(lines)

    for issue in issues[:3]:
        simple = humanize_issue(issue)
        if simple:
            lines.append(f"- {simple}")
    if len(issues) > 3:
        lines.append(f"- 그 외 {len(issues) - 3}건")
    return "\n".join(lines)


def build_recovery_message(*, summary_lines: list[str]) -> str:
    return "자동 점검: 정상화됨\n직전 문제는 해소됐습니다."


def main() -> int:
    service_statuses, service_issues = get_service_statuses()
    api_issue = get_api_health_issue()
    queue_lengths, queue_issues = get_queue_lengths()
    conflict_count, conflict_error = get_recent_conflict_count()
    if conflict_error:
        service_issues.append(conflict_error)
    probe, probe_error = run_probe()

    issues = evaluate_issues(
        service_issues=service_issues,
        api_issue=api_issue,
        queue_issues=queue_issues,
        queue_lengths=queue_lengths,
        conflict_count=conflict_count,
        probe=probe,
        probe_error=probe_error,
    )
    summary_lines = build_summary(services=service_statuses, queue_lengths=queue_lengths, probe=probe)

    print("[summary]")
    for line in summary_lines:
        print(line)
    if issues:
        print("[issues]")
        for issue in issues:
            print(f"- {issue}")

    state = read_state()
    now_iso = datetime.now(timezone.utc).isoformat()

    if issues:
        current_hash = issue_fingerprint(issues)
        should_notify = state.get("last_status") != "issue" or state.get("last_issue_hash") != current_hash
        if should_notify:
            send_telegram(build_issue_message(issues=issues, summary_lines=summary_lines, probe=probe))
            state = {"last_status": "issue", "last_issue_hash": current_hash, "last_notified_at": now_iso}
            write_state(state)
            print("[notify] issue alert sent")
        else:
            state.update({"last_status": "issue", "last_issue_hash": current_hash})
            write_state(state)
            print("[notify] same issue; skipped")
        return 1

    if state.get("last_status") == "issue":
        send_telegram(build_recovery_message(summary_lines=summary_lines))
        print("[notify] recovery alert sent")

    write_state({"last_status": "healthy", "last_issue_hash": None, "last_notified_at": now_iso})
    return 0


if __name__ == "__main__":
    sys.exit(main())
