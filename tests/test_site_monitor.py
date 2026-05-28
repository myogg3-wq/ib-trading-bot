import unittest

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.main import create_app
from app.web.site_monitor import _build_next_state, build_notification_message, collect_site_report


class SiteMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_site_report_is_healthy_for_app(self):
        app = create_app(skip_startup=True)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            report = await collect_site_report(client=client, base_url="http://testserver", slow_ms=5000)

        self.assertEqual(report["overall_status"], "healthy")
        self.assertEqual(report["error_checks"], 0)
        self.assertGreaterEqual(report["healthy_checks"], 5)
        self.assertTrue(any(check["id"] == "platform" for check in report["checks"]))

    async def test_collect_site_report_detects_platform_marker_failure(self):
        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/")
        async def home():
            return HTMLResponse("<html><body>Signal Loom <a href='/llms.txt'>llms</a></body></html>")

        @app.get("/platform")
        async def platform():
            return HTMLResponse("<html><body>Signal Loom only</body></html>")

        @app.get("/api/platform/blueprint")
        async def blueprint():
            return {"authors": [{}] * 5, "ai_roundtable": {"models": [{}] * 4}}

        @app.get("/platform-static/platform.js")
        async def platform_js():
            return HTMLResponse("const SUPPORTED_LANGUAGES = []; function requestJson() {}")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            report = await collect_site_report(client=client, base_url="http://testserver", slow_ms=5000)

        self.assertEqual(report["overall_status"], "down")
        failing = next(check for check in report["checks"] if check["id"] == "platform")
        self.assertEqual(failing["severity"], "error")
        self.assertEqual(failing["detail_key"], "missing_marker")

    def test_build_notification_message_for_incident_and_recovery(self):
        incident_report = {
            "overall_status": "down",
            "checked_at": "2026-03-24T00:00:00+00:00",
            "problem_fingerprint": "platform:error:missing_marker",
            "checks": [
                {
                    "id": "platform",
                    "label": "Interactive platform",
                    "severity": "error",
                    "status": "failed",
                    "status_code": 200,
                    "elapsed_ms": 120,
                    "detail": "missing marker: thread-search",
                    "detail_key": "missing_marker",
                }
            ],
        }
        message = build_notification_message({}, incident_report)
        self.assertIn("사이트 장애 감지", message)
        self.assertIn("Interactive platform", message)

        recovery_report = {
            "overall_status": "healthy",
            "checked_at": "2026-03-24T00:05:00+00:00",
            "problem_fingerprint": "",
            "checks": [],
        }
        recovery = build_notification_message(
            {"overall_status": "down", "problem_fingerprint": "platform:error:missing_marker"},
            recovery_report,
        )
        self.assertIn("복구", recovery)

    def test_build_notification_message_suppresses_slow_warning_noise(self):
        degraded_report = {
            "overall_status": "degraded",
            "checked_at": "2026-03-24T00:00:00+00:00",
            "problem_fingerprint": "platform:warn:slow",
            "checks": [
                {
                    "id": "platform",
                    "label": "Interactive platform",
                    "severity": "warn",
                    "status": "slow",
                    "status_code": 200,
                    "elapsed_ms": 2200,
                    "detail": "slower than 1800ms",
                    "detail_key": "slow",
                }
            ],
        }
        self.assertIsNone(build_notification_message({}, degraded_report))

        recovery_report = {
            "overall_status": "healthy",
            "checked_at": "2026-03-24T00:05:00+00:00",
            "problem_fingerprint": "",
            "checks": [],
        }
        self.assertIsNone(
            build_notification_message(
                {"overall_status": "degraded", "problem_fingerprint": "platform:warn:slow"},
                recovery_report,
            )
        )

    def test_degraded_cycle_does_not_forget_active_down_incident(self):
        previous_state = {
            "checked_at": "2026-03-24T00:00:00+00:00",
            "overall_status": "down",
            "problem_fingerprint": "platform:error:missing_marker",
        }
        degraded_report = {
            "overall_status": "degraded",
            "checked_at": "2026-03-24T00:05:00+00:00",
            "problem_fingerprint": "platform:warn:slow",
            "checks": [],
        }

        self.assertIsNone(build_notification_message(previous_state, degraded_report))
        degraded_state = _build_next_state(previous_state, degraded_report)

        self.assertEqual(degraded_state["overall_status"], "degraded")
        self.assertEqual(degraded_state["active_incident_status"], "down")
        self.assertEqual(
            degraded_state["active_incident_fingerprint"],
            "platform:error:missing_marker",
        )

        recovery_report = {
            "overall_status": "healthy",
            "checked_at": "2026-03-24T00:10:00+00:00",
            "problem_fingerprint": "",
            "checks": [],
        }
        recovery = build_notification_message(degraded_state, recovery_report)

        self.assertIn("복구", recovery)
        recovered_state = _build_next_state(degraded_state, recovery_report)
        self.assertNotIn("active_incident_status", recovered_state)


if __name__ == "__main__":
    unittest.main()
