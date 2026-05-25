import os
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app.web.router as platform_router
from app.config import settings
from app.main import create_app
from app.web.auth_store import AuthStore
from app.web.commerce_store import CommerceStore
from app.web.community_store import CommunityStore
from app.web.social_oauth import write_signed_payload


TEST_STORE_PATH = Path(__file__).resolve().parent / ".tmp_platform_community.json"
TEST_AUTH_STORE_PATH = Path(__file__).resolve().parent / ".tmp_platform_auth.json"
TEST_COMMERCE_STORE_PATH = Path(__file__).resolve().parent / ".tmp_platform_commerce.json"
os.environ["PLATFORM_COMMUNITY_STORE_PATH"] = str(TEST_STORE_PATH)
os.environ["PLATFORM_AUTH_STORE_PATH"] = str(TEST_AUTH_STORE_PATH)
os.environ["PLATFORM_COMMERCE_STORE_PATH"] = str(TEST_COMMERCE_STORE_PATH)
os.environ["PLATFORM_ADMIN_TOKEN"] = "test-admin-token"
os.environ["PLATFORM_BANK_NAME"] = "테스트은행"
os.environ["PLATFORM_BANK_ACCOUNT"] = "110-123-456789"
os.environ["PLATFORM_BANK_HOLDER"] = "Signal Loom Test"
os.environ["PLATFORM_DISABLE_LIVE_NEWS"] = "1"
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "692156939420-9oofa171lfcipvepifaq34demo5bpmfd.apps.googleusercontent.com"
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-google-secret"


def _configure_platform_test_runtime() -> None:
    """Reset import-time platform globals so full-suite runs stay isolated."""
    settings.google_oauth_client_id = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    settings.google_oauth_client_secret = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
    settings.platform_oauth_state_secret = "test-platform-oauth-secret"
    settings.platform_public_base_url = ""

    platform_router.auth_store = AuthStore(TEST_AUTH_STORE_PATH)
    platform_router.commerce_store = CommerceStore(TEST_COMMERCE_STORE_PATH)
    platform_router.community_store = CommunityStore(TEST_STORE_PATH)


class WebPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _configure_platform_test_runtime()
        for path in (TEST_STORE_PATH, TEST_AUTH_STORE_PATH, TEST_COMMERCE_STORE_PATH):
            if path.exists():
                path.unlink()
        cls.client = TestClient(create_app(skip_startup=True))

    @classmethod
    def tearDownClass(cls):
        for path in (TEST_STORE_PATH, TEST_AUTH_STORE_PATH, TEST_COMMERCE_STORE_PATH):
            if path.exists():
                path.unlink()

    def setUp(self):
        for path in (TEST_STORE_PATH, TEST_AUTH_STORE_PATH, TEST_COMMERCE_STORE_PATH):
            if path.exists():
                path.unlink()
        self.client.cookies.clear()

    def _required_agreements(self, **overrides):
        payload = {
            "terms_required": True,
            "privacy_required": True,
            "investment_notice_required": True,
            "marketing_optional": False,
        }
        payload.update(overrides)
        return payload

    def _register_payload(self, name, email, password="supersecret123", **agreement_overrides):
        return {
            "name": name,
            "email": email,
            "password": password,
            "agreements": self._required_agreements(**agreement_overrides),
        }

    def test_platform_blueprint_contains_social_data(self):
        response = self.client.get("/api/platform/blueprint")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["ideas"]), 30)
        self.assertGreaterEqual(len(payload["threads"]), 800)
        self.assertGreaterEqual(len(payload["modules"]), 10)
        self.assertGreaterEqual(len(payload["authors"]), 9)
        self.assertIn("performance", payload["authors"][0])
        self.assertIn("total_return", payload["authors"][0]["performance"])
        self.assertIn("ai_roundtable", payload)
        self.assertEqual(len(payload["ai_roundtable"]["models"]), 4)
        self.assertIn("world_news", payload)
        self.assertGreaterEqual(len(payload["world_news"]), 3)
        self.assertGreaterEqual(len(payload["world_news"][0]["views"]), 3)
        self.assertEqual(payload["creator"]["stats"][1]["value"], str(len(payload["threads"])))

        dated_threads = [
            datetime.fromisoformat(thread["created_at"])
            for thread in payload["threads"]
            if thread.get("created_at")
        ]
        self.assertGreaterEqual(len(dated_threads), 800)
        self.assertGreaterEqual((max(dated_threads) - min(dated_threads)).days, 720)

    def test_platform_page_serves_html(self):
        response = self.client.get("/platform")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-robots-tag"], "noindex, follow")
        self.assertIn("Signal Loom", response.text)
        self.assertIn('content="noindex,follow"', response.text)
        self.assertIn("/platform-static/platform.js", response.text)
        self.assertIn("language-select", response.text)
        self.assertIn("hero-feature", response.text)
        self.assertIn("signal-board", response.text)
        self.assertIn("quick-guide-grid", response.text)
        self.assertIn("browse-grid", response.text)
        self.assertIn("ai-roundtable-form", response.text)
        self.assertIn("ai-roundtable-grid", response.text)
        self.assertIn("community-stage-title", response.text)
        self.assertIn("composer-form", response.text)
        self.assertIn("composer-shell", response.text)
        self.assertIn("following-card", response.text)
        self.assertIn("leaderboard-card", response.text)
        self.assertIn("leaderboard-list", response.text)
        self.assertIn("contribution-type-row", response.text)
        self.assertIn("monetization-card", response.text)
        self.assertIn("thread-search", response.text)
        self.assertIn("thread-feed", response.text)
        self.assertIn("active-signals-title", response.text)

    def test_platform_page_uses_accept_language_for_initial_shell(self):
        response = self.client.get(
            "/platform",
            headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('lang="ko"', response.text)
        self.assertIn('data-platform-default-language="ko"', response.text)
        self.assertIn("라이브 피드를 불러오는 중입니다", response.text)
        self.assertIn("계정", response.text)

    def test_root_page_serves_crawlable_seo_landing(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Signals fade. Recorded conviction stays.", response.text)
        self.assertIn("application/ld+json", response.text)
        self.assertIn("seo-language-select", response.text)
        self.assertIn("How to use this site", response.text)
        self.assertIn("/llms.txt", response.text)
        self.assertIn("/traders/signal-loom", response.text)
        self.assertIn("/signals/nvda-buy", response.text)

    def test_root_page_supports_korean_rendering(self):
        response = self.client.get("/", params={"lang": "ko"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "ko")
        self.assertIn('lang="ko"', response.text)
        self.assertIn("신호는 지나가도, 판단 기록은 남습니다.", response.text)
        self.assertIn("언어", response.text)
        self.assertIn('rel="canonical" href="http://testserver/?lang=ko"', response.text)
        self.assertIn('hreflang="ko" href="http://testserver/?lang=ko"', response.text)
        self.assertIn('hreflang="x-default" href="http://testserver/"', response.text)

    def test_root_page_supports_japanese_rendering(self):
        response = self.client.get("/", params={"lang": "ja"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "ja")
        self.assertIn('lang="ja"', response.text)
        self.assertIn("シグナルは過ぎても、判断の記録は残ります。", response.text)
        self.assertIn("ライブアプリを開く", response.text)
        self.assertIn("このサイトの見方", response.text)
        self.assertIn("最初はこの3つだけ見れば十分です。", response.text)
        self.assertIn('rel="canonical" href="http://testserver/?lang=ja"', response.text)
        self.assertIn('hreflang="ja" href="http://testserver/?lang=ja"', response.text)
        self.assertIn('"availableLanguage"', response.text)

    def test_root_page_supports_spanish_rendering(self):
        response = self.client.get("/", params={"lang": "es"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "es")
        self.assertIn('lang="es"', response.text)
        self.assertIn("Las señales pasan, el criterio registrado queda.", response.text)
        self.assertIn("Cómo usar este sitio", response.text)
        self.assertIn("Solo necesitas estos tres pasos para empezar.", response.text)
        self.assertIn('rel="canonical" href="http://testserver/?lang=es"', response.text)
        self.assertIn('hreflang="es" href="http://testserver/?lang=es"', response.text)

    def test_root_page_uses_accept_language_without_query_param(self):
        response = self.client.get(
            "/",
            headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["vary"], "Accept-Language")
        self.assertIn('lang="ko"', response.text)
        self.assertIn("신호는 지나가도, 판단 기록은 남습니다.", response.text)
        self.assertIn("언어", response.text)

    def test_trader_profile_page_serves_structured_profile(self):
        response = self.client.get("/traders/signal-loom")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "en")
        self.assertIn("AI Strategy Profile", response.text)
        self.assertIn("Loom Core", response.text)
        self.assertIn("Core AI desk for the site", response.text)
        self.assertIn("Strategy profile", response.text)
        self.assertIn('"@type": "ProfilePage"', response.text)

    def test_trader_profile_page_supports_spanish_rendering(self):
        response = self.client.get("/traders/signal-loom", params={"lang": "es"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "es")
        self.assertIn("Perfil de estrategia IA", response.text)
        self.assertIn("Mesas IA líderes", response.text)
        self.assertIn("Perfil de estrategia", response.text)
        self.assertIn('"availableLanguage"', response.text)
        self.assertIn('"alternateName": "@loomcore"', response.text)

    def test_trader_profile_page_uses_generated_japanese_profile_copy(self):
        response = self.client.get("/traders/signal-loom", params={"lang": "ja"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "ja")
        self.assertIn("AI戦略プロフィール", response.text)
        self.assertIn("Loom CoreはSignal Loomで公開AI戦略ノートを投稿しています。", response.text)
        self.assertIn("Loom Coreの戦略プロフィール", response.text)
        self.assertIn("このページでは、このデスクが公開投稿で何を重視するのかを要約します。", response.text)
        self.assertNotIn("Core AI desk for the site", response.text)

    def test_signal_page_serves_structured_article(self):
        response = self.client.get("/signals/nvda-buy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "en")
        self.assertIn("NVDA", response.text)
        self.assertIn("Signal Loom publishes this page as a documented market note", response.text)
        self.assertIn("Why this AI posted", response.text)
        self.assertIn("<strong>NVDA</strong>Ticker", response.text)
        self.assertIn('"@type": "Article"', response.text)
        self.assertIn('"isPartOf"', response.text)

    def test_signal_page_uses_generated_japanese_thread_copy(self):
        response = self.client.get("/signals/nvda-buy", params={"lang": "ja"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "ja")
        self.assertIn("NVDAの買いシグナルがSignal Loomに公開されました。", response.text)
        self.assertIn("このページではエントリー価格とリスク水準を確認できます。", response.text)
        self.assertIn("エントリー", response.text)
        self.assertIn("リスク", response.text)
        self.assertNotIn("NVDA just triggered a live buy post.", response.text)

    def test_signal_page_uses_localized_spanish_labels_in_html_and_json_ld(self):
        response = self.client.get("/signals/nvda-buy", params={"lang": "es"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "es")
        self.assertIn("<strong>NVDA</strong>Símbolo", response.text)
        self.assertIn("<strong>$876.20</strong><span>Entrada</span>", response.text)
        self.assertIn('"articleSection": "Señal de compra"', response.text)

    def test_trader_profile_page_uses_localized_french_focus_label(self):
        response = self.client.get("/traders/signal-loom", params={"lang": "fr"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-language"], "fr")
        self.assertIn("<p class=\"section-kicker\">Profil de stratégie</p>", response.text)
        self.assertIn("Cette page résume ce que ce desk privilégie", response.text)
        self.assertNotIn(">Focus<", response.text)

    def test_robots_txt_exposes_ai_crawler_rules(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("User-agent: OAI-SearchBot", response.text)
        self.assertIn("User-agent: GPTBot", response.text)
        self.assertIn("Disallow: /api/", response.text)
        self.assertIn("/sitemap.xml", response.text)

    def test_llms_endpoints_publish_machine_readable_site_summary(self):
        compact = self.client.get("/llms.txt")
        full = self.client.get("/llms-full.txt")

        self.assertEqual(compact.status_code, 200)
        self.assertEqual(full.status_code, 200)
        self.assertIn("# Signal Loom", compact.text)
        self.assertIn("public market research platform", compact.text)
        self.assertIn("/traders/signal-loom", compact.text)
        self.assertIn("Best citation summary", full.text)
        self.assertIn("/signals/crwd-sell", full.text)

        localized = self.client.get("/llms.txt", params={"lang": "ko"})
        self.assertEqual(localized.headers["content-language"], "ko")
        self.assertEqual(localized.headers["vary"], "Accept-Language")
        self.assertIn("http://testserver/?lang=ko", localized.text)
        self.assertIn("/traders/signal-loom?lang=ko", localized.text)
        self.assertIn("/signals/nvda-buy?lang=ko", localized.text)
        self.assertIn("## 핵심 정보", localized.text)
        self.assertIn("http://testserver/sitemap.xml", localized.text)
        self.assertNotIn("http://testserver/sitemap.xml?lang=ko", localized.text)

        japanese = self.client.get("/llms.txt", params={"lang": "ja"})
        self.assertEqual(japanese.headers["content-language"], "ja")
        self.assertIn("## 主要情報", japanese.text)
        self.assertIn("http://testserver/?lang=ja", japanese.text)
        self.assertIn("/signals/nvda-buy?lang=ja", japanese.text)
        self.assertIn("ウォッチシグナル", japanese.text)
        self.assertNotIn(" watch:", japanese.text)

        spanish = self.client.get("/llms.txt", params={"lang": "es"})
        self.assertEqual(spanish.headers["content-language"], "es")
        self.assertIn("plataforma pública de investigación de mercado", spanish.text)
        self.assertIn("http://testserver/?lang=es", spanish.text)
        self.assertIn("Señal de compra", spanish.text)

        chinese = self.client.get("/llms.txt", params={"lang": "zh-CN"})
        self.assertEqual(chinese.headers["content-language"], "zh-CN")
        self.assertIn("## 关键信息", chinese.text)
        self.assertIn("观察信号", chinese.text)
        self.assertNotIn(" buy:", chinese.text)

    def test_sitemap_xml_lists_canonical_pages(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', response.text)
        self.assertIn("<urlset", response.text)
        self.assertIn('xmlns:xhtml="http://www.w3.org/1999/xhtml"', response.text)
        self.assertIn('hreflang="ko"', response.text)
        self.assertIn("/?lang=ko", response.text)
        self.assertIn("/llms.txt", response.text)
        self.assertIn("/traders/hana-macro", response.text)
        self.assertIn("/signals/nvda-sell", response.text)

    def test_platform_community_api_returns_empty_state(self):
        response = self.client.get("/api/platform/community", params={"viewer_id": "viewer-a"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["posts"], [])
        self.assertEqual(payload["following_ids"], [])
        self.assertIn("signal-loom", payload["follower_counts"])

    def test_platform_can_create_shared_post(self):
        response = self.client.post(
            "/api/platform/posts",
            json={
                "author_id": "signal-loom",
                "kind": "buy",
                "contribution_type": "evidence",
                "ticker": "AAPL",
                "company": "Apple",
                "headline": "AAPL cleared the desk and opened a fresh entry thread.",
                "summary": "Momentum tightened, the level was simple, and the watch note converted into a live post.",
                "tags": ["Mega cap", "Momentum"],
                "levels": ["$198.40", "$194.10", "$205.00"],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["thread"]["ticker"], "AAPL")
        self.assertEqual(payload["thread"]["author_id"], "signal-loom")
        self.assertEqual(payload["thread"]["contribution_type"], "evidence")
        self.assertEqual(payload["thread"]["copy"]["source_language"], "en")
        self.assertIn("en", payload["thread"]["copy"])
        self.assertNotIn("ko", payload["thread"]["copy"])

        community = self.client.get("/api/platform/community", params={"viewer_id": "viewer-a"}).json()
        self.assertEqual(len(community["posts"]), 1)
        self.assertEqual(community["posts"][0]["ticker"], "AAPL")

    def test_platform_can_create_translation_ready_korean_post(self):
        response = self.client.post(
            "/api/platform/posts",
            json={
                "author_id": "hana-macro",
                "kind": "watch",
                "contribution_type": "question",
                "ticker": "MSFT",
                "company": "Microsoft",
                "headline": "MSFT는 아직 안 삽니다. 더 지켜봅니다.",
                "summary": "지금은 바로 들어가지 않고, 다시 올라오는지 먼저 확인합니다.",
                "tags": ["관망", "클라우드"],
                "levels": ["$412.50", "$416.10", "Watching"],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["thread"]["copy"]["source_language"], "ko")
        self.assertIn("ko", payload["thread"]["copy"])
        self.assertNotIn("en", payload["thread"]["copy"])

    def test_platform_follow_api_requires_sign_in(self):
        response = self.client.post(
            "/api/platform/follows",
            json={
                "viewer_id": "viewer-a",
                "author_id": "signal-loom",
                "following": True,
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_platform_follow_api_requires_follow_unlock(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Follow User", "follow@example.com"),
        )

        response = self.client.post(
            "/api/platform/follows",
            json={
                "viewer_id": "viewer-a",
                "author_id": "signal-loom",
                "following": True,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_follow_pass_purchase_persists_on_account(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Follow Pass User", "follow-pass@example.com"),
        )

        response = self.client.post(
            "/api/platform/commerce/products/purchase",
            json={"product_id": "follow-pass"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["account"]
        self.assertTrue(payload["follow_pass_active"])
        self.assertEqual(payload["credits_balance"], 20)

        session = self.client.get("/api/platform/account").json()["account"]
        self.assertTrue(session["follow_pass_active"])
        self.assertEqual(session["credits_balance"], 20)

    def test_platform_follow_api_updates_state_after_follow_unlock(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Follow Ready", "follow-ready@example.com"),
        )
        self.client.post(
            "/api/platform/commerce/products/purchase",
            json={"product_id": "follow-pass"},
        )

        response = self.client.post(
            "/api/platform/follows",
            json={
                "viewer_id": "viewer-a",
                "author_id": "signal-loom",
                "following": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["following_ids"], ["signal-loom"])
        self.assertGreater(payload["follower_counts"]["signal-loom"], 18400)

        community = self.client.get("/api/platform/community", params={"viewer_id": "viewer-a"}).json()
        self.assertEqual(community["following_ids"], ["signal-loom"])

    def test_platform_static_assets_serve(self):
        response = self.client.get("/platform-static/platform.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("--bg", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")

    def test_platform_i18n_asset_serves(self):
        response = self.client.get("/platform-static/platform-i18n.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SUPPORTED_LANGUAGES", response.text)

    def test_platform_js_contains_paid_rank_author_focus(self):
        response = self.client.get("/platform-static/platform.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("data-author-rank-focus", response.text)
        self.assertIn('handleCommerceAction("desk-pass"', response.text)

    def test_platform_js_contains_paid_follow_cta_in_threads(self):
        response = self.client.get("/platform-static/platform.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("thread-follow-row", response.text)
        self.assertIn('uiText("threadFollowUnlockLabel"', response.text)

    def test_platform_js_contains_admin_dashboard_entry(self):
        response = self.client.get("/platform-static/platform.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("data-admin-access-form", response.text)
        self.assertIn("/api/platform/admin/session", response.text)
        self.assertNotIn("/platform/admin?token=", response.text)

    def test_platform_favicon_serves(self):
        response = self.client.get("/platform-static/platform-favicon.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<svg", response.text)

    def test_platform_account_defaults_to_signed_out(self):
        response = self.client.get("/api/platform/account")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["authenticated"])
        self.assertIsNone(payload["user"])
        self.assertIsNone(payload["account"])
        self.assertIsNone(payload["identity"])
        self.assertIn("catalog", payload)
        self.assertEqual(len(payload["catalog"]["credit_packs"]), 3)
        self.assertEqual(len(payload["catalog"]["payment_methods"]), 2)
        self.assertIn("oauth_providers", payload)
        self.assertEqual([item["provider"] for item in payload["oauth_providers"]], ["google"])
        self.assertTrue(all(item["enabled"] is True for item in payload["oauth_providers"]))
        self.assertEqual(
            payload["oauth_providers"][0]["client_id"],
            "692156939420-9oofa171lfcipvepifaq34demo5bpmfd.apps.googleusercontent.com",
        )

    def test_register_returns_session_and_starter_credits(self):
        response = self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Test User", "test@example.com"),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["email"], "test@example.com")
        self.assertEqual(payload["account"]["credits_balance"], 24)
        self.assertEqual(payload["account"]["desk_passes"], [])
        self.assertEqual(payload["identity"]["provider"], "local")
        self.assertEqual(payload["identity"]["linked_providers"], ["local"])
        self.assertTrue(payload["identity"]["required_agreements_completed"])
        self.assertTrue(payload["identity"]["has_local_password"])
        self.assertFalse(payload["identity"]["social_only"])
        self.assertEqual(payload["identity"]["agreement_version"], "2026-03-28")

        session = self.client.get("/api/platform/account").json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["account"]["credits_balance"], 24)
        self.assertEqual(session["identity"]["provider"], "local")
        self.assertEqual(len(session["catalog"]["credit_packs"]), 3)

    def test_register_requires_required_agreements(self):
        response = self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Missing Agreements", "missing@example.com", terms_required=False),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("required terms", response.json()["detail"].lower())

    def test_social_complete_creates_account_and_session(self):
        response = self.client.post(
            "/api/platform/auth/social/complete",
            json={
                "provider": "google",
                "subject": "google-user-1",
                "name": "Social User",
                "email": "social@example.com",
                "agreements": self._required_agreements(),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["provider"], "google")
        self.assertEqual(payload["user"]["email"], "social@example.com")
        self.assertEqual(payload["identity"]["provider"], "google")
        self.assertEqual(payload["identity"]["linked_providers"], ["google"])
        self.assertTrue(payload["identity"]["required_agreements_completed"])
        self.assertFalse(payload["identity"]["has_local_password"])
        self.assertTrue(payload["identity"]["social_only"])

        session = self.client.get("/api/platform/account").json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["user"]["provider"], "google")
        self.assertEqual(session["identity"]["provider"], "google")

    def test_oauth_start_redirects_to_google_when_provider_is_configured(self):
        response = self.client.get("/api/platform/auth/oauth/google/start?lang=ko", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertIn("accounts.google.com", response.headers["location"])
        self.assertIn("redirect_uri=", response.headers["location"])

    def test_oauth_start_supports_twitter_alias(self):
        response = self.client.get("/api/platform/auth/oauth/twitter/start?lang=ko", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/platform?lang=ko", response.headers["location"])
        self.assertIn("Twitter", response.headers["location"])

    def test_social_complete_can_link_existing_account(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Linked User", "linked@example.com"),
        )
        self.client.post("/api/platform/auth/logout", json={})

        response = self.client.post(
            "/api/platform/auth/social/complete",
            json={
                "provider": "apple",
                "subject": "apple-user-1",
                "name": "Linked User",
                "email": "linked@example.com",
                "agreements": self._required_agreements(),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["email"], "linked@example.com")
        self.assertEqual(payload["identity"]["linked_providers"], ["apple", "local"])

    def test_social_only_account_rejects_local_password_login(self):
        self.client.post(
            "/api/platform/auth/social/complete",
            json={
                "provider": "google",
                "subject": "google-user-2",
                "name": "Social Only",
                "email": "social-only@example.com",
                "agreements": self._required_agreements(),
            },
        )
        self.client.post("/api/platform/auth/logout", json={})

        response = self.client.post(
            "/api/platform/auth/login",
            json={"email": "social-only@example.com", "password": "password123"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("social sign-in", response.json()["detail"].lower())

    def test_oauth_start_redirect_sets_flow_cookie(self):
        with patch("app.web.router.build_authorization_redirect", return_value=("https://accounts.example.test/start", "signed-flow")):
            response = self.client.get("/api/platform/auth/oauth/google/start?lang=ko", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://accounts.example.test/start")
        self.assertIn("platform_oauth_flow=", response.headers.get("set-cookie", ""))

    def test_oauth_callback_existing_account_sets_session(self):
        self.client.post(
            "/api/platform/auth/social/complete",
            json={
                "provider": "google",
                "subject": "google-user-3",
                "name": "Existing Social User",
                "email": "existing-social@example.com",
                "agreements": self._required_agreements(),
            },
        )
        self.client.post("/api/platform/auth/logout", json={})
        self.client.cookies.set(
            "platform_oauth_flow",
            write_signed_payload({
                "provider": "google",
                "state": "state-123",
                "lang": "ko",
                "created_at": 9999999999,
            }),
        )
        with patch(
            "app.web.router.complete_callback",
            new=AsyncMock(return_value={
                "provider": "google",
                "subject": "google-user-3",
                "email": "existing-social@example.com",
                "name": "Existing Social User",
            }),
        ):
            response = self.client.get(
                "/api/platform/auth/oauth/google/callback?code=ok&state=state-123",
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://testserver/platform?lang=ko")
        session = self.client.get("/api/platform/account").json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["user"]["email"], "existing-social@example.com")

    def test_oauth_callback_new_user_sets_pending_cookie(self):
        self.client.cookies.set(
            "platform_oauth_flow",
            write_signed_payload({
                "provider": "apple",
                "state": "state-456",
                "lang": "ko",
                "created_at": 9999999999,
            }),
        )
        with patch(
            "app.web.router.complete_callback",
            new=AsyncMock(return_value={
                "provider": "apple",
                "subject": "apple-user-1",
                "email": "",
                "name": "Apple Starter",
            }),
        ):
            response = self.client.get(
                "/api/platform/auth/oauth/apple/callback?code=ok&state=state-456",
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("auth=complete-social", response.headers["location"])
        pending = self.client.get("/api/platform/auth/social/pending").json()["pending"]
        self.assertEqual(pending["provider"], "apple")
        self.assertEqual(pending["subject"], "apple-user-1")
        self.assertEqual(pending["name"], "Apple Starter")

    def test_oauth_callback_post_supports_apple_form_post(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Apple User", "apple-user@example.com"),
        )
        self.client.post("/api/platform/auth/logout", json={})
        self.client.cookies.set(
            "platform_oauth_flow",
            write_signed_payload({
                "provider": "apple",
                "state": "apple-state-1",
                "lang": "ko",
                "created_at": 9999999999,
            }),
        )
        with patch(
            "app.web.router.complete_callback",
            new=AsyncMock(return_value={
                "provider": "apple",
                "subject": "apple-user-2",
                "email": "apple-user@example.com",
                "name": "Apple User",
            }),
        ):
            response = self.client.post(
                "/api/platform/auth/oauth/apple/callback",
                data={"code": "ok", "state": "apple-state-1"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://testserver/platform?lang=ko")
        session = self.client.get("/api/platform/account").json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["user"]["provider"], "apple")

    def test_social_complete_consumes_pending_cookie(self):
        self.client.cookies.set(
            "platform_social_pending",
            write_signed_payload({
                "provider": "x",
                "subject": "x-user-1",
                "email": "x-user@example.com",
                "name": "X User",
                "created_at": 9999999999,
            }),
        )
        response = self.client.post(
            "/api/platform/auth/social/complete",
            json={
                "provider": "",
                "subject": "",
                "name": "X User",
                "email": "x-user@example.com",
                "agreements": self._required_agreements(),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["identity"]["provider"], "x")
        self.assertEqual(payload["identity"]["linked_providers"], ["x"])
        self.assertIsNone(self.client.get("/api/platform/auth/social/pending").json()["pending"])

    def test_google_credential_login_existing_account_sets_session(self):
        self.client.post(
            "/api/platform/auth/social/complete",
            json={
                "provider": "google",
                "subject": "google-existing-1",
                "name": "Google Existing",
                "email": "google-existing@example.com",
                "agreements": self._required_agreements(),
            },
        )
        self.client.post("/api/platform/auth/logout", json={})

        with patch(
            "app.web.router.verify_google_credential",
            new=AsyncMock(
                return_value={
                    "provider": "google",
                    "subject": "google-existing-1",
                    "email": "google-existing@example.com",
                    "name": "Google Existing",
                }
            ),
        ):
            response = self.client.post(
                "/api/platform/auth/google/credential",
                json={"credential": "test-google-id-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["email"], "google-existing@example.com")
        self.assertEqual(payload["identity"]["provider"], "google")

    def test_google_credential_login_new_user_returns_pending_social_completion(self):
        with patch(
            "app.web.router.verify_google_credential",
            new=AsyncMock(
                return_value={
                    "provider": "google",
                    "subject": "google-new-1",
                    "email": "google-new@example.com",
                    "name": "Google New",
                }
            ),
        ):
            response = self.client.post(
                "/api/platform/auth/google/credential",
                json={"credential": "test-google-id-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["authenticated"])
        self.assertTrue(payload["needs_social_completion"])
        self.assertEqual(payload["pending"]["provider"], "google")
        pending = self.client.get("/api/platform/auth/social/pending").json()["pending"]
        self.assertEqual(pending["provider"], "google")
        self.assertEqual(pending["subject"], "google-new-1")

    def test_legal_pages_render(self):
        for path, needles in (
            ("/legal/terms?lang=ko", ("회원 이용약관", "크레딧과 유료 상품", "서비스 변경")),
            ("/legal/privacy?lang=ko", ("개인정보 수집 및 이용", "SNS 로그인 정보", "고지와 변경")),
            ("/legal/investment-notice?lang=ko", ("투자 콘텐츠 유의사항", "자동 매매 지시 아님", "지연 및 한계")),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            for needle in needles:
                self.assertIn(needle, response.text)

    def test_unlock_sections_deducts_credits_and_persists(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Unlock User", "unlock@example.com"),
        )

        response = self.client.post(
            "/api/platform/commerce/sections/unlock",
            json={
                "ticker": "NVDA",
                "section_ids": ["model-briefs", "entry-window"],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["account"]["credits_balance"], 16)
        self.assertEqual(
            sorted(payload["account"]["unlocked_sections"]["NVDA"]),
            ["entry-window", "model-briefs"],
        )

        session = self.client.get("/api/platform/account").json()
        self.assertEqual(session["account"]["credits_balance"], 16)
        self.assertEqual(
            sorted(session["account"]["unlocked_sections"]["NVDA"]),
            ["entry-window", "model-briefs"],
        )

    def test_purchase_products_and_alert_preferences_persist(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Commerce User", "commerce@example.com"),
        )

        membership = self.client.post(
            "/api/platform/commerce/products/purchase",
            json={"product_id": "membership"},
        )
        self.assertEqual(membership.status_code, 200)
        membership_payload = membership.json()
        self.assertTrue(membership_payload["account"]["membership_active"])
        self.assertGreaterEqual(membership_payload["account"]["credits_balance"], 42)

        desk_pass = self.client.post(
            "/api/platform/commerce/products/purchase",
            json={"product_id": "desk-pass", "author_id": "signal-loom"},
        )
        self.assertEqual(desk_pass.status_code, 200)
        self.assertIn("signal-loom", desk_pass.json()["account"]["desk_passes"])

        alerts = self.client.post(
            "/api/platform/commerce/products/purchase",
            json={"product_id": "alerts"},
        )
        self.assertEqual(alerts.status_code, 200)
        self.assertTrue(alerts.json()["account"]["alerts_active"])

        prefs = self.client.post(
            "/api/platform/alerts/preferences",
            json={"preferences": {"buy": False, "watch": True, "sell": False, "research": True}},
        )
        self.assertEqual(prefs.status_code, 200)
        prefs_payload = prefs.json()
        self.assertEqual(
            prefs_payload["account"]["alert_preferences"],
            {"buy": False, "watch": True, "sell": False, "research": True},
        )

        session = self.client.get("/api/platform/account").json()["account"]
        self.assertTrue(session["membership_active"])
        self.assertTrue(session["alerts_active"])
        self.assertIn("signal-loom", session["desk_passes"])
        self.assertEqual(
            session["alert_preferences"],
            {"buy": False, "watch": True, "sell": False, "research": True},
        )

    def test_recent_rank_purchase_persists_on_account(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Ranking User", "ranking@example.com"),
        )

        response = self.client.post(
            "/api/platform/commerce/products/purchase",
            json={"product_id": "recent-rank"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["account"]
        self.assertTrue(payload["recent_rank_active"])
        self.assertEqual(payload["credits_balance"], 21)

        session = self.client.get("/api/platform/account").json()["account"]
        self.assertTrue(session["recent_rank_active"])
        self.assertEqual(session["credits_balance"], 21)

    def test_create_payment_request_persists_on_account(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Wallet User", "wallet@example.com"),
        )

        response = self.client.post(
            "/api/platform/commerce/payment-requests",
            json={
                "pack_id": "plus",
                "method": "bank-transfer",
                "depositor_name": "Hong Gil Dong",
                "note": "evening transfer",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["account"]["credits_balance"], 24)
        self.assertEqual(len(payload["account"]["payment_requests"]), 1)
        request = payload["account"]["payment_requests"][0]
        self.assertEqual(request["pack_id"], "plus")
        self.assertEqual(request["method"], "bank-transfer")
        self.assertEqual(request["status"], "pending")
        self.assertEqual(request["amount_krw"], 8900)
        self.assertEqual(request["depositor_name"], "Hong Gil Dong")
        self.assertTrue(request["reference"])

        session = self.client.get("/api/platform/account").json()
        self.assertEqual(len(session["account"]["payment_requests"]), 1)
        self.assertEqual(session["account"]["payment_requests"][0]["pack_id"], "plus")

    def test_admin_payment_request_listing_requires_token(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Admin Target", "admin-target@example.com"),
        )
        self.client.post(
            "/api/platform/commerce/payment-requests",
            json={
                "pack_id": "starter",
                "method": "bank-transfer",
                "depositor_name": "Kim Tester",
                "note": "morning transfer",
            },
        )

        denied = self.client.get("/api/platform/admin/payment-requests")
        self.assertEqual(denied.status_code, 403)

        allowed = self.client.get(
            "/api/platform/admin/payment-requests",
            headers={"x-platform-admin-token": "test-admin-token"},
        )
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.json()
        self.assertEqual(len(payload["requests"]), 1)
        self.assertEqual(payload["requests"][0]["user"]["email"], "admin-target@example.com")
        self.assertEqual(payload["requests"][0]["status"], "pending")

    def test_admin_overview_returns_authors_members_and_payments(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Overview User", "overview@example.com"),
        )
        self.client.post(
            "/api/platform/commerce/payment-requests",
            json={
                "pack_id": "starter",
                "method": "bank-transfer",
                "depositor_name": "Overview Tester",
                "note": "overview transfer",
            },
        )
        response = self.client.get("/api/platform/admin/overview", headers={"x-platform-admin-token": "test-admin-token"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("authors", payload)
        self.assertIn("members", payload)
        self.assertIn("payment_requests", payload)
        self.assertGreaterEqual(payload["summary"]["ai_desks"], 5)
        self.assertEqual(payload["summary"]["members"], 1)
        self.assertEqual(payload["summary"]["pending_payments"], 1)
        self.assertEqual(payload["members"][0]["email"], "overview@example.com")

    def test_admin_dashboard_renders_after_session_token_exchange(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Dashboard User", "dashboard@example.com"),
        )

        denied = self.client.get("/platform/admin?token=test-admin-token")
        self.assertEqual(denied.status_code, 403)

        session = self.client.post("/api/platform/admin/session", json={"token": "test-admin-token"})
        self.assertEqual(session.status_code, 200)

        response = self.client.get("/platform/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Admin dashboard", response.text)
        self.assertIn("AI desks", response.text)
        self.assertIn("Members", response.text)
        self.assertIn("dashboard@example.com", response.text)

    def test_admin_can_approve_payment_request_and_grant_credits(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Approval User", "approval@example.com"),
        )
        request_response = self.client.post(
            "/api/platform/commerce/payment-requests",
            json={
                "pack_id": "plus",
                "method": "bank-transfer",
                "depositor_name": "Park Approval",
                "note": "wire sent",
            },
        )
        request_id = request_response.json()["account"]["payment_requests"][0]["id"]

        approve = self.client.post(
            f"/api/platform/admin/payment-requests/{request_id}/approve",
            headers={"x-platform-admin-token": "test-admin-token"},
            json={"note": "confirmed manually"},
        )
        self.assertEqual(approve.status_code, 200)
        payload = approve.json()
        self.assertEqual(payload["request"]["status"], "approved")
        self.assertEqual(payload["request"]["review_note"], "confirmed manually")
        self.assertEqual(payload["account"]["credits_balance"], 104)

        session = self.client.get("/api/platform/account").json()["account"]
        self.assertEqual(session["credits_balance"], 104)
        self.assertEqual(session["payment_requests"][0]["status"], "approved")

    def test_admin_can_reject_payment_request_without_granting_credits(self):
        self.client.post(
            "/api/platform/auth/register",
            json=self._register_payload("Reject User", "reject@example.com"),
        )
        request_response = self.client.post(
            "/api/platform/commerce/payment-requests",
            json={
                "pack_id": "starter",
                "method": "manual-card-request",
                "depositor_name": "",
                "note": "card link requested",
            },
        )
        request_id = request_response.json()["account"]["payment_requests"][0]["id"]

        reject = self.client.post(
            f"/api/platform/admin/payment-requests/{request_id}/reject",
            headers={"x-platform-admin-token": "test-admin-token"},
            json={"note": "could not verify"},
        )
        self.assertEqual(reject.status_code, 200)
        payload = reject.json()
        self.assertEqual(payload["request"]["status"], "rejected")
        self.assertEqual(payload["account"]["credits_balance"], 24)

        session = self.client.get("/api/platform/account").json()["account"]
        self.assertEqual(session["credits_balance"], 24)
        self.assertEqual(session["payment_requests"][0]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
