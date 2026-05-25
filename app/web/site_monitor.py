"""Automated website health and incident monitoring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = PROJECT_ROOT / "output" / "site-monitor" / "state.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "site-monitor" / "latest_report.json"

SITE_CHECKS = (
    {
        "id": "health",
        "label": "API health",
        "path": "/health",
        "kind": "json",
        "required_status": 200,
    },
    {
        "id": "home",
        "label": "Home page",
        "path": "/",
        "kind": "html",
        "required_status": 200,
        "markers": ("Signal Loom", "/llms.txt"),
    },
    {
        "id": "platform",
        "label": "Interactive platform",
        "path": "/platform",
        "kind": "html",
        "required_status": 200,
        "markers": ("Signal Loom", "thread-search", "platform-static/platform.js"),
    },
    {
        "id": "blueprint",
        "label": "Platform blueprint API",
        "path": "/api/platform/blueprint",
        "kind": "json",
        "required_status": 200,
    },
    {
        "id": "platform_js",
        "label": "Platform JS asset",
        "path": "/platform-static/platform.js",
        "kind": "text",
        "required_status": 200,
        "markers": ("SUPPORTED_LANGUAGES", "requestJson"),
    },
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path() -> Path:
    configured = (settings.site_monitor_state_path or "").strip()
    return Path(configured) if configured else DEFAULT_STATE_PATH


def _report_path() -> Path:
    configured = (settings.site_monitor_report_path or "").strip()
    return Path(configured) if configured else DEFAULT_REPORT_PATH


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load site monitor json", path=str(path), error=str(exc))
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _status_rank(status: str) -> int:
    return {"healthy": 0, "degraded": 1, "down": 2}.get(status, 2)


def _render_check_message(check: dict[str, Any]) -> str:
    icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}.get(check["severity"], "•")
    code = check.get("status_code")
    code_text = f"HTTP {code}" if code else "no response"
    return (
        f"{icon} {check['label']}: {check['status'].upper()} · "
        f"{code_text} · {check['elapsed_ms']}ms · {check['detail']}"
    )


def summarize_report(report: dict[str, Any]) -> str:
    lines = [
        "🛰️ 사이트 점검 리포트",
        f"상태: {report['overall_status'].upper()}",
        f"점검 시각(UTC): {report['checked_at']}",
        (
            f"정상 {report['healthy_checks']}개 · "
            f"경고 {report['warning_checks']}개 · "
            f"오류 {report['error_checks']}개"
        ),
        "",
    ]
    lines.extend(_render_check_message(check) for check in report["checks"])
    return "\n".join(lines)


def build_notification_message(
    previous_state: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    previous_status = previous_state.get("overall_status", "unknown")
    previous_fingerprint = previous_state.get("problem_fingerprint", "")
    current_status = report["overall_status"]
    current_fingerprint = report["problem_fingerprint"]

    if current_status == "healthy":
        if previous_status in {"degraded", "down"}:
            lines = [
                "🟢 사이트 상태가 복구되었습니다.",
                f"이전 상태: {previous_status.upper()}",
                f"복구 시각(UTC): {report['checked_at']}",
            ]
            return "\n".join(lines)
        return None

    if current_status != previous_status or current_fingerprint != previous_fingerprint:
        headline = "🔴 사이트 장애 감지" if current_status == "down" else "🟠 사이트 이상 감지"
        lines = [
            headline,
            f"현재 상태: {current_status.upper()}",
            f"감지 시각(UTC): {report['checked_at']}",
            "",
        ]
        lines.extend(_render_check_message(check) for check in report["checks"] if check["severity"] != "ok")
        return "\n".join(lines)

    return None


def _fingerprint(checks: list[dict[str, Any]]) -> str:
    parts = [
        f"{check['id']}:{check['severity']}:{check['detail_key']}"
        for check in checks
        if check["severity"] != "ok"
    ]
    return "|".join(sorted(parts))


async def _run_single_check(
    client: httpx.AsyncClient,
    check: dict[str, Any],
    *,
    slow_ms: int,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        response = await client.get(check["path"])
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        if response.status_code != check["required_status"]:
            return {
                "id": check["id"],
                "label": check["label"],
                "path": check["path"],
                "severity": "error",
                "status": "failed",
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "detail": f"expected HTTP {check['required_status']}",
                "detail_key": "bad_status",
            }

        if check["kind"] == "json":
            payload = response.json()
            if check["id"] == "health":
                if payload.get("status") != "healthy":
                    return {
                        "id": check["id"],
                        "label": check["label"],
                        "path": check["path"],
                        "severity": "error",
                        "status": "failed",
                        "status_code": response.status_code,
                        "elapsed_ms": elapsed_ms,
                        "detail": "status field is not healthy",
                        "detail_key": "bad_payload",
                    }
            if check["id"] == "blueprint":
                if len(payload.get("authors", [])) < 5 or len(payload.get("ai_roundtable", {}).get("models", [])) < 4:
                    return {
                        "id": check["id"],
                        "label": check["label"],
                        "path": check["path"],
                        "severity": "error",
                        "status": "failed",
                        "status_code": response.status_code,
                        "elapsed_ms": elapsed_ms,
                        "detail": "blueprint payload is incomplete",
                        "detail_key": "bad_payload",
                    }
        else:
            body = response.text
            missing = [marker for marker in check.get("markers", ()) if marker not in body]
            if missing:
                return {
                    "id": check["id"],
                    "label": check["label"],
                    "path": check["path"],
                    "severity": "error",
                    "status": "failed",
                    "status_code": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "detail": f"missing marker: {missing[0]}",
                    "detail_key": "missing_marker",
                }

        if elapsed_ms > slow_ms:
            return {
                "id": check["id"],
                "label": check["label"],
                "path": check["path"],
                "severity": "warn",
                "status": "slow",
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "detail": f"slower than {slow_ms}ms",
                "detail_key": "slow",
            }

        return {
            "id": check["id"],
            "label": check["label"],
            "path": check["path"],
            "severity": "ok",
            "status": "ok",
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "detail": "ok",
            "detail_key": "ok",
        }
    except Exception as exc:
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "id": check["id"],
            "label": check["label"],
            "path": check["path"],
            "severity": "error",
            "status": "failed",
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "detail": str(exc),
            "detail_key": "exception",
        }


async def collect_site_report(
    *,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
    slow_ms: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Collect a current site health report."""
    base_url = (base_url or settings.site_monitor_base_url).rstrip("/")
    timeout_seconds = timeout_seconds or settings.site_monitor_timeout_seconds
    slow_ms = slow_ms or settings.site_monitor_slow_ms

    owned_client = client is None
    if owned_client:
        client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    try:
        checks = []
        for definition in SITE_CHECKS:
            checks.append(await _run_single_check(client, definition, slow_ms=slow_ms))

        error_checks = sum(1 for check in checks if check["severity"] == "error")
        warning_checks = sum(1 for check in checks if check["severity"] == "warn")
        healthy_checks = sum(1 for check in checks if check["severity"] == "ok")
        overall_status = "down" if error_checks else ("degraded" if warning_checks else "healthy")

        report = {
            "checked_at": _utc_now_iso(),
            "base_url": base_url,
            "overall_status": overall_status,
            "healthy_checks": healthy_checks,
            "warning_checks": warning_checks,
            "error_checks": error_checks,
            "check_count": len(checks),
            "problem_fingerprint": _fingerprint(checks),
            "checks": checks,
        }
        return report
    finally:
        if owned_client and client is not None:
            await client.aclose()


async def run_site_monitor_cycle(*, notify: bool = True) -> dict[str, Any]:
    """Collect, persist, and optionally notify on site status changes."""
    report = await collect_site_report()
    previous_state = _load_json(_state_path())
    notification = build_notification_message(previous_state, report)

    _write_json(_report_path(), report)
    _write_json(
        _state_path(),
        {
            "checked_at": report["checked_at"],
            "overall_status": report["overall_status"],
            "problem_fingerprint": report["problem_fingerprint"],
        },
    )

    if notify and notification:
        from app.notifications.telegram_bot import send_notification

        await send_notification(notification)

    return report
