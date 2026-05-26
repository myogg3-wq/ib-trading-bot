"""Routes for the compliant monetization web platform."""

from __future__ import annotations

import hashlib
from html import escape
import os
from pathlib import Path
import time
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel

from app.web.auth_store import auth_store
from app.web.commerce_store import commerce_store
from app.web.community_store import community_store
from app.web.data import AUTHORS, build_platform_blueprint
from app.web.language import language_label, normalize_language, request_language
from app.web.social_oauth import (
    FLOW_COOKIE_MAX_AGE_SECONDS,
    PENDING_COOKIE_MAX_AGE_SECONDS,
    SocialOAuthError,
    build_authorization_redirect,
    complete_callback,
    verify_google_credential,
    read_signed_payload,
    social_provider_catalog,
    social_provider_title,
    write_signed_payload,
)
from app.web.seo import (
    render_home_page,
    render_llms_txt,
    render_robots_txt,
    render_signal_page,
    render_sitemap_xml,
    render_trader_page,
)

router = APIRouter()
STATIC_DIR = Path(__file__).resolve().parent / "static"
PLATFORM_HTML = STATIC_DIR / "platform.html"
SESSION_COOKIE = "platform_session"
ADMIN_SESSION_COOKIE = "platform_admin_session"
OAUTH_FLOW_COOKIE = "platform_oauth_flow"
PENDING_SOCIAL_COOKIE = "platform_social_pending"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30
ADMIN_SESSION_COOKIE_MAX_AGE = 60 * 60 * 8
PLATFORM_SHELL_TEXT = {
    "en": {
        "boot_title": "SYSTEM LINKING",
        "boot_copy": "Loading live feed…",
        "brand_kicker": "AI investing feed and research",
        "brand_label": "Signal Loom",
        "account_label": "Account",
        "account_current": "Sign in",
        "language_label": "Language",
        "leaderboard_title": "AI Rank",
        "threads_title": "Public Research Threads",
        "research_stage_kicker": "Research",
        "research_stage_title": "Ask one ticker, then open deeper proof only if you need it.",
        "research_stage_description": "Fast AI summary first. Paid sections unlock timing, risk, and full notes.",
        "compare_button": "Compare opinions",
        "dock_label": "AI QUERY",
        "dock_status": "SYSTEM READY",
        "search_label": "Search threads",
        "search_placeholder": "Search ticker, tag, or phrase",
        "search_submit": "Search",
        "nav_research": "Research",
        "nav_feed": "Feed",
    },
    "ko": {
        "boot_title": "시스템 연결 중",
        "boot_copy": "라이브 피드를 불러오는 중입니다…",
        "brand_kicker": "AI 투자 피드와 리서치",
        "brand_label": "Signal Loom",
        "account_label": "계정",
        "account_current": "로그인",
        "language_label": "언어",
        "leaderboard_title": "AI 랭킹",
        "threads_title": "공개 리서치 스레드",
        "research_stage_kicker": "리서치",
        "research_stage_title": "종목 하나를 물어보고, 필요할 때만 심화 리서치를 여세요.",
        "research_stage_description": "먼저 빠른 AI 요약을 보고, 진입 시점과 리스크는 유료 섹션에서 확인하세요.",
        "compare_button": "의견 비교",
        "dock_label": "AI 질의",
        "dock_status": "준비 완료",
        "search_label": "글 검색",
        "search_placeholder": "종목, 태그, 문구로 검색",
        "search_submit": "검색",
        "nav_research": "리서치",
        "nav_feed": "피드",
    },
}

LEGAL_TEXT = {
    "en": {
        "title_suffix": "Signal Loom Legal",
        "terms": {
            "title": "Terms of Service",
            "summary": "These terms explain account access, social sign-in, credits, paid research, acceptable use, and user responsibility on Signal Loom.",
            "sections": [
                ("Eligibility and account creation", "You must use accurate profile information when creating or linking an account. If you start with Google, you are still responsible for the final profile details and agreement completion used inside the service."),
                ("Account security", "Keep your email address, password, and connected login methods secure. Activity performed through your account is treated as your responsibility unless you promptly report unauthorized access."),
                ("Credits and paid products", "Credits unlock premium research, bundles, desk passes, memberships, and archive access inside the platform. Credits are internal service value only and are not cash, deposits, prepaid financial instruments, or securities."),
                ("Manual payments and review", "Domestic top-up requests may be reviewed manually before credits are granted. We may request basic payment confirmation details when needed to prevent fraud, duplicate requests, or charge disputes."),
                ("Premium research access", "Unlocked research is licensed for your own viewing inside the service. Copying, redistributing, scraping, or reselling protected content is prohibited unless we give explicit written permission."),
                ("Research and investment responsibility", "Signal Loom provides research, summaries, rankings, and AI viewpoints. Nothing inside the service is personalized investment advice, portfolio management, or a promise of returns."),
                ("Refunds and reversals", "Where a payment is rejected, reversed, or confirmed to be abusive, we may cancel the related credits, access rights, or purchased products. Separate refund handling may depend on the payment route you used."),
                ("Abuse and suspension", "We may suspend or close accounts that abuse payments, scrape protected content, impersonate others, automate misuse of the service, or otherwise disrupt operations or other users."),
                ("Updates to the service", "We may update product structure, pricing, credit packs, research sections, and interface flows as the service changes. Material legal changes will be reflected through updated agreement versions."),
            ],
        },
        "privacy": {
            "title": "Privacy Collection and Use",
            "summary": "This notice explains what data we collect, how social sign-in data is handled, why we use it, and how long it stays on record.",
            "sections": [
                ("What we collect", "We store account name, email address, selected login provider, consent records, purchase history, alert preferences, and payment request details needed to operate the service."),
                ("Social sign-in data", "When you begin with Google, we only store the provider label and account details required for service access. We do not publish your Google account profile beyond what is needed for the platform account."),
                ("Why we use it", "We use this information to identify accounts, grant premium access, review manual payments, send operational notices, deliver alerts you requested, and answer support requests."),
                ("Legal basis and service operation", "We process required account data because it is necessary to provide the service you asked to use. Optional marketing consent is used only when you choose to receive product updates or event emails."),
                ("Retention", "We keep account and transaction data while the account is active and for a reasonable period after closure when support, billing, fraud review, or legal recordkeeping requires it."),
                ("Sharing and processors", "We may use service providers that support hosting, analytics, notifications, or payment review. They receive only the information required to perform their role for the service."),
                ("Your control", "You can request account review or deletion. Some billing, fraud-prevention, and compliance records may still be retained where law or legitimate operational needs require it."),
                ("Contact and updates", "If collection or use policies change in a material way, we will update this notice and the recorded agreement version used for future sign-ins or registrations."),
            ],
        },
        "investment_notice": {
            "title": "Investment Content Notice",
            "summary": "Signal Loom is a research and media platform. Users remain fully responsible for their own decisions and trade execution.",
            "sections": [
                ("Not personalized advice", "Signals, rankings, AI comments, premium notes, and world news reactions are informational only and do not consider your personal objectives, capital, cash flow needs, or risk tolerance."),
                ("No execution mandate", "The service does not place trades on your behalf as part of the public research experience. Any decision to buy, hold, or sell remains your own execution choice."),
                ("Risk of loss", "Market prices move quickly and losses can exceed expectations. Past performance, open-position markups, and AI rankings do not guarantee future results."),
                ("AI-generated content", "Some content is created or summarized by AI systems. Before acting, review the evidence, timing, liquidity, and risk levels yourself."),
                ("Delays and data limits", "Quotes, rankings, or summaries may be delayed, incomplete, or updated after publication. Premium access does not guarantee that every market event or risk factor is captured in real time."),
                ("Suitability check", "If you are unsure whether a position fits your circumstances, you should seek advice from a licensed professional before taking action."),
            ],
        },
    },
    "ko": {
        "title_suffix": "Signal Loom 약관",
        "terms": {
            "title": "회원 이용약관",
            "summary": "이 약관은 계정 이용, SNS 간편 시작, 크레딧, 유료 리서치, 서비스 이용 기준과 이용자 책임을 설명합니다.",
            "sections": [
                ("가입 대상과 계정 생성", "회원가입 또는 SNS 간편 시작 시 정확한 이름, 이메일, 동의 정보를 입력해야 합니다. 구글로 시작하더라도 최종 가입 정보와 동의 완료 책임은 이용자에게 있습니다."),
                ("계정 보안", "이메일, 비밀번호, 연결한 로그인 수단은 이용자가 직접 관리해야 합니다. 무단 접속이 의심되면 즉시 알려야 하며, 신고 전 계정에서 발생한 활동은 원칙적으로 본인 책임입니다."),
                ("크레딧과 유료 상품", "크레딧은 플랫폼 안의 심화 리서치, 번들, 데스크 패스, 멤버십, 아카이브를 여는 내부 사용 수단입니다. 현금, 예금, 선불전자지급수단, 증권 또는 환금성 자산이 아닙니다."),
                ("국내 결제 요청과 확인", "크레딧 충전은 계좌이체 또는 국내 카드 결제 요청으로 진행될 수 있으며, 운영 확인 전까지는 대기 상태일 수 있습니다. 중복 요청, 허위 요청, 결제 분쟁 방지를 위해 기본 확인 정보를 요청할 수 있습니다."),
                ("유료 리서치 이용 범위", "유료로 열린 심화 리서치와 아카이브는 회원 본인의 열람 용도로만 제공됩니다. 무단 복제, 재배포, 스크래핑, 재판매는 허용되지 않습니다."),
                ("리서치와 투자 책임", "Signal Loom은 리서치, 요약, 랭킹, AI 관점을 제공합니다. 플랫폼의 어떤 내용도 개인 맞춤 투자자문, 일임, 수익 보장을 의미하지 않습니다."),
                ("환불과 회수", "결제가 거절, 취소, 회수되거나 악용이 확인되면 관련 크레딧과 접근 권한이 회수될 수 있습니다. 실제 환불 처리는 이용한 결제 수단과 운영 정책에 따라 달라질 수 있습니다."),
                ("오남용과 제한", "결제 흐름 악용, 유료 콘텐츠 무단 수집, 사칭, 자동화 오남용, 서비스 운영 방해가 확인되면 계정 제한, 상품 회수, 해지가 이뤄질 수 있습니다."),
                ("서비스 변경", "서비스 구조, 가격, 크레딧 팩, 리서치 섹션, UI 흐름은 운영상 필요에 따라 변경될 수 있으며, 중요한 약관 변경은 버전 갱신과 함께 반영됩니다."),
            ],
        },
        "privacy": {
            "title": "개인정보 수집 및 이용",
            "summary": "서비스 운영에 필요한 계정, SNS 로그인, 결제, 알림 정보를 어떻게 수집하고 이용하는지 설명합니다.",
            "sections": [
                ("수집 항목", "계정 이름, 이메일, 선택한 로그인 수단, 약관 동의 기록, 구매 내역, 알림 설정, 충전 요청 정보 등 서비스 제공에 필요한 정보를 저장합니다."),
                ("SNS 로그인 정보", "구글로 시작하는 경우에도 서비스 접근에 필요한 범위의 로그인 수단 정보만 저장하며, 플랫폼 계정 운영에 불필요한 프로필 정보는 별도로 공개하지 않습니다."),
                ("이용 목적", "회원 식별, 유료 접근 권한 부여, 수동 결제 확인, 알림 발송, 서비스 공지, 문의 대응, 부정 이용 방지를 위해 사용합니다."),
                ("처리 근거", "필수 정보는 서비스 제공과 계정 운영을 위해 처리되며, 마케팅 수신은 이용자가 별도로 동의한 경우에만 사용합니다."),
                ("보관 기간", "회원 탈퇴 전까지 보관하며, 결제·문의·부정 이용 대응·법적 기록 보관이 필요한 정보는 관련 기준에 따라 추가 보관할 수 있습니다."),
                ("제공 및 위탁", "호스팅, 알림 발송, 분석, 결제 확인 등 서비스 운영을 위해 필요한 범위에서 외부 처리자와 정보를 공유하거나 위탁할 수 있습니다."),
                ("이용자 권리", "이용자는 계정 검토, 정정, 삭제를 요청할 수 있습니다. 다만 결제 및 법적 의무 이행에 필요한 일부 기록은 별도 보관될 수 있습니다."),
                ("고지와 변경", "수집·이용 정책이 중요하게 바뀌면 이 문서와 동의 버전을 함께 갱신합니다."),
            ],
        },
        "investment_notice": {
            "title": "투자 콘텐츠 유의사항",
            "summary": "Signal Loom은 리서치와 정보 제공 플랫폼이며, 최종 투자 판단과 실행 책임은 이용자에게 있습니다.",
            "sections": [
                ("개인 맞춤 자문 아님", "신호, 랭킹, AI 의견, 프리미엄 리서치, 세계 경제 뉴스 해설은 일반 정보 제공이며 이용자의 자산 상황, 목표, 위험 성향을 반영한 개인 맞춤 자문이 아닙니다."),
                ("자동 매매 지시 아님", "플랫폼의 공개 리서치 경험은 이용자를 대신해 자동으로 주문을 넣지 않습니다. 매수, 관망, 매도 판단은 모두 정보 제공이며 실제 실행은 이용자 본인이 결정합니다."),
                ("손실 가능성", "시장 가격은 빠르게 변하며 손실이 발생할 수 있습니다. 과거 성과, 미청산 평가손익, 청산 기록, AI 랭킹은 미래 수익을 보장하지 않습니다."),
                ("AI 생성 콘텐츠", "일부 콘텐츠는 AI가 생성하거나 요약합니다. 실제 매매 전에는 근거, 타이밍, 유동성, 리스크 기준을 직접 확인해야 합니다."),
                ("지연 및 한계", "시세, 뉴스 반응, 랭킹, 요약은 지연되거나 불완전할 수 있습니다. 유료 리서치가 모든 시장 이벤트를 실시간으로 포착한다는 보장은 없습니다."),
                ("적합성 확인", "현재 판단이 본인 상황에 맞는지 확신이 없다면, 실제 투자 전 자격을 갖춘 전문가와 상담해야 합니다."),
            ],
        },
    },
}


def _platform_shell_text(language: str) -> dict[str, str]:
    return PLATFORM_SHELL_TEXT.get(language) or PLATFORM_SHELL_TEXT.get(language.split("-")[0]) or PLATFORM_SHELL_TEXT["en"]


def _render_platform_shell(request: Request) -> str:
    language = request_language(request, query_param="lang")
    text = _platform_shell_text(language)
    template = PLATFORM_HTML.read_text(encoding="utf-8")
    replacements = {
        "__PLATFORM_INITIAL_LANGUAGE__": escape(language),
        "__PLATFORM_BOOT_TITLE__": escape(text["boot_title"]),
        "__PLATFORM_BOOT_COPY__": escape(text["boot_copy"]),
        "__PLATFORM_BRAND_KICKER__": escape(text["brand_kicker"]),
        "__PLATFORM_BRAND_LABEL__": escape(text["brand_label"]),
        "__PLATFORM_ACCOUNT_LABEL__": escape(text["account_label"]),
        "__PLATFORM_ACCOUNT_CURRENT__": escape(text["account_current"]),
        "__PLATFORM_LANGUAGE_LABEL__": escape(text["language_label"]),
        "__PLATFORM_LANGUAGE_CURRENT__": escape(language_label(language)),
        "__PLATFORM_RESEARCH_STAGE_KICKER__": escape(text["research_stage_kicker"]),
        "__PLATFORM_RESEARCH_STAGE_TITLE__": escape(text["research_stage_title"]),
        "__PLATFORM_RESEARCH_STAGE_DESCRIPTION__": escape(text["research_stage_description"]),
        "__PLATFORM_COMPARE_BUTTON__": escape(text["compare_button"]),
        "__PLATFORM_LEADERBOARD_TITLE__": escape(text["leaderboard_title"]),
        "__PLATFORM_THREADS_TITLE__": escape(text["threads_title"]),
        "__PLATFORM_DOCK_LABEL__": escape(text["dock_label"]),
        "__PLATFORM_DOCK_STATUS__": escape(text["dock_status"]),
        "__PLATFORM_SEARCH_LABEL__": escape(text["search_label"]),
        "__PLATFORM_SEARCH_PLACEHOLDER__": escape(text["search_placeholder"]),
        "__PLATFORM_SEARCH_SUBMIT__": escape(text["search_submit"]),
        "__PLATFORM_NAV_RESEARCH__": escape(text["nav_research"]),
        "__PLATFORM_NAV_FEED__": escape(text["nav_feed"]),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def _legal_copy(request: Request, slug: str) -> dict:
    language = request_language(request, query_param="lang")
    local = LEGAL_TEXT.get(language) or LEGAL_TEXT.get(language.split("-")[0]) or {}
    base = LEGAL_TEXT["en"]
    page = local.get(slug) or base.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Legal page not found")
    return {
        "language": language,
        "title_suffix": local.get("title_suffix") or base["title_suffix"],
        "page": page,
    }


def _render_legal_page(request: Request, slug: str) -> str:
    copy = _legal_copy(request, slug)
    page = copy["page"]
    sections = "".join(
        f"""
        <section class="legal-section">
          <h2>{escape(title)}</h2>
          <p>{escape(body)}</p>
        </section>
        """
        for title, body in page["sections"]
    )
    return f"""<!doctype html>
<html lang="{escape(copy['language'])}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(page['title'])} · {escape(copy['title_suffix'])}</title>
    <style>
      body {{
        margin: 0;
        background: #070b10;
        color: #e7f0f5;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      main {{
        max-width: 860px;
        margin: 0 auto;
        padding: 48px 24px 72px;
      }}
      .legal-shell {{
        border: 1px solid rgba(91, 178, 193, 0.24);
        background: rgba(7, 12, 16, 0.94);
        box-shadow: inset 0 0 0 1px rgba(20, 50, 62, 0.45);
        padding: 28px;
      }}
      .legal-kicker {{
        color: rgba(112, 201, 219, 0.88);
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin: 0 0 12px;
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: 34px;
        line-height: 1.15;
      }}
      .legal-summary {{
        margin: 0 0 24px;
        color: rgba(189, 211, 221, 0.84);
        font-size: 16px;
        line-height: 1.7;
      }}
      .legal-section + .legal-section {{
        margin-top: 18px;
        padding-top: 18px;
        border-top: 1px solid rgba(72, 127, 140, 0.2);
      }}
      .legal-section h2 {{
        margin: 0 0 8px;
        font-size: 18px;
      }}
      .legal-section p {{
        margin: 0;
        color: rgba(193, 214, 223, 0.82);
        line-height: 1.75;
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="legal-shell">
        <p class="legal-kicker">Signal Loom Legal</p>
        <h1>{escape(page['title'])}</h1>
        <p class="legal-summary">{escape(page['summary'])}</p>
        {sections}
      </div>
    </main>
  </body>
</html>"""


class PlatformPostCreate(BaseModel):
    """Request payload for a new shared community thread."""

    author_id: str
    kind: str
    contribution_type: str = ""
    ticker: str
    company: str = ""
    headline: str
    summary: str
    tags: list[str] = []
    levels: list[str] = []


class PlatformFollowUpdate(BaseModel):
    """Request payload for follow state updates."""

    viewer_id: str = ""
    author_id: str
    following: bool


class PlatformAuthRegister(BaseModel):
    """Request payload for local account creation."""

    name: str
    email: str
    password: str
    agreements: dict[str, bool] = {}


class PlatformAuthSocialComplete(BaseModel):
    """Request payload for SNS sign-up completion."""

    provider: str
    name: str
    email: str
    subject: str = ""
    agreements: dict[str, bool] = {}


class PlatformAuthLogin(BaseModel):
    """Request payload for local login."""

    email: str
    password: str


class PlatformGoogleCredentialLogin(BaseModel):
    """Request payload for Google Identity Services sign-in."""

    credential: str


class PlatformCommerceSectionUnlock(BaseModel):
    """Unlock premium sections for a single ticker."""

    ticker: str
    section_ids: list[str]


class PlatformCommerceProductPurchase(BaseModel):
    """Purchase a commerce product."""

    product_id: str
    ticker: str = ""
    author_id: str = ""


class PlatformPaymentRequestCreate(BaseModel):
    """Create a manual top-up request for a credit pack."""

    pack_id: str
    method: str
    depositor_name: str = ""
    note: str = ""


class PlatformPaymentRequestReview(BaseModel):
    """Review a manual payment request."""

    note: str = ""


class PlatformAlertPreferenceUpdate(BaseModel):
    """Update alert preferences for the authenticated account."""

    preferences: dict[str, bool]


class PlatformAdminSession(BaseModel):
    """Create a short-lived admin browser session without putting tokens in URLs."""

    token: str


def _current_session_user(request: Request) -> dict | None:
    return auth_store.user_for_token(request.cookies.get(SESSION_COOKIE))


def _require_session_user(request: Request) -> dict:
    user = _current_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in first.")
    return user


def _viewer_key(request: Request, fallback: str = "") -> str:
    session_user = _current_session_user(request)
    if session_user:
        return session_user["id"]
    return fallback


def _account_response(request: Request, user: dict | None) -> dict:
    return {
        "authenticated": bool(user),
        "user": user,
        "account": commerce_store.snapshot(user["id"]) if user else None,
        "identity": auth_store.account_snapshot(user["id"]) if user else None,
        "catalog": commerce_store.catalog(),
        "oauth_providers": social_provider_catalog(request),
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_social_cookies(response: Response) -> None:
    for name in (OAUTH_FLOW_COOKIE, PENDING_SOCIAL_COOKIE):
        response.delete_cookie(name, path="/")
        response.set_cookie(
            name,
            "",
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=0,
            expires=0,
            path="/",
        )


def _platform_redirect_url(request: Request, language: str, **params: str) -> str:
    query = {"lang": language}
    query.update({key: value for key, value in params.items() if value})
    return f"{request.url_for('platform_home')}?{urlencode(query)}"


def _pending_social_profile(request: Request) -> dict | None:
    payload = read_signed_payload(
        request.cookies.get(PENDING_SOCIAL_COOKIE),
        max_age_seconds=PENDING_COOKIE_MAX_AGE_SECONDS,
    )
    if not payload:
        return None
    return {
        "provider": payload.get("provider") or "",
        "subject": payload.get("subject") or "",
        "name": payload.get("name") or "",
        "email": payload.get("email") or "",
    }


def _content_language_headers(request: Request) -> dict[str, str]:
    return {
        "Content-Language": request_language(request),
        "Vary": "Accept-Language",
    }


def _expected_admin_token() -> str:
    expected = os.getenv("PLATFORM_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin token is not configured.")
    return expected


def _admin_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _admin_cookie_is_valid(request: Request, expected: str) -> bool:
    payload = read_signed_payload(
        request.cookies.get(ADMIN_SESSION_COOKIE),
        max_age_seconds=ADMIN_SESSION_COOKIE_MAX_AGE,
    )
    if not payload:
        return False
    if payload.get("kind") != "platform_admin":
        return False
    return payload.get("token_digest") == _admin_token_digest(expected)


def _require_admin_token(request: Request) -> None:
    expected = _expected_admin_token()
    provided = request.headers.get("x-platform-admin-token", "").strip()
    if provided and provided == expected:
        return
    if _admin_cookie_is_valid(request, expected):
        return
    if request.query_params.get("token"):
        raise HTTPException(status_code=403, detail="Admin token in URL is no longer accepted.")
    raise HTTPException(status_code=403, detail="Admin token is invalid.")


def _set_admin_session_cookie(response: Response, expected: str) -> None:
    token = write_signed_payload(
        {
            "kind": "platform_admin",
            "token_digest": _admin_token_digest(expected),
            "created_at": time.time(),
        }
    )
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=ADMIN_SESSION_COOKIE_MAX_AGE,
        path="/",
    )


def _validate_admin_session_token(token: str) -> str:
    expected = _expected_admin_token()
    if token.strip() != expected:
        raise HTTPException(status_code=403, detail="Admin token is invalid.")
    return expected


def _admin_overview_payload() -> dict:
    blueprint = build_platform_blueprint()
    authors = blueprint.get("authors", [])
    members = []
    membership_count = 0
    alerts_count = 0
    archive_count = 0
    social_only_count = 0
    local_password_count = 0

    for account in auth_store.list_accounts():
        commerce = commerce_store.snapshot(account["id"])
        member = {
            **account,
            "credits_balance": commerce.get("credits_balance", 0),
            "membership_active": bool(commerce.get("membership_active")),
            "membership_days_left": int(commerce.get("membership_days_left") or 0),
            "alerts_active": bool(commerce.get("alerts_active")),
            "archive_active": bool(commerce.get("archive_active")),
            "desk_passes_count": len(commerce.get("desk_passes", [])),
            "bundle_tickers_count": len(commerce.get("bundle_tickers", [])),
            "payment_requests_count": len(commerce.get("payment_requests", [])),
            "linked_provider_labels": [social_provider_title(provider) for provider in account.get("linked_providers", [])],
        }
        members.append(member)
        if member["membership_active"]:
            membership_count += 1
        if member["alerts_active"]:
            alerts_count += 1
        if member["archive_active"]:
            archive_count += 1
        if member.get("social_only"):
            social_only_count += 1
        if member.get("has_local_password"):
            local_password_count += 1

    payment_requests = []
    for item in commerce_store.list_payment_requests():
        payment_requests.append(
            {
                **item,
                "user": auth_store.user_by_id(item.get("account_id")),
            }
        )

    return {
        "summary": {
            "ai_desks": len(authors),
            "members": len(members),
            "social_only_members": social_only_count,
            "password_members": local_password_count,
            "active_memberships": membership_count,
            "alerts_enabled": alerts_count,
            "archive_enabled": archive_count,
            "pending_payments": sum(1 for item in payment_requests if item.get("status") == "pending"),
        },
        "authors": authors,
        "members": members,
        "payment_requests": payment_requests,
    }


def _render_admin_dashboard(request: Request) -> str:
    data = _admin_overview_payload()
    summary = data["summary"]
    authors_markup = "".join(
        f"""
        <tr>
          <td>{escape(author.get("display_name", ""))}</td>
          <td>{escape(author.get("handle", ""))}</td>
          <td>{escape(author.get("persona", ""))}</td>
          <td>{escape(author.get("strategy_title", ""))}</td>
          <td>{escape(str(author.get("performance", {}).get("closed_trades", 0)))}</td>
          <td>{escape(str(author.get("performance", {}).get("total_return", "0%")))}</td>
        </tr>
        """
        for author in data["authors"]
    )
    members_markup = "".join(
        f"""
        <tr>
          <td>{escape(member.get("name", ""))}</td>
          <td>{escape(member.get("email", ""))}</td>
          <td>{escape(social_provider_title(member.get("provider", "local")))}</td>
          <td>{escape(", ".join(member.get("linked_provider_labels", [])) or "-")}</td>
          <td>{'yes' if member.get("membership_active") else 'no'}</td>
          <td>{'yes' if member.get("alerts_active") else 'no'}</td>
          <td>{escape(str(member.get("credits_balance", 0)))}</td>
          <td>{escape(member.get("created_at", ""))}</td>
        </tr>
        """
        for member in data["members"]
    )
    payment_markup = "".join(
        f"""
        <tr>
          <td>{escape(item.get("id", ""))}</td>
          <td>{escape(item.get("user", {}).get("email", "-") if isinstance(item.get("user"), dict) else "-")}</td>
          <td>{escape(item.get("pack_id", ""))}</td>
          <td>{escape(item.get("method", ""))}</td>
          <td>{escape(str(item.get("amount_krw", 0)))}</td>
          <td>{escape(item.get("status", ""))}</td>
          <td>{escape(item.get("created_at", ""))}</td>
        </tr>
        """
        for item in data["payment_requests"]
    ) or '<tr><td colspan="7">No payment requests yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Signal Loom Admin Dashboard</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #071018;
        --panel: rgba(9, 18, 26, 0.94);
        --line: rgba(102, 223, 255, 0.26);
        --text: #edf7ff;
        --muted: rgba(191, 210, 224, 0.82);
        --accent: #62dfff;
        --accent-soft: rgba(98, 223, 255, 0.12);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        background: radial-gradient(circle at top, rgba(34, 96, 118, 0.18), transparent 42%), var(--bg);
        color: var(--text);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      main {{ max-width: 1280px; margin: 0 auto; padding: 36px 24px 64px; }}
      .hero {{
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(7, 14, 20, 0.96), rgba(9, 18, 26, 0.92));
        padding: 28px;
        margin-bottom: 24px;
      }}
      .kicker {{
        color: var(--accent);
        font: 700 12px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: 0.24em;
        text-transform: uppercase;
        margin: 0 0 10px;
      }}
      h1 {{ margin: 0 0 8px; font-size: 40px; }}
      p {{ margin: 0; color: var(--muted); line-height: 1.6; }}
      .summary-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 14px;
        margin: 20px 0 0;
      }}
      .summary-card {{
        border: 1px solid var(--line);
        background: var(--panel);
        padding: 18px;
      }}
      .summary-card strong {{ display: block; font-size: 28px; margin-top: 8px; }}
      .section {{
        border: 1px solid var(--line);
        background: var(--panel);
        padding: 22px;
        margin-top: 18px;
      }}
      .section h2 {{
        margin: 0 0 14px;
        font-size: 24px;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
      }}
      th, td {{
        text-align: left;
        padding: 12px 10px;
        border-top: 1px solid rgba(102, 223, 255, 0.12);
        vertical-align: top;
      }}
      th {{
        color: var(--accent);
        font: 700 12px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: 0.18em;
        text-transform: uppercase;
      }}
      .row-label {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        border: 1px solid rgba(102, 223, 255, 0.18);
        background: var(--accent-soft);
        color: var(--accent);
        font: 700 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <p class="kicker">Signal Loom Admin</p>
        <h1>Admin dashboard</h1>
        <p>Review AI desks, member accounts, and manual payment activity from one place.</p>
        <div class="summary-grid">
          <div class="summary-card"><span class="row-label">AI desks</span><strong>{summary['ai_desks']}</strong></div>
          <div class="summary-card"><span class="row-label">Members</span><strong>{summary['members']}</strong></div>
          <div class="summary-card"><span class="row-label">Social only</span><strong>{summary['social_only_members']}</strong></div>
          <div class="summary-card"><span class="row-label">Password ready</span><strong>{summary['password_members']}</strong></div>
          <div class="summary-card"><span class="row-label">Memberships</span><strong>{summary['active_memberships']}</strong></div>
          <div class="summary-card"><span class="row-label">Alerts</span><strong>{summary['alerts_enabled']}</strong></div>
          <div class="summary-card"><span class="row-label">Archive</span><strong>{summary['archive_enabled']}</strong></div>
          <div class="summary-card"><span class="row-label">Pending pay</span><strong>{summary['pending_payments']}</strong></div>
        </div>
      </section>
      <section class="section">
        <h2>AI desks</h2>
        <table>
          <thead>
            <tr><th>Name</th><th>Handle</th><th>Persona</th><th>Strategy</th><th>Closed</th><th>Total return</th></tr>
          </thead>
          <tbody>{authors_markup}</tbody>
        </table>
      </section>
      <section class="section">
        <h2>Members</h2>
        <table>
          <thead>
            <tr><th>Name</th><th>Email</th><th>Primary</th><th>Linked sign-in</th><th>Membership</th><th>Alerts</th><th>Credits</th><th>Created</th></tr>
          </thead>
          <tbody>{members_markup}</tbody>
        </table>
      </section>
      <section class="section">
        <h2>Payment requests</h2>
        <table>
          <thead>
            <tr><th>ID</th><th>Email</th><th>Pack</th><th>Method</th><th>Amount</th><th>Status</th><th>Created</th></tr>
          </thead>
          <tbody>{payment_markup}</tbody>
        </table>
      </section>
    </main>
  </body>
</html>"""


@router.get("/", include_in_schema=False)
async def root_landing(request: Request) -> HTMLResponse:
    """Serve the crawlable marketing and discovery landing page."""
    blueprint = build_platform_blueprint()
    return HTMLResponse(render_home_page(request, blueprint), headers=_content_language_headers(request))


@router.get("/platform", include_in_schema=False)
async def platform_home(request: Request) -> HTMLResponse:
    """Serve the interactive platform shell while consolidating indexing elsewhere."""
    return HTMLResponse(
        _render_platform_shell(request),
        headers={
            "X-Robots-Tag": "noindex, follow",
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            **_content_language_headers(request),
        },
    )


@router.get("/platform/admin", include_in_schema=False)
async def platform_admin_dashboard(request: Request) -> HTMLResponse:
    _require_admin_token(request)
    return HTMLResponse(_render_admin_dashboard(request))


@router.post("/api/platform/admin/session", include_in_schema=False)
async def platform_admin_session(payload: PlatformAdminSession) -> JSONResponse:
    expected = _validate_admin_session_token(payload.token)
    response = JSONResponse({"ok": True, "redirect": "/platform/admin"})
    _set_admin_session_cookie(response, expected)
    return response


@router.get("/legal/terms", include_in_schema=False)
async def legal_terms(request: Request) -> HTMLResponse:
    return HTMLResponse(_render_legal_page(request, "terms"), headers=_content_language_headers(request))


@router.get("/legal/privacy", include_in_schema=False)
async def legal_privacy(request: Request) -> HTMLResponse:
    return HTMLResponse(_render_legal_page(request, "privacy"), headers=_content_language_headers(request))


@router.get("/legal/investment-notice", include_in_schema=False)
async def legal_investment_notice(request: Request) -> HTMLResponse:
    return HTMLResponse(_render_legal_page(request, "investment_notice"), headers=_content_language_headers(request))


@router.get("/traders/{author_id}", include_in_schema=False)
async def trader_profile(author_id: str, request: Request) -> HTMLResponse:
    """Serve a crawlable trader profile page."""
    blueprint = build_platform_blueprint()
    author = next((item for item in blueprint["authors"] if item["id"] == author_id), None)
    if author is None:
        raise HTTPException(status_code=404, detail="Trader not found")
    return HTMLResponse(render_trader_page(request, blueprint, author), headers=_content_language_headers(request))


@router.get("/signals/{thread_id}", include_in_schema=False)
async def signal_detail(thread_id: str, request: Request) -> HTMLResponse:
    """Serve a crawlable signal detail page."""
    blueprint = build_platform_blueprint()
    thread = next((item for item in blueprint["threads"] if item["id"] == thread_id), None)
    if thread is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return HTMLResponse(render_signal_page(request, blueprint, thread), headers=_content_language_headers(request))


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt(request: Request) -> PlainTextResponse:
    """Publish crawler rules for search engines and AI bots."""
    return PlainTextResponse(render_robots_txt(request))


@router.get("/llms.txt", include_in_schema=False)
async def llms_txt(request: Request) -> PlainTextResponse:
    """Publish a compact machine-readable summary for LLM retrieval."""
    blueprint = build_platform_blueprint()
    return PlainTextResponse(
        render_llms_txt(request, blueprint, expanded=False),
        headers=_content_language_headers(request),
    )


@router.get("/llms-full.txt", include_in_schema=False)
async def llms_full_txt(request: Request) -> PlainTextResponse:
    """Publish an expanded machine-readable summary for LLM retrieval."""
    blueprint = build_platform_blueprint()
    return PlainTextResponse(
        render_llms_txt(request, blueprint, expanded=True),
        headers=_content_language_headers(request),
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request) -> Response:
    """Publish the XML sitemap for crawlable platform pages."""
    blueprint = build_platform_blueprint()
    return Response(
        content=render_sitemap_xml(request, blueprint),
        media_type="application/xml",
    )


@router.get("/api/platform/blueprint", include_in_schema=False)
async def platform_blueprint() -> dict:
    """Return structured platform data for the frontend."""
    return build_platform_blueprint()


@router.get("/api/platform/community", include_in_schema=False)
async def platform_community(request: Request, viewer_id: str = Query(default="", max_length=80)) -> dict:
    """Return shared posts and follow state for the current viewer."""
    return community_store.snapshot(viewer_id=_viewer_key(request, viewer_id), authors=AUTHORS)


@router.post("/api/platform/posts", include_in_schema=False)
async def create_platform_post(payload: PlatformPostCreate) -> dict:
    """Create a new shared community thread."""
    try:
        thread = community_store.create_post(payload.model_dump(), authors=AUTHORS)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"thread": thread}


@router.post("/api/platform/follows", include_in_schema=False)
async def update_platform_follow(request: Request, payload: PlatformFollowUpdate) -> dict:
    """Persist follow state for the current viewer."""
    user = _require_session_user(request)
    account = commerce_store.snapshot(user["id"])
    if not (account.get("follow_pass_active") or account.get("membership_active")):
        raise HTTPException(status_code=403, detail="Unlock following first.")
    try:
        return community_store.set_follow(
            viewer_id=_viewer_key(request, user["id"]),
            author_id=payload.author_id,
            following=payload.following,
            authors=AUTHORS,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/platform/session", include_in_schema=False)
async def platform_session(request: Request) -> dict:
    """Return the current signed-in platform user, if any."""
    user = _current_session_user(request)
    return _account_response(request, user)


@router.get("/api/platform/account", include_in_schema=False)
async def platform_account(request: Request) -> dict:
    """Return the current account snapshot, including credits and entitlements."""
    user = _current_session_user(request)
    return _account_response(request, user)


@router.get("/api/platform/auth/social/pending", include_in_schema=False)
async def platform_social_pending(request: Request) -> dict:
    """Return any pending social profile waiting for agreement completion."""
    if _current_session_user(request):
        return {"pending": None}
    return {"pending": _pending_social_profile(request)}


@router.delete("/api/platform/auth/social/pending", include_in_schema=False)
async def platform_social_pending_clear() -> JSONResponse:
    """Clear a pending social profile and return to email auth only."""
    response = JSONResponse({"pending": None})
    response.delete_cookie(PENDING_SOCIAL_COOKIE, path="/")
    return response


@router.get("/api/platform/auth/oauth/{provider}/start", include_in_schema=False)
async def platform_oauth_start(provider: str, request: Request, lang: str = Query(default="")) -> RedirectResponse:
    """Start a real external OAuth flow for a supported social provider."""
    language = (lang or request_language(request, query_param="lang") or "en").strip() or "en"
    try:
        redirect_url, flow_cookie = build_authorization_redirect(provider, request, language)
    except SocialOAuthError as error:
        return RedirectResponse(
            _platform_redirect_url(request, language, auth_error=str(error)),
            status_code=303,
        )

    response = RedirectResponse(redirect_url, status_code=307)
    response.set_cookie(
        OAUTH_FLOW_COOKIE,
        flow_cookie,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=FLOW_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )
    return response


async def _platform_oauth_callback_impl(
    provider: str,
    request: Request,
    *,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    """Handle the provider callback and either sign in or continue sign-up."""
    flow_payload = read_signed_payload(
        request.cookies.get(OAUTH_FLOW_COOKIE),
        max_age_seconds=FLOW_COOKIE_MAX_AGE_SECONDS,
    ) or {}
    query_lang = (request.query_params.get("lang") or "").strip()
    language = (
        normalize_language(query_lang) if query_lang
        else normalize_language(str(flow_payload.get("lang") or "")) if flow_payload.get("lang")
        else request_language(request, query_param="lang")
    )
    if error:
        return RedirectResponse(
            _platform_redirect_url(request, language, auth_error=f"{social_provider_title(provider)} sign-in was canceled."),
            status_code=303,
        )
    if not code or not state:
        return RedirectResponse(
            _platform_redirect_url(request, language, auth_error="Sign-in response was incomplete."),
            status_code=303,
        )

    try:
        profile = await complete_callback(provider, request, code, state, request.cookies.get(OAUTH_FLOW_COOKIE))
    except SocialOAuthError as oauth_error:
        response = RedirectResponse(
            _platform_redirect_url(request, language, auth_error=str(oauth_error)),
            status_code=303,
        )
        _clear_social_cookies(response)
        return response

    try:
        session = auth_store.oauth_sign_in(
            provider=profile["provider"],
            subject=profile["subject"],
            email=profile.get("email", ""),
            name=profile.get("name", ""),
        )
    except ValueError as error_detail:
        response = RedirectResponse(
            _platform_redirect_url(request, language, auth_error=str(error_detail)),
            status_code=303,
        )
        _clear_social_cookies(response)
        return response

    if session:
        user, token = session
        response = RedirectResponse(_platform_redirect_url(request, language), status_code=303)
        _set_session_cookie(response, token)
        _clear_social_cookies(response)
        return response

    pending_cookie = write_signed_payload(
        {
            "provider": profile["provider"],
            "subject": profile["subject"],
            "email": profile.get("email", ""),
            "name": profile.get("name", ""),
            "created_at": __import__("time").time(),
        }
    )
    response = RedirectResponse(
        _platform_redirect_url(request, language, auth="complete-social"),
        status_code=303,
    )
    response.set_cookie(
        PENDING_SOCIAL_COOKIE,
        pending_cookie,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=PENDING_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )
    response.delete_cookie(OAUTH_FLOW_COOKIE, path="/")
    response.set_cookie(
        OAUTH_FLOW_COOKIE,
        "",
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=0,
        expires=0,
        path="/",
    )
    return response


@router.get("/api/platform/auth/oauth/{provider}/callback", include_in_schema=False)
async def platform_oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    return await _platform_oauth_callback_impl(
        provider,
        request,
        code=code,
        state=state,
        error=error,
    )


@router.post("/api/platform/auth/oauth/{provider}/callback", include_in_schema=False)
async def platform_oauth_callback_post(provider: str, request: Request) -> RedirectResponse:
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body, keep_blank_values=True)
    return await _platform_oauth_callback_impl(
        provider,
        request,
        code=str((form.get("code") or [""])[0] or ""),
        state=str((form.get("state") or [""])[0] or ""),
        error=str((form.get("error") or [""])[0] or ""),
    )


@router.get("/api/platform/commerce/catalog", include_in_schema=False)
async def platform_commerce_catalog() -> dict:
    """Return the current pricing and manual top-up catalog."""
    return {"catalog": commerce_store.catalog()}


@router.post("/api/platform/auth/register", include_in_schema=False)
async def platform_register(request: Request, payload: PlatformAuthRegister) -> JSONResponse:
    """Create a lightweight local account and start a session."""
    try:
        user, token = auth_store.register(
            name=payload.name,
            email=payload.email,
            password=payload.password,
            agreements=payload.agreements,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    response = JSONResponse(_account_response(request, user))
    _set_session_cookie(response, token)
    return response


@router.post("/api/platform/auth/social/complete", include_in_schema=False)
async def platform_social_complete(request: Request, payload: PlatformAuthSocialComplete) -> JSONResponse:
    """Create or sign in to an SNS-started account after agreement completion."""
    pending = _pending_social_profile(request)
    provider = pending.get("provider") if pending else payload.provider
    subject = pending.get("subject") if pending else payload.subject
    name = payload.name or (pending.get("name") if pending else "")
    email = payload.email or (pending.get("email") if pending else "")
    try:
        user, token = auth_store.social_complete(
            provider=provider,
            name=name,
            email=email,
            subject=subject,
            agreements=payload.agreements,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    response = JSONResponse(_account_response(request, user))
    _set_session_cookie(response, token)
    response.delete_cookie(PENDING_SOCIAL_COOKIE, path="/")
    response.set_cookie(
        PENDING_SOCIAL_COOKIE,
        "",
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=0,
        expires=0,
        path="/",
    )
    return response


@router.post("/api/platform/auth/google/credential", include_in_schema=False)
async def platform_google_credential_login(request: Request, payload: PlatformGoogleCredentialLogin) -> JSONResponse:
    """Sign in with a Google ID token verified server-side."""
    try:
        profile = await verify_google_credential(payload.credential)
    except SocialOAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=400, detail="Google sign-in could not be verified.") from error

    try:
        session = auth_store.oauth_sign_in(
            provider=profile["provider"],
            subject=profile["subject"],
            email=profile.get("email", ""),
            name=profile.get("name", ""),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if session:
        user, token = session
        response = JSONResponse(_account_response(request, user))
        _set_session_cookie(response, token)
        _clear_social_cookies(response)
        return response

    pending_cookie = write_signed_payload(
        {
            "provider": profile["provider"],
            "subject": profile["subject"],
            "email": profile.get("email", ""),
            "name": profile.get("name", ""),
            "created_at": __import__("time").time(),
        }
    )
    response = JSONResponse(
        {
            **_account_response(request, None),
            "pending": {
                "provider": profile["provider"],
                "subject": profile["subject"],
                "email": profile.get("email", ""),
                "name": profile.get("name", ""),
            },
            "needs_social_completion": True,
        }
    )
    response.set_cookie(
        PENDING_SOCIAL_COOKIE,
        pending_cookie,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=PENDING_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )
    response.delete_cookie(OAUTH_FLOW_COOKIE, path="/")
    response.set_cookie(
        OAUTH_FLOW_COOKIE,
        "",
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=0,
        expires=0,
        path="/",
    )
    return response


@router.post("/api/platform/auth/login", include_in_schema=False)
async def platform_login(request: Request, payload: PlatformAuthLogin) -> JSONResponse:
    """Start a lightweight local account session."""
    try:
        user, token = auth_store.login(email=payload.email, password=payload.password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    response = JSONResponse(_account_response(request, user))
    _set_session_cookie(response, token)
    return response


@router.post("/api/platform/auth/logout", include_in_schema=False)
async def platform_logout(request: Request) -> JSONResponse:
    """Clear the current session cookie."""
    auth_store.logout(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse(_account_response(request, None))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.post("/api/platform/commerce/sections/unlock", include_in_schema=False)
async def platform_unlock_sections(request: Request, payload: PlatformCommerceSectionUnlock) -> dict:
    """Unlock paid research sections for the authenticated user."""
    user = _require_session_user(request)
    try:
        account = commerce_store.unlock_sections(
            account_id=user["id"],
            ticker=payload.ticker,
            section_ids=payload.section_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "authenticated": True,
        "user": user,
        "account": account,
        "catalog": commerce_store.catalog(),
    }


@router.post("/api/platform/commerce/products/purchase", include_in_schema=False)
async def platform_purchase_product(request: Request, payload: PlatformCommerceProductPurchase) -> dict:
    """Purchase a product or entitlement with credits."""
    user = _require_session_user(request)
    try:
        account = commerce_store.purchase_product(
            account_id=user["id"],
            product_id=payload.product_id,
            ticker=payload.ticker,
            author_id=payload.author_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "authenticated": True,
        "user": user,
        "account": account,
        "catalog": commerce_store.catalog(),
    }


@router.post("/api/platform/commerce/payment-requests", include_in_schema=False)
async def platform_create_payment_request(request: Request, payload: PlatformPaymentRequestCreate) -> dict:
    """Create a manual domestic payment request for a credit pack."""
    user = _require_session_user(request)
    try:
        account = commerce_store.create_payment_request(
            account_id=user["id"],
            pack_id=payload.pack_id,
            method=payload.method,
            depositor_name=payload.depositor_name,
            note=payload.note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "authenticated": True,
        "user": user,
        "account": account,
        "catalog": commerce_store.catalog(),
    }


@router.get("/api/platform/admin/payment-requests", include_in_schema=False)
async def platform_admin_payment_requests(request: Request) -> dict:
    """List pending and reviewed manual payment requests for operations."""
    _require_admin_token(request)
    requests = []
    for item in commerce_store.list_payment_requests():
        user = auth_store.user_by_id(item.get("account_id"))
        requests.append(
            {
                **item,
                "user": user,
            }
        )
    return {"requests": requests}


@router.get("/api/platform/admin/overview", include_in_schema=False)
async def platform_admin_overview(request: Request) -> dict:
    _require_admin_token(request)
    return _admin_overview_payload()


@router.post("/api/platform/admin/payment-requests/{request_id}/approve", include_in_schema=False)
async def platform_admin_approve_payment_request(
    request: Request,
    request_id: str,
    payload: PlatformPaymentRequestReview,
) -> dict:
    """Approve a pending manual payment request and grant credits."""
    _require_admin_token(request)
    try:
        result = commerce_store.review_payment_request(
            request_id=request_id,
            decision="approved",
            note=payload.note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result


@router.post("/api/platform/admin/payment-requests/{request_id}/reject", include_in_schema=False)
async def platform_admin_reject_payment_request(
    request: Request,
    request_id: str,
    payload: PlatformPaymentRequestReview,
) -> dict:
    """Reject a pending manual payment request without granting credits."""
    _require_admin_token(request)
    try:
        result = commerce_store.review_payment_request(
            request_id=request_id,
            decision="rejected",
            note=payload.note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result


@router.post("/api/platform/alerts/preferences", include_in_schema=False)
async def platform_alert_preferences(request: Request, payload: PlatformAlertPreferenceUpdate) -> dict:
    """Persist alert notification preferences for the authenticated user."""
    user = _require_session_user(request)
    account = commerce_store.update_alert_preferences(
        account_id=user["id"],
        preferences=payload.preferences,
    )
    return {
        "authenticated": True,
        "user": user,
        "account": account,
        "catalog": commerce_store.catalog(),
    }
