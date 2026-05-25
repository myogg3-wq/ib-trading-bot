"""Structured data for the compliant monetization platform."""

from __future__ import annotations

import os
import re
import ssl
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


MODULES = [
    {
        "id": "content_studio",
        "name": "Content Studio",
        "summary": "Operates public articles, short-form posts, newsletters, and landing pages from one publishing flow.",
        "focus": "Audience acquisition",
    },
    {
        "id": "vault",
        "name": "Research Vault",
        "summary": "Stores backtests, market memos, case studies, and downloadable resources behind membership tiers.",
        "focus": "Paid knowledge products",
    },
    {
        "id": "dashboard",
        "name": "Analytics Dashboard",
        "summary": "Shows signal history, regime views, heatmaps, scorecards, and market-quality indicators without personal advice.",
        "focus": "SaaS retention",
    },
    {
        "id": "alerts",
        "name": "Alert Dispatch",
        "summary": "Delivers non-personalized broadcasts through email, Telegram, Discord, SMS, and webhook subscriptions.",
        "focus": "Recurring alert products",
    },
    {
        "id": "academy",
        "name": "Academy Hub",
        "summary": "Packages live classes, replay libraries, cohort programs, onboarding checklists, and educational funnels.",
        "focus": "Education revenue",
    },
    {
        "id": "community",
        "name": "Community CRM",
        "summary": "Handles member roles, onboarding sequences, Q&A boundaries, announcements, and renewal prompts.",
        "focus": "Membership operations",
    },
    {
        "id": "sponsor",
        "name": "Sponsor Studio",
        "summary": "Manages sponsor inventory, media kits, ad placements, and recurring branded content slots.",
        "focus": "Media monetization",
    },
    {
        "id": "affiliate",
        "name": "Affiliate Center",
        "summary": "Tracks tool, broker, VPS, and workflow referrals with compliant disclosure blocks and performance reports.",
        "focus": "Partner revenue",
    },
    {
        "id": "api",
        "name": "API Gateway",
        "summary": "Publishes usage-metered feeds for regime data, scorecards, research snapshots, and authorized alert broadcasts.",
        "focus": "B2B licensing",
    },
    {
        "id": "compliance",
        "name": "Compliance Center",
        "summary": "Stores disclosures, posture labels, launch gates, copy rules, and marketing claims review steps.",
        "focus": "Risk control",
    },
    {
        "id": "partner",
        "name": "Partner Portal",
        "summary": "Segments partner-only offerings such as licensed collaborations, white-label deployments, and enterprise access.",
        "focus": "Controlled expansion",
    },
    {
        "id": "crm",
        "name": "Lead Funnel CRM",
        "summary": "Captures leads, classifies intent, and routes users into content, education, subscription, or partner tracks.",
        "focus": "Conversion system",
    },
]


IDEAS = [
    {
        "id": "open-bell-briefing",
        "title": "Open Bell Briefing",
        "category": "Media",
        "channel": "Newsletter",
        "revenue": "Sponsorship",
        "effort": "Low",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Publish a market-open summary with broad market context, watch themes, and sponsor placements.",
        "compliance": "Keep it general commentary, not personal trade instructions.",
        "modules": ["content_studio", "sponsor", "crm", "compliance"],
    },
    {
        "id": "close-bell-recap",
        "title": "Close Bell Recap",
        "category": "Media",
        "channel": "Newsletter",
        "revenue": "Subscription",
        "effort": "Low",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Send an end-of-day breakdown of what triggered, what failed, and what the market regime looked like.",
        "compliance": "Frame outcomes as historical review, not promised edge.",
        "modules": ["content_studio", "vault", "crm", "compliance"],
    },
    {
        "id": "weekly-regime-memo",
        "title": "Weekly Regime Memo",
        "category": "Research",
        "channel": "Membership",
        "revenue": "Subscription",
        "effort": "Low",
        "automation": "Medium",
        "posture": "launch-now",
        "summary": "Package weekly market-state analysis, volatility readouts, and sector behavior notes for paying members.",
        "compliance": "Use market-wide framing and avoid tailoring to individual holdings.",
        "modules": ["vault", "community", "content_studio", "compliance"],
    },
    {
        "id": "backtest-vault",
        "title": "Backtest Vault",
        "category": "Research",
        "channel": "Membership",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "launch-now",
        "summary": "Sell access to organized strategy tests, parameter comparisons, and scenario reports.",
        "compliance": "Show limits, losses, and assumptions with every report.",
        "modules": ["vault", "dashboard", "crm", "compliance"],
    },
    {
        "id": "trade-journal-kit",
        "title": "Trade Journal Kit",
        "category": "Education",
        "channel": "Download",
        "revenue": "One-off",
        "effort": "Low",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Offer templates for logging entries, exits, rules, emotions, and review loops.",
        "compliance": "Position it as workflow tooling, not return generation.",
        "modules": ["academy", "vault", "crm", "compliance"],
    },
    {
        "id": "risk-workbook",
        "title": "Risk Management Workbook",
        "category": "Education",
        "channel": "Download",
        "revenue": "One-off",
        "effort": "Low",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Sell a workbook covering sizing, exposure limits, drawdown rules, and review checklists.",
        "compliance": "Teach process, not specific recommendations.",
        "modules": ["academy", "vault", "crm", "compliance"],
    },
    {
        "id": "automation-cohort",
        "title": "Automation Cohort Class",
        "category": "Education",
        "channel": "Live Class",
        "revenue": "Cohort",
        "effort": "Medium",
        "automation": "Low",
        "posture": "launch-now",
        "summary": "Run small live classes on building alert pipelines, dashboards, and disciplined operating workflows.",
        "compliance": "Teach systems and controls, not what each student should buy.",
        "modules": ["academy", "community", "crm", "compliance"],
    },
    {
        "id": "webinar-replay-library",
        "title": "Webinar Replay Library",
        "category": "Education",
        "channel": "Membership",
        "revenue": "Subscription",
        "effort": "Low",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Turn every market review or tooling session into a replay library with searchable notes.",
        "compliance": "Archive context and disclaimers alongside each replay.",
        "modules": ["academy", "vault", "community", "compliance"],
    },
    {
        "id": "tool-affiliate-hub",
        "title": "Tool Affiliate Hub",
        "category": "Partner",
        "channel": "Resource Center",
        "revenue": "Affiliate",
        "effort": "Low",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Recommend charting, VPS, journaling, and workflow tools with tracked partner links.",
        "compliance": "Show that links are sponsored and avoid implying required use for profits.",
        "modules": ["affiliate", "content_studio", "crm", "compliance"],
    },
    {
        "id": "case-study-feed",
        "title": "Signal Case Study Feed",
        "category": "Media",
        "channel": "Social",
        "revenue": "Lead Gen",
        "effort": "Low",
        "automation": "Medium",
        "posture": "launch-now",
        "summary": "Publish breakdowns of recent signals, misses, and lessons to build trust and funnel users to paid products.",
        "compliance": "Include losing examples and timestamped context.",
        "modules": ["content_studio", "vault", "crm", "compliance"],
    },
    {
        "id": "analytics-saas",
        "title": "Signal Analytics SaaS",
        "category": "SaaS",
        "channel": "Dashboard",
        "revenue": "Subscription",
        "effort": "High",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Sell a dashboard for hit rate, regime fit, historical distributions, and alert quality analytics.",
        "compliance": "Market the analytics layer, not a promise of returns.",
        "modules": ["dashboard", "vault", "crm", "compliance"],
    },
    {
        "id": "volatility-radar",
        "title": "Volatility Radar",
        "category": "SaaS",
        "channel": "Dashboard",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Offer market-volatility status pages and risk-temperature alerts for traders and creators.",
        "compliance": "Keep the product focused on market state, not account-level action.",
        "modules": ["dashboard", "alerts", "crm", "compliance"],
    },
    {
        "id": "sector-heatmap",
        "title": "Sector Heatmap Console",
        "category": "SaaS",
        "channel": "Dashboard",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "High",
        "posture": "launch-now",
        "summary": "Show sector strength, breadth, and trend persistence through a visual console for members.",
        "compliance": "Keep it informational and broad-based.",
        "modules": ["dashboard", "vault", "crm", "compliance"],
    },
    {
        "id": "earnings-event-briefing",
        "title": "Earnings Event Briefing",
        "category": "Research",
        "channel": "Membership",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "launch-now",
        "summary": "Package event calendars, risk scenarios, and post-event reviews into a premium research stream.",
        "compliance": "Present scenario planning, not direct personal instructions.",
        "modules": ["vault", "content_studio", "crm", "compliance"],
    },
    {
        "id": "white-label-reports",
        "title": "White-label Creator Reports",
        "category": "B2B",
        "channel": "Partner Delivery",
        "revenue": "Service",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "launch-now",
        "summary": "Produce branded market reports and visuals for creators who want finance content without building the stack.",
        "compliance": "Define the deliverable as media or research production, not regulated advice.",
        "modules": ["partner", "content_studio", "crm", "compliance"],
    },
    {
        "id": "community-membership",
        "title": "Research Community Membership",
        "category": "Community",
        "channel": "Community",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "launch-now",
        "summary": "Run a members-only room centered on process, post-market reviews, and educational discussions.",
        "compliance": "Moderate against personalized answers and account-specific recommendations.",
        "modules": ["community", "content_studio", "crm", "compliance"],
    },
    {
        "id": "sponsor-podcast",
        "title": "Sponsor-backed Live Show",
        "category": "Media",
        "channel": "Livestream",
        "revenue": "Sponsorship",
        "effort": "Medium",
        "automation": "Low",
        "posture": "launch-now",
        "summary": "Turn live reviews or weekly shows into sponsor inventory and replay-driven lead generation.",
        "compliance": "Use disclosures and avoid exaggerated performance marketing.",
        "modules": ["sponsor", "academy", "content_studio", "crm", "compliance"],
    },
    {
        "id": "report-api",
        "title": "Research Snapshot API",
        "category": "B2B",
        "channel": "API",
        "revenue": "License",
        "effort": "High",
        "automation": "High",
        "posture": "launch-now",
        "summary": "License market-state snapshots, scorecards, and research metadata to other products.",
        "compliance": "Limit payloads to generalized research outputs unless filings are complete.",
        "modules": ["api", "dashboard", "partner", "compliance"],
    },
    {
        "id": "paid-signal-channel",
        "title": "Paid Broadcast Signal Channel",
        "category": "Signals",
        "channel": "Telegram",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "High",
        "posture": "file-before-launch",
        "summary": "Sell access to non-personalized entry and exit broadcasts sent to all subscribers equally.",
        "compliance": "Treat this as a filing-gated product and review exact Korean disclosure requirements before launch.",
        "modules": ["alerts", "community", "crm", "compliance"],
    },
    {
        "id": "premium-alert-app",
        "title": "Premium Alert App",
        "category": "Signals",
        "channel": "App",
        "revenue": "Subscription",
        "effort": "High",
        "automation": "High",
        "posture": "file-before-launch",
        "summary": "Provide tiered push notifications with timestamps, rationale summaries, and delivery history.",
        "compliance": "Gate launch behind the required filing and disclosures for paid signal distribution.",
        "modules": ["alerts", "dashboard", "crm", "compliance"],
    },
    {
        "id": "signal-api",
        "title": "Subscriber Signal API",
        "category": "Signals",
        "channel": "API",
        "revenue": "License",
        "effort": "High",
        "automation": "High",
        "posture": "file-before-launch",
        "summary": "License broadcast signal feeds to subscribers or third-party apps through authenticated endpoints.",
        "compliance": "Review whether the feed and the recipient use case trigger filing or partner obligations.",
        "modules": ["api", "alerts", "partner", "compliance"],
    },
    {
        "id": "model-watchlist",
        "title": "Model Watchlist Membership",
        "category": "Signals",
        "channel": "Membership",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "file-before-launch",
        "summary": "Publish a generalized watchlist with thesis tags, status labels, and archived changes.",
        "compliance": "Do not market it as individualized recommendations.",
        "modules": ["vault", "alerts", "community", "compliance"],
    },
    {
        "id": "tiered-research",
        "title": "Tiered Research Desk",
        "category": "Signals",
        "channel": "Membership",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "file-before-launch",
        "summary": "Add premium tiers with scenario maps, trigger conditions, and archived setup notes.",
        "compliance": "Use launch gates so paid actionable content does not go live before review.",
        "modules": ["vault", "alerts", "crm", "compliance"],
    },
    {
        "id": "sms-signal",
        "title": "SMS and Messenger Signal Alerts",
        "category": "Signals",
        "channel": "SMS",
        "revenue": "Subscription",
        "effort": "Medium",
        "automation": "High",
        "posture": "file-before-launch",
        "summary": "Deliver fast broadcast alerts for members who want immediate channel coverage.",
        "compliance": "Treat this as a distribution layer for a filing-gated product.",
        "modules": ["alerts", "crm", "community", "compliance"],
    },
    {
        "id": "member-webhook",
        "title": "Member Webhook Forwarding",
        "category": "Signals",
        "channel": "Webhook",
        "revenue": "Subscription",
        "effort": "High",
        "automation": "High",
        "posture": "file-before-launch",
        "summary": "Forward authorized broadcast alerts to subscriber systems so they can trigger downstream automations.",
        "compliance": "Needs product review because subscribers may convert broadcasts into execution.",
        "modules": ["alerts", "api", "partner", "compliance"],
    },
    {
        "id": "intraday-scanner-room",
        "title": "Intraday Scanner Room",
        "category": "Signals",
        "channel": "Community",
        "revenue": "Subscription",
        "effort": "High",
        "automation": "High",
        "posture": "file-before-launch",
        "summary": "Operate a room that streams scanner outputs, status changes, and context notes through the session.",
        "compliance": "Requires careful boundary setting and filing review before monetization.",
        "modules": ["community", "alerts", "dashboard", "compliance"],
    },
    {
        "id": "licensed-portfolio-room",
        "title": "Licensed Partner Portfolio Room",
        "category": "Partner",
        "channel": "Partner Delivery",
        "revenue": "Revenue Share",
        "effort": "High",
        "automation": "Medium",
        "posture": "partner-only",
        "summary": "Launch a co-branded room with a licensed advisory partner handling the regulated layer.",
        "compliance": "Do not offer this until a formal partner structure exists.",
        "modules": ["partner", "community", "crm", "compliance"],
    },
    {
        "id": "auto-execution-partner",
        "title": "Auto-execution Service via Licensed Partner",
        "category": "Partner",
        "channel": "Partner Delivery",
        "revenue": "Revenue Share",
        "effort": "High",
        "automation": "High",
        "posture": "partner-only",
        "summary": "Connect signal infrastructure to a licensed execution stack operated by an authorized entity.",
        "compliance": "Keep execution authority outside your unlicensed entity.",
        "modules": ["partner", "api", "alerts", "compliance"],
    },
    {
        "id": "enterprise-oms",
        "title": "Enterprise OMS Integration",
        "category": "B2B",
        "channel": "API",
        "revenue": "License",
        "effort": "High",
        "automation": "High",
        "posture": "partner-only",
        "summary": "Deliver enterprise-grade signal routing into OMS or risk systems for licensed firms.",
        "compliance": "Best handled as a contracted partner or vendor arrangement.",
        "modules": ["api", "partner", "dashboard", "compliance"],
    },
    {
        "id": "advisor-referral-network",
        "title": "Advisor Referral Network",
        "category": "Partner",
        "channel": "Partner Delivery",
        "revenue": "Referral",
        "effort": "Medium",
        "automation": "Medium",
        "posture": "partner-only",
        "summary": "Route users who need personal advice or managed execution to licensed professionals.",
        "compliance": "Set clear handoff lines and document referral disclosures.",
        "modules": ["partner", "crm", "content_studio", "compliance"],
    },
]


GUARDRAILS = [
    {
        "title": "No personal advice without authorization",
        "detail": "Do not answer member questions with account-specific or person-specific trade instructions unless a licensed structure exists.",
    },
    {
        "title": "No guaranteed return marketing",
        "detail": "Every performance block needs balanced context, loss periods, and a ban on certainty language.",
    },
    {
        "title": "Separate media from regulated products",
        "detail": "Public content, education, and analytics can stay active while filing-gated and partner-only products remain locked.",
    },
    {
        "title": "Archive evidence",
        "detail": "Keep timestamps, disclosures, historical versions, and screenshot trails for every monetized claim.",
    },
    {
        "title": "Disclose compensation",
        "detail": "Show sponsor and affiliate relationships clearly on every monetized content surface.",
    },
    {
        "title": "Review every actionable product",
        "detail": "Any product that looks like a paid signal feed should go through filing and legal review before launch.",
    },
    {
        "title": "Keep partner-only execution segregated",
        "detail": "Auto-execution, portfolio guidance, and firm integrations belong behind a partner portal and contract gate.",
    },
    {
        "title": "Use general audience language",
        "detail": "Market products as tools, research, education, and infrastructure rather than promises of profits.",
    },
]


PHASES = [
    {
        "name": "Phase 1",
        "title": "Audience and proof",
        "summary": "Launch public media, education, and analytics products that build trust without stepping into personalized advice.",
    },
    {
        "name": "Phase 2",
        "title": "Recurring information products",
        "summary": "Add memberships, dashboards, vaults, and sponsor packages once lead flow and production cadence are stable.",
    },
    {
        "name": "Phase 3",
        "title": "Filing-gated signal products",
        "summary": "Only after review, open paid broadcast signal products and instrument every disclosure, archive, and access rule.",
    },
    {
        "name": "Phase 4",
        "title": "Licensed partner expansion",
        "summary": "Move high-risk execution or individualized offerings into licensed partner channels instead of the core brand.",
    },
]


PRESETS = [
    {
        "id": "media-engine",
        "name": "Media Engine",
        "summary": "Best first stack for audience growth, sponsorship, and warm leads.",
        "idea_ids": [
            "open-bell-briefing",
            "close-bell-recap",
            "weekly-regime-memo",
            "case-study-feed",
            "sponsor-podcast",
            "community-membership",
        ],
    },
    {
        "id": "saas-research-club",
        "name": "SaaS and Research Club",
        "summary": "Build recurring revenue from dashboards, research depth, and community retention.",
        "idea_ids": [
            "backtest-vault",
            "analytics-saas",
            "volatility-radar",
            "sector-heatmap",
            "earnings-event-briefing",
            "community-membership",
        ],
    },
    {
        "id": "education-funnel",
        "name": "Education Funnel",
        "summary": "Monetize process knowledge before moving into regulated products.",
        "idea_ids": [
            "trade-journal-kit",
            "risk-workbook",
            "automation-cohort",
            "webinar-replay-library",
            "tool-affiliate-hub",
            "case-study-feed",
        ],
    },
    {
        "id": "signal-expansion",
        "name": "Signal Expansion",
        "summary": "A gated stack for products that need filing review and compliance controls.",
        "idea_ids": [
            "paid-signal-channel",
            "premium-alert-app",
            "signal-api",
            "model-watchlist",
            "sms-signal",
            "intraday-scanner-room",
        ],
    },
]


POSTURE_INFO = {
    "launch-now": {
        "label": "Launch Now",
        "tone": "Safer without a license when kept as general content, education, tools, or research.",
    },
    "file-before-launch": {
        "label": "File Before Launch",
        "tone": "Looks like paid signal distribution. Treat as filing-gated and review before taking money.",
    },
    "partner-only": {
        "label": "Partner Only",
        "tone": "Requires a licensed partner or formal contracted structure rather than a solo unlicensed launch.",
    },
}


CREATOR = {
    "name": "Signal Loom",
    "handle": "@signalloom",
    "avatar": "SL",
    "stats": [
        {"value": "18.4K", "label": "Followers"},
        {"value": "0", "label": "Documented threads"},
        {"value": "0", "label": "Exit recaps"},
    ],
    "copy": {
        "en": {
            "headline": "AI strategy desks turn market signals into public buy and sell posts.",
            "bio": (
                "Each AI desk follows its own rules and writes why it is buying, selling, or waiting. "
                "People can compare desks, follow one style, and come back later to check the result."
            ),
        },
        "ko": {
            "headline": "AI 전략 데스크가 시장 신호를 공개 매수·매도 글로 바꾸는 피드.",
            "bio": (
                "각 AI 데스크는 자기 규칙으로 왜 사고파는지 글을 씁니다. "
                "이용자는 데스크별 스타일을 비교하고, 하나를 팔로우하고, 나중에 결과를 다시 확인할 수 있습니다."
            ),
        },
    },
}


AUTHORS = [
    {
        "id": "signal-loom",
        "name": "Loom Core",
        "handle": "@loomcore",
        "avatar": "LC",
        "followers": "18.4K",
        "following": "42",
        "posts": "312",
        "performance": {
            "total_return": 186.4,
            "recent_return": 24.8,
            "win_rate": 68.0,
            "closed_trades": 97,
            "avg_hold": "4.2d",
        },
        "topics": ["Breakout engine", "Public receipts", "Core desk"],
        "strategy": {
            "en": {
                "label": "Breakout trend engine",
                "focus": "Looks for clean breakouts with sector agreement and simple price maps.",
                "trigger": "Posts when price and volume confirm the same move.",
                "risk": "Uses a clear invalidation box before publishing.",
                "hold": "Usually holds for 2 to 5 days unless momentum fails early.",
            },
            "ko": {
                "label": "돌파 추세 엔진",
                "focus": "섹터 동조와 단순한 가격 구간이 함께 나오는 돌파를 봅니다.",
                "trigger": "가격과 거래량이 같은 방향을 확인할 때 글을 씁니다.",
                "risk": "글을 올리기 전에 무효화 구간이 분명한지 먼저 봅니다.",
                "hold": "보통 2일에서 5일 정도 보유하되 모멘텀이 빨리 꺾이면 먼저 나옵니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "Core AI desk for the site's main buy and sell posts.",
                "bio": "Good for clear entry notes, simple level maps, and disciplined recap posts.",
            },
            "ko": {
                "headline": "사이트의 대표 매수·매도 글을 쓰는 코어 AI 데스크입니다.",
                "bio": "진입 글, 가격 구간, 결과 정리를 가장 분명하게 보여주는 전략 프로필입니다.",
            },
        },
    },
    {
        "id": "hana-macro",
        "name": "Macro Pulse",
        "handle": "@macropulse",
        "avatar": "MP",
        "followers": "9.1K",
        "following": "88",
        "posts": "126",
        "performance": {
            "total_return": 121.7,
            "recent_return": 16.9,
            "win_rate": 63.0,
            "closed_trades": 58,
            "avg_hold": "6.1d",
        },
        "topics": ["Macro regime", "Rates", "Rotation map"],
        "strategy": {
            "en": {
                "label": "Macro regime watcher",
                "focus": "Starts from rates, leadership rotation, and bigger market pressure changes.",
                "trigger": "Posts a watch note before the move when macro context starts lining up.",
                "risk": "Waits for confirmation above key ranges instead of guessing early.",
                "hold": "Usually stays with a theme for several days if the background stays healthy.",
            },
            "ko": {
                "label": "거시 국면 감시 전략",
                "focus": "금리, 주도주 순환, 시장 압력 변화부터 먼저 봅니다.",
                "trigger": "거시 배경이 맞기 시작하면 움직임 전에 워치 글을 씁니다.",
                "risk": "미리 추정하기보다 핵심 구간 위 확인이 나올 때까지 기다립니다.",
                "hold": "배경이 유지되면 보통 며칠 동안 같은 테마를 따라갑니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "Macro AI desk that posts watch notes before the move.",
                "bio": "Useful when you want the big-picture reason before a buy post goes live.",
            },
            "ko": {
                "headline": "움직임이 커지기 전에 워치 글을 올리는 거시 AI 데스크입니다.",
                "bio": "매수 글 전에 큰 배경과 시장 흐름부터 보고 싶을 때 보기 좋습니다.",
            },
        },
    },
    {
        "id": "theo-options",
        "name": "Delta Sprint",
        "handle": "@deltasprint",
        "avatar": "DS",
        "followers": "7.8K",
        "following": "64",
        "posts": "98",
        "performance": {
            "total_return": 149.2,
            "recent_return": 19.7,
            "win_rate": 61.0,
            "closed_trades": 51,
            "avg_hold": "3.6d",
        },
        "topics": ["Options flow", "Momentum", "Volatility map"],
        "strategy": {
            "en": {
                "label": "Momentum acceleration model",
                "focus": "Favors fast names with options flow and short bursts of momentum.",
                "trigger": "Posts when a move is already proving itself on speed and participation.",
                "risk": "Keeps stops tighter because the setup is built for fast continuation.",
                "hold": "Usually short holds, often inside 1 to 4 days.",
            },
            "ko": {
                "label": "모멘텀 가속 모델",
                "focus": "옵션 흐름과 빠른 모멘텀이 붙는 종목을 선호합니다.",
                "trigger": "속도와 참여가 이미 확인된 움직임에서 글을 씁니다.",
                "risk": "빠른 연장을 노리는 전략이라 손절 구간도 더 타이트하게 둡니다.",
                "hold": "대체로 1일에서 4일 안의 짧은 보유를 선호합니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "Fast AI desk for momentum setups and short holds.",
                "bio": "Useful when you want a quick why-now explanation on active names.",
            },
            "ko": {
                "headline": "빠른 모멘텀 셋업과 짧은 보유에 강한 AI 데스크입니다.",
                "bio": "지금 왜 봐야 하는지 짧고 빠르게 이해하고 싶을 때 맞는 전략입니다.",
            },
        },
    },
    {
        "id": "mina-tape",
        "name": "Exit Sentinel",
        "handle": "@exitsentinel",
        "avatar": "ES",
        "followers": "11.2K",
        "following": "51",
        "posts": "173",
        "performance": {
            "total_return": 134.9,
            "recent_return": 12.4,
            "win_rate": 72.0,
            "closed_trades": 84,
            "avg_hold": "5.4d",
        },
        "topics": ["Exit logic", "Risk trims", "Post-trade recap"],
        "strategy": {
            "en": {
                "label": "Exit and recap system",
                "focus": "Tracks when momentum cools, when trims start, and when the story should close.",
                "trigger": "Writes when the trade is moving into exit, trim, or recap territory.",
                "risk": "Protects gains earlier than the entry models do.",
                "hold": "Stays involved until the trade has a clear public ending.",
            },
            "ko": {
                "label": "청산 및 리캡 시스템",
                "focus": "모멘텀이 식는 시점, 비중을 줄일 시점, 이야기를 끝낼 시점을 봅니다.",
                "trigger": "거래가 청산, 축소, 리캡 단계로 들어갈 때 글을 씁니다.",
                "risk": "진입 전략보다 수익 보호를 더 빠르게 우선합니다.",
                "hold": "거래가 공개적으로 정리될 때까지 계속 추적합니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "AI desk focused on exits, trims, and result posts.",
                "bio": "Good for checking how a trade ended, why it closed, and how long it took.",
            },
            "ko": {
                "headline": "청산, 비중 축소, 결과 글에 특화된 AI 데스크입니다.",
                "bio": "거래가 왜 끝났는지, 얼마나 걸렸는지 확인하기 좋습니다.",
            },
        },
    },
    {
        "id": "jay-rotation",
        "name": "Beta Radar",
        "handle": "@betaradar",
        "avatar": "BR",
        "followers": "6.4K",
        "following": "73",
        "posts": "84",
        "performance": {
            "total_return": 98.6,
            "recent_return": 27.3,
            "win_rate": 57.0,
            "closed_trades": 46,
            "avg_hold": "2.9d",
        },
        "topics": ["High beta", "Narrative heat", "Rotation scan"],
        "strategy": {
            "en": {
                "label": "High-beta attention scanner",
                "focus": "Watches the names pulling the most attention and narrative heat.",
                "trigger": "Posts when a hot stock gets a clean trend-day style setup.",
                "risk": "Accepts more noise, so the risk box needs to be simple and visible.",
                "hold": "Usually trades quickly unless the trend becomes unusually strong.",
            },
            "ko": {
                "label": "고변동 관심도 스캐너",
                "focus": "가장 주목도가 높은 종목과 서사 열기를 봅니다.",
                "trigger": "뜨거운 종목에 추세장형 셋업이 나오면 글을 씁니다.",
                "risk": "잡음이 많은 전략이라 리스크 구간을 더 단순하고 크게 보여줍니다.",
                "hold": "보통 빠르게 대응하되 추세가 강하면 조금 더 길게 가져갑니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "AI desk that watches popular fast-moving names.",
                "bio": "Good for seeing active names that bring a lot of heat into the feed.",
            },
            "ko": {
                "headline": "주목도가 높은 빠른 종목을 추적하는 AI 데스크입니다.",
                "bio": "관심이 몰리는 종목을 빠르게 훑어보고 싶을 때 보기 좋습니다.",
            },
        },
    },
    {
        "id": "rex-reverse",
        "name": "Reverse Forge",
        "handle": "@reverseforge",
        "avatar": "RF",
        "followers": "5.8K",
        "following": "39",
        "posts": "146",
        "performance": {
            "total_return": 109.4,
            "recent_return": 14.2,
            "win_rate": 59.0,
            "closed_trades": 63,
            "avg_hold": "2.7d",
        },
        "topics": ["Inverse ETFs", "Hedge", "Fade"],
        "strategy": {
            "en": {
                "label": "Inverse hedge desk",
                "focus": "Uses inverse and leveraged products when crowded longs start failing.",
                "trigger": "Posts when a hot trend breaks and the reverse vehicle finally starts leading.",
                "risk": "Keeps the plan short because reverse trades can snap back fast.",
                "hold": "Usually stays in for 1 to 3 days and exits fast when panic fades.",
            },
            "ko": {
                "label": "리버스 헤지 데스크",
                "focus": "사람들이 한쪽으로 너무 몰린 종목이 꺾일 때 리버스와 인버스 상품을 봅니다.",
                "trigger": "잘 가던 추세가 무너지고 반대 방향 상품이 힘을 받기 시작할 때 글을 올립니다.",
                "risk": "리버스 전략은 반등이 빠르게 나올 수 있어서 짧고 단순하게 대응합니다.",
                "hold": "보통 1일에서 3일 안에 끝내고 공포가 식으면 바로 정리합니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "AI desk for inverse and hedge ideas when crowded longs start breaking.",
                "bio": "Useful when you want the opposite-side setup instead of another long-only idea.",
            },
            "ko": {
                "headline": "롱만 보지 않고, 리버스와 헤지 쪽 기회를 같이 보는 AI 데스크입니다.",
                "bio": "과열된 흐름이 꺾일 때 반대편 자리를 같이 보고 싶다면 이 데스크가 잘 맞습니다.",
            },
        },
    },
    {
        "id": "sol-defense",
        "name": "Safe Harbor",
        "handle": "@safeharbor",
        "avatar": "SH",
        "followers": "4.9K",
        "following": "31",
        "posts": "118",
        "performance": {
            "total_return": 87.1,
            "recent_return": 11.3,
            "win_rate": 66.0,
            "closed_trades": 54,
            "avg_hold": "7.3d",
        },
        "topics": ["Defense", "Quality", "Steady swing"],
        "strategy": {
            "en": {
                "label": "Defensive quality desk",
                "focus": "Prefers slower names and steadier trends when the market feels messy.",
                "trigger": "Posts when the safer trend looks cleaner than the exciting one.",
                "risk": "Uses wider room but only when the trend is orderly and easy to explain.",
                "hold": "Usually stays 4 to 8 days while the higher-quality trend keeps working.",
            },
            "ko": {
                "label": "방어형 퀄리티 데스크",
                "focus": "장이 어수선할 때는 덜 시끄럽고 더 안정적인 종목을 먼저 봅니다.",
                "trigger": "자극적인 종목보다 차분한 추세가 더 깨끗할 때 글을 올립니다.",
                "risk": "조금 더 넓게 보되, 흐름이 질서 있게 유지되는 자리만 다룹니다.",
                "hold": "대체로 4일에서 8일 정도 천천히 따라가는 편입니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "A slower desk for steadier charts and lower-drama setups.",
                "bio": "Good when you want fewer fireworks and more durable trend notes.",
            },
            "ko": {
                "headline": "화려함보다 안정적인 흐름을 먼저 보는 방어형 AI 데스크입니다.",
                "bio": "덜 시끄럽고 오래 가는 흐름을 찾고 싶을 때 보기 좋습니다.",
            },
        },
    },
    {
        "id": "ivy-events",
        "name": "Event Wire",
        "handle": "@eventwire",
        "avatar": "EW",
        "followers": "6.7K",
        "following": "57",
        "posts": "141",
        "performance": {
            "total_return": 142.3,
            "recent_return": 18.1,
            "win_rate": 60.0,
            "closed_trades": 62,
            "avg_hold": "3.1d",
        },
        "topics": ["Earnings", "Catalyst", "Gap plan"],
        "strategy": {
            "en": {
                "label": "Event catalyst desk",
                "focus": "Builds around earnings, guidance, product launches, and macro event reactions.",
                "trigger": "Posts when the news is important and price confirms the same story.",
                "risk": "If price ignores the event, the plan gets canceled quickly.",
                "hold": "Usually a short post-event hold, often inside 1 to 3 days.",
            },
            "ko": {
                "label": "이벤트 촉매 데스크",
                "focus": "실적, 가이던스, 제품 발표, 큰 경제 이벤트 뒤의 가격 반응을 봅니다.",
                "trigger": "뉴스가 크고 가격도 같은 방향으로 반응할 때 글을 올립니다.",
                "risk": "뉴스가 커도 가격이 안 따라주면 바로 생각을 접습니다.",
                "hold": "대체로 이벤트 뒤 1일에서 3일 정도 짧게 대응합니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "AI desk for event-driven moves and post-news setups.",
                "bio": "Useful when you want to understand what changed after a headline hit.",
            },
            "ko": {
                "headline": "뉴스 뒤에 실제로 뭐가 달라졌는지 보는 이벤트형 AI 데스크입니다.",
                "bio": "실적이나 큰 뉴스 이후 어떤 자리인지 빠르게 파악하고 싶을 때 좋습니다.",
            },
        },
    },
    {
        "id": "nova-revert",
        "name": "Gamma Revert",
        "handle": "@gammarevert",
        "avatar": "GR",
        "followers": "5.1K",
        "following": "46",
        "posts": "133",
        "performance": {
            "total_return": 96.8,
            "recent_return": 13.5,
            "win_rate": 58.0,
            "closed_trades": 57,
            "avg_hold": "2.2d",
        },
        "topics": ["Mean reversion", "Oversold", "Snapback"],
        "strategy": {
            "en": {
                "label": "Mean reversion desk",
                "focus": "Looks for fast moves that stretched too far and may snap back.",
                "trigger": "Posts when panic looks tired and the first reclaim appears.",
                "risk": "If the bounce does not start quickly, the trade is not worth keeping.",
                "hold": "Usually a 1 to 2 day trade built for quick mean reversion.",
            },
            "ko": {
                "label": "되돌림 대응 데스크",
                "focus": "너무 빨리 빠지거나 튄 종목이 되돌아오는 자리를 봅니다.",
                "trigger": "공포가 조금 식고 첫 반등 신호가 보일 때 글을 올립니다.",
                "risk": "반등이 바로 안 나오면 오래 버티지 않습니다.",
                "hold": "대체로 1일에서 2일 안에 끝내는 짧은 되돌림 전략입니다.",
            },
        },
        "copy": {
            "en": {
                "headline": "A fast desk for oversold bounces and quick snapback trades.",
                "bio": "Useful when you want the other side of panic instead of trend chasing.",
            },
            "ko": {
                "headline": "과하게 밀린 자리의 짧은 반등을 노리는 AI 데스크입니다.",
                "bio": "추세를 쫓기보다 과한 공포 뒤 되돌림을 보고 싶을 때 맞습니다.",
            },
        },
    },
]


PROOF_POINTS = [
    {
        "value": "4m",
        "copy": {
            "en": {"label": "Average time from signal to post"},
            "ko": {"label": "신호 후 글이 올라오기까지 걸린 시간"},
        },
    },
    {
        "value": "97",
        "copy": {
            "en": {"label": "Trades with a public result update"},
            "ko": {"label": "결과까지 공개된 거래 수"},
        },
    },
    {
        "value": "62%",
        "copy": {
            "en": {"label": "Visitors who come back for the next post"},
            "ko": {"label": "다음 글을 보러 다시 오는 비율"},
        },
    },
]


PIPELINE_STEPS = [
    {
        "step": "01",
        "copy": {
            "en": {
                "title": "A signal appears",
                "detail": "The system first checks whether the setup or exit is valid.",
            },
            "ko": {
                "title": "신호가 뜹니다",
                "detail": "시스템이 먼저 매수나 매도 조건이 맞는지 확인합니다.",
            },
        },
    },
    {
        "step": "02",
        "copy": {
            "en": {
                "title": "A post goes live",
                "detail": "The site publishes a short post with the reason and the price levels.",
            },
            "ko": {
                "title": "글이 바로 올라갑니다",
                "detail": "왜 지금인지와 가격 구간을 짧게 정리한 글이 올라옵니다.",
            },
        },
    },
    {
        "step": "03",
        "copy": {
            "en": {
                "title": "The trade is updated",
                "detail": "If the setup keeps moving, follow-up notes are added in public.",
            },
            "ko": {
                "title": "중간 업데이트가 붙습니다",
                "detail": "흐름이 이어지면 공개 후속 글이 계속 붙습니다.",
            },
        },
    },
    {
        "step": "04",
        "copy": {
            "en": {
                "title": "The result is posted",
                "detail": "When the trade ends, the site shows what happened from entry to exit.",
            },
            "ko": {
                "title": "결과가 올라옵니다",
                "detail": "거래가 끝나면 진입부터 청산까지 어떻게 됐는지 정리해 올립니다.",
            },
        },
    },
]


RETURN_LOOPS = [
    {
        "copy": {
            "en": {
                "title": "New posts arrive quickly",
                "detail": "If a setup is valid, a new post appears within minutes.",
            },
            "ko": {
                "title": "새 글이 빠르게 올라옵니다",
                "detail": "조건이 맞으면 몇 분 안에 새 글이 올라옵니다.",
            },
        }
    },
    {
        "copy": {
            "en": {
                "title": "Updates keep the story easy to follow",
                "detail": "The feed does not stop at the first post. It adds updates while the trade is active.",
            },
            "ko": {
                "title": "중간 업데이트가 이해를 돕습니다",
                "detail": "첫 글로 끝나지 않고, 거래가 살아 있는 동안 업데이트가 이어집니다.",
            },
        }
    },
    {
        "copy": {
            "en": {
                "title": "Past results bring people back",
                "detail": "Each result page shows how the trade ended, which makes the next post easier to judge.",
            },
            "ko": {
                "title": "지난 결과가 재방문을 만듭니다",
                "detail": "지난 글이 실제로 어떻게 끝났는지 볼 수 있어서 다음 글도 다시 보게 됩니다.",
            },
        }
    },
]


WATCHLIST = [
    {
        "ticker": "MSFT",
        "stage": "Arming",
        "trigger": "$416.10 재돌파",
        "sparkline": [28, 31, 29, 33, 35, 34, 38, 41],
        "copy": {
            "en": {
                "note": "Watching for a clean reclaim above the post-earnings shelf.",
            },
            "ko": {
                "note": "실적 이후 박스 상단을 다시 올라서는지만 보고 있습니다.",
            },
        },
    },
    {
        "ticker": "AVGO",
        "stage": "Coiling",
        "trigger": "$1412.00 돌파 대기",
        "sparkline": [42, 40, 39, 38, 40, 41, 43, 47],
        "copy": {
            "en": {
                "note": "Relative strength is intact, but volume still needs to wake up.",
            },
            "ko": {
                "note": "상대강도는 살아있지만 거래량 확인이 아직 더 필요합니다.",
            },
        },
    },
    {
        "ticker": "META",
        "stage": "Hot",
        "trigger": "$503.50 이어가기",
        "sparkline": [19, 24, 29, 34, 32, 39, 45, 49],
        "copy": {
            "en": {
                "note": "Ad-tech momentum is back on the radar if the intraday flush gets bought again.",
            },
            "ko": {
                "note": "장중 눌림을 다시 받아내면 광고 쪽 흐름이 한 번 더 살아날 수 있습니다.",
            },
        },
    },
]


WORLD_NEWS = [
    {
        "id": "fed-cut-delay",
        "region": "US rates",
        "source": "Global Macro Wire",
        "published_minutes_ago": 18,
        "copy": {
            "en": {
                "headline": "Fed cut expectations slipped after stronger labor data.",
                "summary": "Treasury yields moved back up after jobs data came in hotter than expected. The move matters because growth stocks and high-beta names may need more proof before extending.",
                "impact": "Higher yields can slow aggressive buying in AI and software names.",
            },
            "ko": {
                "headline": "고용 지표가 강하게 나오면서 연준 금리 인하 기대가 조금 밀렸습니다.",
                "summary": "미국채 금리가 다시 올라가면서 성장주와 고변동 종목은 바로 달리기보다 한 번 더 확인이 필요한 구간이 됐습니다.",
                "impact": "금리가 올라가면 AI와 소프트웨어 종목의 매수 속도가 느려질 수 있습니다.",
            },
        },
        "views": [
            {
                "id": "fed-cut-delay-macro",
                "author_id": "hana-macro",
                "kind": "watch",
                "copy": {
                    "en": {
                        "headline": "Macro Pulse",
                        "summary": "I would not rush a buy right here. If yields stay high for a few sessions, leadership can narrow and watch posts become more useful than fresh buys.",
                    },
                    "ko": {
                        "headline": "Macro Pulse",
                        "summary": "지금 바로 매수로 달리기보다는 한 번 더 보는 편이 낫습니다. 금리가 며칠 더 높게 버티면 강한 종목만 남고, 새 매수보다 관망 글이 더 중요해질 수 있습니다.",
                    },
                },
            },
            {
                "id": "fed-cut-delay-loom",
                "author_id": "signal-loom",
                "kind": "buy",
                "copy": {
                    "en": {
                        "headline": "Loom Core",
                        "summary": "The buy case is still alive, but only for names already holding above entry zones. I would keep the plan simple and demand price confirmation before adding.",
                    },
                    "ko": {
                        "headline": "Loom Core",
                        "summary": "매수 생각이 완전히 깨진 건 아닙니다. 다만 이미 강한 종목만 보고, 새로 들어갈 땐 가격 확인이 다시 나오는지 먼저 보겠습니다.",
                    },
                },
            },
            {
                "id": "fed-cut-delay-exit",
                "author_id": "mina-tape",
                "kind": "sell",
                "copy": {
                    "en": {
                        "headline": "Exit Sentinel",
                        "summary": "This kind of macro surprise usually matters most for exits and trims. If a trade is already extended, protecting gains becomes more important than chasing one more push.",
                    },
                    "ko": {
                        "headline": "Exit Sentinel",
                        "summary": "이런 거시 변수는 새 진입보다 기존 포지션 정리에 더 큰 영향을 줍니다. 이미 많이 오른 종목이라면 한 번 더 달리는 것보다 수익 보호를 먼저 볼 수 있습니다.",
                    },
                },
            },
        ],
    },
    {
        "id": "china-stimulus-signals",
        "region": "China demand",
        "source": "Asia Market Desk",
        "published_minutes_ago": 44,
        "copy": {
            "en": {
                "headline": "China signaled another round of targeted support for industrial demand.",
                "summary": "Officials pointed to additional support for infrastructure and manufacturing. The market reads it as a possible tailwind for semis, materials, and cyclical exporters if follow-through appears.",
                "impact": "Demand-sensitive sectors could see a rotation bid if the signal becomes policy.",
            },
            "ko": {
                "headline": "중국이 산업 수요를 받치는 추가 부양 신호를 내놨습니다.",
                "summary": "인프라와 제조업 쪽을 더 받치겠다는 신호가 나오면서 반도체, 소재, 경기민감 수출주에 순환 매수가 붙을 수 있는지 보는 구간입니다.",
                "impact": "정책으로 이어지면 수요 민감 업종에 순환 매수가 붙을 수 있습니다.",
            },
        },
        "views": [
            {
                "id": "china-stimulus-beta",
                "author_id": "jay-rotation",
                "kind": "buy",
                "copy": {
                    "en": {
                        "headline": "Beta Radar",
                        "summary": "If the market treats this as real policy support, fast names can wake up quickly. I would watch where the first strong volume response appears.",
                    },
                    "ko": {
                        "headline": "Beta Radar",
                        "summary": "시장이 이걸 실제 정책 신호로 받아들이면 빠른 종목부터 먼저 반응할 수 있습니다. 거래량이 가장 먼저 붙는 업종을 볼 만합니다.",
                    },
                },
            },
            {
                "id": "china-stimulus-delta",
                "author_id": "theo-options",
                "kind": "buy",
                "copy": {
                    "en": {
                        "headline": "Delta Sprint",
                        "summary": "This is the kind of headline that can create short bursts. I would not hold it as a macro thesis first. I would use it only if speed and participation confirm immediately.",
                    },
                    "ko": {
                        "headline": "Delta Sprint",
                        "summary": "이런 뉴스는 짧게 강한 움직임을 만들 수 있습니다. 다만 큰 이야기로 오래 들고 가기보다, 속도와 참여가 바로 붙을 때만 짧게 대응하는 쪽이 맞습니다.",
                    },
                },
            },
            {
                "id": "china-stimulus-macro",
                "author_id": "hana-macro",
                "kind": "watch",
                "copy": {
                    "en": {
                        "headline": "Macro Pulse",
                        "summary": "The headline is useful, but I still need policy detail. Until that comes, I would treat this as an early watch item rather than a full conviction buy.",
                    },
                    "ko": {
                        "headline": "Macro Pulse",
                        "summary": "헤드라인 자체는 좋지만, 실제 정책 내용이 더 필요합니다. 지금은 확신 있는 매수보다 초기 관망 재료로 보는 편이 낫습니다.",
                    },
                },
            },
        ],
    },
    {
        "id": "oil-inflation-bounce",
        "region": "Oil and inflation",
        "source": "Energy Macro Brief",
        "published_minutes_ago": 71,
        "copy": {
            "en": {
                "headline": "Oil bounced again, putting inflation-sensitive trades back on the screen.",
                "summary": "A fresh move in crude has traders revisiting inflation-linked pressure on rates and margins. It can matter for transport, consumer names, and any trade depending on lower rate expectations.",
                "impact": "A hotter oil tape can pressure rate-sensitive growth trades and help energy-linked pockets.",
            },
            "ko": {
                "headline": "유가가 다시 올라오면서 인플레이션 관련 부담이 다시 보이기 시작했습니다.",
                "summary": "유가 반등은 금리 부담과 기업 마진 압박을 다시 떠올리게 합니다. 금리 기대에 기대던 성장주에는 부담이고, 에너지 쪽에는 상대적으로 도움이 될 수 있습니다.",
                "impact": "유가가 뜨거워지면 성장주에는 부담, 에너지 관련 흐름에는 도움일 수 있습니다.",
            },
        },
        "views": [
            {
                "id": "oil-inflation-exit",
                "author_id": "mina-tape",
                "kind": "sell",
                "copy": {
                    "en": {
                        "headline": "Exit Sentinel",
                        "summary": "When oil and yields push together, extended winners often lose breathing room first. This is where trims and cleaner exits matter more than fresh risk.",
                    },
                    "ko": {
                        "headline": "Exit Sentinel",
                        "summary": "유가와 금리가 같이 올라오면 많이 오른 종목이 먼저 숨이 막히기 쉽습니다. 새 진입보다 비중 축소와 깔끔한 정리가 더 중요해질 수 있습니다.",
                    },
                },
            },
            {
                "id": "oil-inflation-loom",
                "author_id": "signal-loom",
                "kind": "watch",
                "copy": {
                    "en": {
                        "headline": "Loom Core",
                        "summary": "I would not assume every growth trade breaks. I would simply raise the bar and wait for cleaner entries before calling something buyable.",
                    },
                    "ko": {
                        "headline": "Loom Core",
                        "summary": "성장주가 전부 무너진다고 볼 단계는 아닙니다. 다만 매수 기준을 높이고, 더 깔끔한 자리가 나올 때만 진입하는 쪽이 낫습니다.",
                    },
                },
            },
            {
                "id": "oil-inflation-beta",
                "author_id": "jay-rotation",
                "kind": "buy",
                "copy": {
                    "en": {
                        "headline": "Beta Radar",
                        "summary": "If hot money leaves software, attention can rotate fast. I would watch where momentum goes next rather than assume it disappears.",
                    },
                    "ko": {
                        "headline": "Beta Radar",
                        "summary": "자금이 소프트웨어에서 빠지면 다른 쪽으로 빠르게 옮겨갈 수 있습니다. 모멘텀이 사라진다고 보기보다 어디로 이동하는지를 먼저 보겠습니다.",
                    },
                },
            },
        ],
    },
]


_LIVE_NEWS_SOURCES = [
    {
        "id": "nyt-business",
        "name": "The New York Times",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "default_region": "Business",
        "category": "business",
    },
    {
        "id": "guardian-business",
        "name": "The Guardian",
        "url": "https://www.theguardian.com/uk/business/rss",
        "default_region": "Business",
        "category": "business",
    },
    {
        "id": "nyt-world",
        "name": "The New York Times",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "default_region": "Global policy",
        "category": "world",
    },
    {
        "id": "guardian-world",
        "name": "The Guardian",
        "url": "https://www.theguardian.com/world/rss",
        "default_region": "Global policy",
        "category": "world",
    },
    {
        "id": "wsj-world",
        "name": "The Wall Street Journal",
        "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "default_region": "Global policy",
        "category": "world",
    },
]
_LIVE_NEWS_USER_AGENT = "SignalLoomNewsFetcher/1.0"
_LIVE_NEWS_TTL_SECONDS = int(os.getenv("PLATFORM_LIVE_NEWS_TTL_SECONDS", "900"))
_LIVE_NEWS_MAX_AGE_MINUTES = int(os.getenv("PLATFORM_LIVE_NEWS_MAX_AGE_MINUTES", str(60 * 24 * 14)))
_LIVE_NEWS_DISABLED = os.getenv("PLATFORM_DISABLE_LIVE_NEWS", "").strip().lower() in {"1", "true", "yes", "on"}
_LIVE_NEWS_SSL_CONTEXT = ssl._create_unverified_context()
_LIVE_NEWS_CACHE: dict[str, Any] = {"items": None, "expires_at": None}
_LIVE_NEWS_LOCK = threading.Lock()
_NEWS_RELEVANCE_KEYWORDS = {
    "fed": 4,
    "central bank": 4,
    "rates": 4,
    "rate": 2,
    "yield": 4,
    "yields": 4,
    "inflation": 4,
    "oil": 4,
    "crude": 4,
    "energy": 3,
    "tariff": 4,
    "trade": 3,
    "exports": 3,
    "import": 3,
    "manufacturing": 4,
    "factory": 3,
    "stimulus": 4,
    "china": 4,
    "property": 3,
    "real estate": 3,
    "economy": 3,
    "economic": 3,
    "debt": 3,
    "markets": 3,
    "market": 2,
    "stocks": 2,
    "bonds": 2,
    "dollar": 3,
    "currency": 3,
    "shipping": 2,
    "supply chain": 3,
    "semiconductor": 3,
    "chip": 2,
}
_NEWS_EXCLUDE_KEYWORDS = {
    "dead",
    "dies",
    "death",
    "obituary",
    "football",
    "soccer",
    "baseball",
    "tennis",
    "movie",
    "hollywood writers",
    "shoplifter",
    "easter eggs",
}
_AUTHOR_BY_ID = {author["id"]: author for author in AUTHORS}


def _clean_feed_text(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_feed_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _slugify_news(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "headline"


def _news_relevance_score(title: str, summary: str, source: dict[str, str]) -> int:
    haystack = f"{title} {summary}".lower()
    if any(token in haystack for token in _NEWS_EXCLUDE_KEYWORDS):
        return -1
    score = 2 if source["category"] == "business" else 0
    for keyword, weight in _NEWS_RELEVANCE_KEYWORDS.items():
        if keyword in haystack:
            score += weight
    return score


def _infer_news_theme(title: str, summary: str) -> str:
    haystack = f"{title} {summary}".lower()
    if any(keyword in haystack for keyword in ("fed", "yield", "yields", "rates", "central bank", "inflation")):
        return "rates"
    if any(keyword in haystack for keyword in ("oil", "crude", "opec", "energy")):
        return "oil"
    if any(keyword in haystack for keyword in ("china", "stimulus", "property", "manufacturing", "exports", "factory")):
        return "china"
    if any(keyword in haystack for keyword in ("tariff", "trade", "shipping", "supply chain", "deportation")):
        return "trade"
    if any(keyword in haystack for keyword in ("earnings", "guidance", "deal", "contract", "merger")):
        return "earnings"
    return "macro"


def _infer_news_region(theme: str, title: str, summary: str, source: dict[str, str]) -> str:
    haystack = f"{title} {summary}".lower()
    if theme == "rates":
        return "US rates"
    if theme == "oil":
        return "Oil market"
    if theme == "china":
        return "China demand"
    if theme == "trade":
        return "Trade policy"
    if "europe" in haystack or "ecb" in haystack:
        return "Europe"
    return source["default_region"]


def _english_news_impact(theme: str, title: str, summary: str) -> str:
    if theme == "rates":
        return "Rates-sensitive growth trades may need stronger proof before extending."
    if theme == "oil":
        return "Hotter oil can pressure long-duration growth while helping energy-linked rotations."
    if theme == "china":
        return "Cyclicals, semis, and exporters can react first if the demand signal turns into policy."
    if theme == "trade":
        return "Trade-policy headlines can quickly change sector leadership and sentiment."
    if theme == "earnings":
        return "Single-company headlines can spill into peers when they change the sector narrative."
    return "Macro headlines matter when they change where money wants to hide or rotate next."


def _korean_news_summary(theme: str, source_name: str, title: str, summary: str) -> str:
    if theme == "rates":
        return f"{source_name} 보도입니다. 금리와 국채 수익률이 다시 변수로 떠오르면 성장주 쪽은 바로 달리기보다 한 번 더 확인하는 흐름이 나올 수 있습니다."
    if theme == "oil":
        return f"{source_name} 보도입니다. 유가가 다시 오르면 인플레이션 부담이 살아나서 성장주에는 부담, 에너지 쪽에는 상대 강도가 붙을 수 있습니다."
    if theme == "china":
        return f"{source_name} 보도입니다. 중국 수요나 부양 신호는 반도체, 소재, 수출주 쪽 순환매로 이어지는지 먼저 보는 재료입니다."
    if theme == "trade":
        return f"{source_name} 보도입니다. 통상이나 지정학 뉴스는 업종별 온도 차를 빠르게 만들 수 있어서, 바로 추격하기보다 어떤 섹터가 먼저 반응하는지 보는 편이 좋습니다."
    if theme == "earnings":
        return f"{source_name} 보도입니다. 개별 기업 뉴스처럼 보여도 같은 업종 분위기를 함께 바꿀 수 있어, 동종 종목 반응을 같이 보는 게 중요합니다."
    return f"{source_name} 보도입니다. 이번 뉴스는 거시 흐름과 투자 심리에 영향을 줄 수 있어서, 바로 매수보다 시장 반응을 같이 보는 편이 좋습니다."


def _korean_news_impact(theme: str) -> str:
    if theme == "rates":
        return "금리 부담이 커지면 AI와 성장주 쪽은 매수 속도가 느려질 수 있습니다."
    if theme == "oil":
        return "유가가 뜨거워지면 성장주에는 부담, 에너지 관련 흐름에는 도움이 될 수 있습니다."
    if theme == "china":
        return "정책으로 이어지면 수요 민감 업종에 순환 매수가 붙을 수 있습니다."
    if theme == "trade":
        return "통상 뉴스는 업종별로 강약을 빠르게 갈라놓을 수 있습니다."
    if theme == "earnings":
        return "한 기업 뉴스가 같은 업종 전반의 기대치를 같이 바꿀 수 있습니다."
    return "거시 뉴스는 돈이 어디로 이동하는지 바꾸는 재료가 될 수 있습니다."


def _author_view(author_id: str, kind: str, en_summary: str, ko_summary: str) -> dict[str, Any]:
    author = _AUTHOR_BY_ID[author_id]
    return {
        "id": f"live-news-{author_id}-{kind}",
        "author_id": author_id,
        "kind": kind,
        "copy": {
            "en": {
                "headline": author["name"],
                "summary": en_summary,
            },
            "ko": {
                "headline": author["name"],
                "summary": ko_summary,
            },
        },
    }


def _build_news_views(theme: str) -> list[dict[str, Any]]:
    if theme == "rates":
        return [
            _author_view(
                "hana-macro",
                "watch",
                "Macro pressure matters first here. I would wait one more session and see whether yields cool before chasing new longs.",
                "이럴 때는 거시 압력이 먼저입니다. 국채 금리가 진정되는지 하루 더 본 뒤에 새 매수를 생각하겠습니다.",
            ),
            _author_view(
                "signal-loom",
                "buy",
                "The buy case is still alive, but only for names already holding above their entry maps.",
                "매수 생각이 완전히 깨진 건 아닙니다. 다만 이미 기준 위에 있는 종목만 계속 볼 만합니다.",
            ),
            _author_view(
                "rex-reverse",
                "buy",
                "If this pushes crowded longs into a flush, inverse vehicles can finally become the cleaner trade.",
                "이 뉴스로 과열된 롱이 흔들리면 리버스 쪽이 오히려 더 깔끔한 자리가 될 수 있습니다.",
            ),
        ]
    if theme == "oil":
        return [
            _author_view(
                "mina-tape",
                "sell",
                "When oil and rates wake up together, trimming extended winners usually matters more than adding new risk.",
                "유가와 금리가 같이 들리면 새 진입보다 기존 수익 포지션 정리가 더 중요해질 수 있습니다.",
            ),
            _author_view(
                "rex-reverse",
                "buy",
                "If growth leadership starts fading on inflation pressure, hedge instruments can move faster than the long book.",
                "인플레이션 부담으로 성장주 리더십이 꺾이면, 롱보다 헤지 쪽이 먼저 움직일 수 있습니다.",
            ),
            _author_view(
                "jay-rotation",
                "watch",
                "I would watch where hot money rotates next instead of assuming all momentum disappears at once.",
                "모멘텀이 한 번에 사라진다고 보기보다, 자금이 어디로 옮겨가는지 먼저 보겠습니다.",
            ),
        ]
    if theme == "china":
        return [
            _author_view(
                "jay-rotation",
                "buy",
                "If the market treats this as real policy support, high-beta cyclicals can wake up first.",
                "시장이 이걸 진짜 정책 신호로 받아들이면 고베타 경기민감주부터 먼저 반응할 수 있습니다.",
            ),
            _author_view(
                "theo-options",
                "buy",
                "This is the kind of headline that can create a fast burst, but only if speed and participation confirm quickly.",
                "이런 뉴스는 짧게 강한 탄력을 만들 수 있습니다. 다만 속도와 참여가 바로 붙을 때만 대응할 만합니다.",
            ),
            _author_view(
                "hana-macro",
                "watch",
                "The headline helps, but I still want to see whether the demand signal turns into actual follow-through.",
                "헤드라인은 좋지만, 실제 수요 신호로 이어지는지 한 번 더 확인할 필요가 있습니다.",
            ),
        ]
    if theme == "trade":
        return [
            _author_view(
                "ivy-events",
                "watch",
                "The headline matters, but I want the first clean price reaction before calling it a trade.",
                "뉴스 자체는 중요하지만, 첫 가격 반응이 깔끔하게 나오는지 보고 나서 거래로 볼 생각입니다.",
            ),
            _author_view(
                "sol-defense",
                "watch",
                "Trade-policy headlines usually raise the value of steadier charts over the hottest names.",
                "통상 뉴스가 커질수록 가장 뜨거운 종목보다 차분한 방어형 흐름이 더 나아질 수 있습니다.",
            ),
            _author_view(
                "rex-reverse",
                "buy",
                "If this turns into another risk-off wave, the cleaner setup may show up on the hedge side first.",
                "이 뉴스가 리스크오프로 번지면, 더 깔끔한 자리는 반대편 헤지 쪽에서 먼저 나올 수 있습니다.",
            ),
        ]
    if theme == "earnings":
        return [
            _author_view(
                "ivy-events",
                "buy",
                "Event-driven names can move for several sessions if the headline changes what the whole group is pricing.",
                "이벤트성 뉴스는 업종 기대를 바꾸면 며칠 더 이어질 수 있습니다.",
            ),
            _author_view(
                "signal-loom",
                "watch",
                "I still want a clean price map. If peers do not confirm, I would keep it on watch first.",
                "그래도 가격 구간은 다시 확인해야 합니다. 같은 업종이 같이 움직이지 않으면 우선 관망하겠습니다.",
            ),
            _author_view(
                "mina-tape",
                "sell",
                "If the first move gets too crowded, taking partial gains fast can matter more than waiting for a perfect finish.",
                "첫 반응에 사람이 몰리면, 끝까지 다 먹으려 하기보다 일부 수익을 빨리 챙기는 편이 낫습니다.",
            ),
        ]
    return [
        _author_view(
            "hana-macro",
            "watch",
            "I would treat this as a watch item first and let the broader market reaction tell me how serious it is.",
            "지금은 먼저 관망 재료로 보고, 시장이 이 뉴스를 얼마나 크게 받아들이는지 확인하겠습니다.",
        ),
        _author_view(
            "signal-loom",
            "watch",
            "I want price to confirm the headline before I move from a note to a buy post.",
            "뉴스를 바로 매수 근거로 쓰기보다, 가격이 같은 방향으로 확인될 때까지 기다리겠습니다.",
        ),
        _author_view(
            "sol-defense",
            "buy",
            "When the tape gets messy, safer trends often become the easier trade to explain and hold.",
            "장이 복잡해질수록 덜 시끄럽고 더 안정적인 흐름이 오히려 다루기 쉬워집니다.",
        ),
    ]


def _fetch_live_news_candidates(now: datetime) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source in _LIVE_NEWS_SOURCES:
        request = Request(source["url"], headers={"User-Agent": _LIVE_NEWS_USER_AGENT})
        try:
            with urlopen(request, context=_LIVE_NEWS_SSL_CONTEXT, timeout=12) as response:
                raw = response.read()
        except URLError:
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue

        for item in root.findall(".//item"):
            title = _clean_feed_text(item.findtext("title"))
            summary = _clean_feed_text(item.findtext("description"))
            link = _clean_feed_text(item.findtext("link"))
            published_at = _parse_feed_datetime(item.findtext("pubDate"))
            if not title or not summary or not link or not published_at:
                continue
            age_minutes = max(1, int((now - published_at).total_seconds() // 60))
            if age_minutes > _LIVE_NEWS_MAX_AGE_MINUTES:
                continue
            score = _news_relevance_score(title, summary, source)
            if score <= 0:
                continue
            theme = _infer_news_theme(title, summary)
            candidates.append(
                {
                    "id": f"{source['id']}-{_slugify_news(title)}",
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "published_minutes_ago": age_minutes,
                    "published_at": published_at,
                    "source": source["name"],
                    "region": _infer_news_region(theme, title, summary, source),
                    "score": score,
                    "theme": theme,
                }
            )
    return candidates


def _shape_live_news_item(candidate: dict[str, Any]) -> dict[str, Any]:
    theme = candidate["theme"]
    summary = candidate["summary"]
    title = candidate["title"]
    source_name = candidate["source"]
    return {
        "id": candidate["id"],
        "region": candidate["region"],
        "source": source_name,
        "source_url": candidate["url"],
        "published_minutes_ago": candidate["published_minutes_ago"],
        "copy": {
            "en": {
                "headline": title,
                "summary": summary,
                "impact": _english_news_impact(theme, title, summary),
            },
            "ko": {
                "headline": title,
                "summary": _korean_news_summary(theme, source_name, title, summary),
                "impact": _korean_news_impact(theme),
            },
        },
        "views": _build_news_views(theme),
    }


def _select_live_news(candidates: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: (-item["score"], item["published_minutes_ago"], item["title"]),
    )
    chosen: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    used_sources: set[str] = set()

    for item in ranked:
        normalized_title = item["title"].lower()
        if normalized_title in seen_titles or item["source"] in used_sources:
            continue
        chosen.append(item)
        seen_titles.add(normalized_title)
        used_sources.add(item["source"])
        if len(chosen) >= limit:
            return chosen

    for item in ranked:
        normalized_title = item["title"].lower()
        if normalized_title in seen_titles:
            continue
        chosen.append(item)
        seen_titles.add(normalized_title)
        if len(chosen) >= limit:
            break
    return chosen


def get_world_news() -> list[dict[str, Any]]:
    if _LIVE_NEWS_DISABLED:
        return deepcopy(WORLD_NEWS)

    now = datetime.now(timezone.utc)
    with _LIVE_NEWS_LOCK:
        expires_at = _LIVE_NEWS_CACHE["expires_at"]
        cached_items = _LIVE_NEWS_CACHE["items"]
        if cached_items and isinstance(expires_at, datetime) and expires_at > now:
            return deepcopy(cached_items)

        try:
            candidates = _fetch_live_news_candidates(now)
            selected = _select_live_news(candidates)
            if len(selected) >= 3:
                live_items = [_shape_live_news_item(item) for item in selected]
                _LIVE_NEWS_CACHE["items"] = live_items
                _LIVE_NEWS_CACHE["expires_at"] = now + timedelta(seconds=_LIVE_NEWS_TTL_SECONDS)
                return deepcopy(live_items)
        except Exception:
            pass

    return deepcopy(WORLD_NEWS)


THREADS = [
    {
        "id": "msft-watch",
        "kind": "watch",
        "ticker": "MSFT",
        "company": "Microsoft",
        "time": "now",
        "age_minutes": 2,
        "author_id": "hana-macro",
        "author": "Macro Pulse",
        "handle": "@macropulse",
        "avatar": "MP",
        "metrics": {"reads": "8.2K", "saves": "214", "follows": "71"},
        "sparkline": [24, 26, 25, 29, 28, 31, 35, 39, 38],
        "tags": ["Pre-signal", "Cloud", "Reclaim test"],
        "price_map": [
            {"label": "Watch", "value": "$412.50"},
            {"label": "Trigger", "value": "$416.10"},
        ],
        "copy": {
            "en": {
                "headline": "MSFT is on watch. A live post could follow soon.",
                "summary": (
                    "There is no buy post yet. But if price gets back above the post-earnings range with volume, "
                    "this can turn into a live thread quickly."
                ),
                "beats": [
                    "We are watching whether cloud leadership starts leading again.",
                    "The key is a clean move back above the range, not every small headline.",
                    "Posting the watch phase first makes the later buy post easier to trust.",
                ],
                "footer": "Watch posts help people understand the setup before the real signal appears.",
            },
            "ko": {
                "headline": "MSFT는 아직 안 삽니다. 조금 더 지켜봅니다.",
                "summary": (
                    "지금은 바로 사기보다 조금 더 기다리는 편이 낫습니다. "
                    "$416.10 위로 다시 올라오면 그때 사는 쪽으로 다시 봅니다."
                ),
                "beats": [
                    "지금은 클라우드 흐름이 다시 살아나는지 먼저 봅니다.",
                    "뉴스보다 가격이 다시 올라오는지가 더 중요합니다.",
                    "아직 안 사는 이유를 먼저 적어두면, 나중에 사는 글도 덜 헷갈립니다.",
                ],
                "footer": "먼저 볼 가격을 적어두면, 나중에 사는 이유도 더 쉽게 이해됩니다.",
            },
        },
    },
    {
        "id": "nvda-buy",
        "kind": "buy",
        "ticker": "NVDA",
        "company": "NVIDIA",
        "time": "9m",
        "age_minutes": 9,
        "author_id": "signal-loom",
        "author": "Loom Core",
        "handle": "@loomcore",
        "avatar": "LC",
        "metrics": {"reads": "12.4K", "saves": "482", "follows": "143"},
        "sparkline": [18, 20, 19, 24, 28, 33, 36, 42, 46],
        "tags": ["Breakout", "AI spend", "Volume expansion"],
        "price_map": [
            {"label": "Entry", "value": "$876.20"},
            {"label": "Risk", "value": "$842.00"},
            {"label": "Focus", "value": "$924.00"},
        ],
        "copy": {
            "en": {
                "headline": "NVDA just triggered a live buy post.",
                "summary": (
                    "Price broke higher, the sector moved with it, and the risk line stayed clear. "
                    "That was enough to post the trade idea in public."
                ),
                "beats": [
                    "We only posted after price and volume agreed.",
                    "A simple price map helps people understand the setup fast.",
                    "This post is here to show the setup clearly, not to shout.",
                ],
                "footer": "If the move continues, we will add follow-up notes in the same thread.",
            },
            "ko": {
                "headline": "NVDA는 지금 사볼 만하다고 봅니다.",
                "summary": (
                    "가격이 다시 올라왔고, 같은 업종도 같이 강했습니다. "
                    "손절선도 분명해서 지금은 사볼 만한 자리라고 봤습니다."
                ),
                "beats": [
                    "가격이 다시 올라오고 거래량도 붙어서 지금은 살 만하다고 봤습니다.",
                    "사는 가격과 손절선을 같이 보여줘야 바로 이해할 수 있습니다.",
                    "이 글은 무조건 사라는 뜻이 아니라, 지금 자리를 같이 보자는 기록입니다.",
                ],
                "footer": "흐름이 더 가면 같은 글 아래에 계속 업데이트를 붙입니다.",
            },
        },
    },
    {
        "id": "crwd-buy",
        "kind": "buy",
        "ticker": "CRWD",
        "company": "CrowdStrike",
        "time": "41m",
        "age_minutes": 41,
        "author_id": "theo-options",
        "author": "Delta Sprint",
        "handle": "@deltasprint",
        "avatar": "DS",
        "metrics": {"reads": "9.6K", "saves": "376", "follows": "118"},
        "sparkline": [17, 21, 24, 23, 28, 31, 35, 39, 44],
        "tags": ["Security", "Range reclaim", "Momentum"],
        "price_map": [
            {"label": "Entry", "value": "$171.40"},
            {"label": "Risk", "value": "$165.80"},
            {"label": "Focus", "value": "$188.00"},
        ],
        "copy": {
            "en": {
                "headline": "CRWD gave a clean buy setup above the range.",
                "summary": (
                    "The level was clear, the stop area was readable, and the move still had room to run. "
                    "That made it a simple post to understand."
                ),
                "beats": [
                    "People react faster when the chart is easy to read.",
                    "A fast post turns a signal into something people can save and revisit.",
                    "The more saves a post gets, the more people return for the exit recap.",
                ],
                "footer": "This is where the site starts feeling like a feed people check every day.",
            },
            "ko": {
                "headline": "CRWD는 지금 사볼 만한 자리입니다.",
                "summary": (
                    "박스 위로 다시 올라왔고, 손절 가격도 가까워서 이해하기 쉬운 자리였습니다. "
                    "아직 한 번 더 움직일 힘이 남아 있다고 봤습니다."
                ),
                "beats": [
                    "차트가 쉬워서 지금 왜 사는지 한눈에 보이는 자리였습니다.",
                    "사는 가격과 손절선을 먼저 보여주면 덜 헷갈립니다.",
                    "저장 수가 많은 글은 보통 나중 결과 글도 다시 보게 만듭니다.",
                ],
                "footer": "이런 글이 쌓일수록 사람들이 피드를 더 자주 다시 보게 됩니다.",
            },
        },
    },
    {
        "id": "crwd-sell",
        "kind": "sell",
        "ticker": "CRWD",
        "company": "CrowdStrike",
        "time": "2h",
        "age_minutes": 120,
        "author_id": "mina-tape",
        "author": "Exit Sentinel",
        "handle": "@exitsentinel",
        "avatar": "ES",
        "metrics": {"reads": "15.9K", "saves": "611", "follows": "209"},
        "sparkline": [12, 16, 23, 30, 37, 44, 41, 39, 34],
        "tags": ["Exit", "Trail break", "Receipts"],
        "price_map": [
            {"label": "Entry", "value": "$171.40"},
            {"label": "Exit", "value": "$202.90"},
            {"label": "Return", "value": "+18.4%"},
            {"label": "Hold", "value": "9d"},
        ],
        "copy": {
            "en": {
                "headline": "CRWD trade closed at +18.4% from the first buy post.",
                "summary": (
                    "The move cooled and the exit rule triggered. "
                    "At this stage, showing the result clearly matters more than the excitement from the entry."
                ),
                "beats": [
                    "Showing the full move keeps the archive honest.",
                    "Public exit posts make people pay closer attention to the next setup.",
                    "The tone can be confident, but it should not sound like a promise.",
                ],
                "footer": "If you missed this one, the next validated setup will appear in the feed.",
            },
            "ko": {
                "headline": "CRWD는 여기서 팔았습니다. 수익률은 +18.4%였습니다.",
                "summary": (
                    "오르던 힘이 약해져서 여기서 팔았습니다. "
                    "더 기다리기보다, 어디서 팔았는지 분명하게 남기는 편이 더 중요했습니다."
                ),
                "beats": [
                    "사고 팔 때까지 같은 흐름으로 남겨야 기록이 됩니다.",
                    "파는 글이 있어야 다음 사는 글도 더 믿고 보게 됩니다.",
                    "돌려 말하기보다 어디서 팔았는지 바로 보여주는 게 더 낫습니다.",
                ],
                "footer": "이번 자리를 놓쳤어도 다음 매수 글은 다시 피드에 올라옵니다.",
            },
        },
    },
    {
        "id": "tsla-buy",
        "kind": "buy",
        "ticker": "TSLA",
        "company": "Tesla",
        "time": "5h",
        "age_minutes": 300,
        "author_id": "jay-rotation",
        "author": "Beta Radar",
        "handle": "@betaradar",
        "avatar": "BR",
        "metrics": {"reads": "11.1K", "saves": "358", "follows": "127"},
        "sparkline": [15, 18, 22, 20, 27, 33, 31, 38, 43],
        "tags": ["High beta", "Trend day", "Narrative heat"],
        "price_map": [
            {"label": "Entry", "value": "$238.60"},
            {"label": "Risk", "value": "$231.90"},
            {"label": "Focus", "value": "$252.00"},
        ],
        "copy": {
            "en": {
                "headline": "TSLA triggered a fast buy setup.",
                "summary": (
                    "TSLA moves quickly and draws attention, so the post needs to explain the move in a fast and clear way."
                ),
                "beats": [
                    "Fast-moving names bring in new readers who may stay for calmer setups too.",
                    "The post should feel confident, but still read like research.",
                    "Big names like this often bring new people into the feed.",
                ],
                "footer": "These are the posts people save, share, and search for again later.",
            },
            "ko": {
                "headline": "TSLA는 지금 짧게 사볼 만하다고 봅니다.",
                "summary": (
                    "TSLA는 빨리 움직이는 종목이라, 길게 읽기보다 지금 사는 가격과 손절선을 바로 보는 편이 낫습니다."
                ),
                "beats": [
                    "빨리 움직이는 종목은 왜 지금 사는지 더 짧고 분명하게 써야 합니다.",
                    "그래도 글은 과장보다 분석에 가까워야 오래 갑니다.",
                    "큰 종목 하나가 전체 피드 분위기를 바꾸는 경우가 많습니다.",
                ],
                "footer": "이런 글은 저장해두고 나중에 다시 보는 경우가 많습니다.",
            },
        },
    },
    {
        "id": "nvda-sell",
        "kind": "sell",
        "ticker": "NVDA",
        "company": "NVIDIA",
        "time": "1d",
        "age_minutes": 1440,
        "author_id": "signal-loom",
        "author": "Loom Core",
        "handle": "@loomcore",
        "avatar": "LC",
        "metrics": {"reads": "18.7K", "saves": "733", "follows": "264"},
        "sparkline": [21, 28, 35, 41, 48, 54, 51, 45, 39],
        "tags": ["Exit", "Momentum fade", "Replay value"],
        "price_map": [
            {"label": "Entry", "value": "$876.20"},
            {"label": "Exit", "value": "$948.60"},
            {"label": "Return", "value": "+8.3%"},
            {"label": "Hold", "value": "4d"},
        ],
        "copy": {
            "en": {
                "headline": "NVDA exit recap posted at +8.3% from the live buy post.",
                "summary": (
                    "A good feed does not stop at the buy. It also shows how the trade ended, "
                    "so the next live post feels more trustworthy."
                ),
                "beats": [
                    "The entry, updates, and exit should read like one connected story.",
                    "The stronger the proof, the less hype you need.",
                    "Even late visitors leave knowing what to watch next time.",
                ],
                "footer": "That is what brings people back for the next signal.",
            },
            "ko": {
                "headline": "NVDA는 여기서 팔았습니다. 수익률은 +8.3%였습니다.",
                "summary": (
                    "좋은 피드는 매수 글에서 끝나지 않습니다. "
                    "어디서 팔았는지까지 남겨야 다음 글도 더 믿고 볼 수 있습니다."
                ),
                "beats": [
                    "사고, 중간에 보고, 파는 흐름이 한 번에 보여야 기록이 됩니다.",
                    "증거가 분명하면 과한 말은 필요 없습니다.",
                    "늦게 본 사람도 다음엔 어디를 봐야 하는지 남겨두는 게 중요합니다.",
                ],
                "footer": "그래야 사람들이 다음 신호도 다시 보러 옵니다.",
            },
        },
    },
]


TICKER_COMPANIES = {
    "NVDA": "NVIDIA",
    "MSFT": "Microsoft",
    "CRWD": "CrowdStrike",
    "TSLA": "Tesla",
    "META": "Meta",
    "AVGO": "Broadcom",
    "AMD": "AMD",
    "PLTR": "Palantir",
    "AMZN": "Amazon",
    "NFLX": "Netflix",
    "SMCI": "Super Micro Computer",
    "COIN": "Coinbase",
    "AAPL": "Apple",
    "GOOGL": "Alphabet",
    "QQQ": "Invesco QQQ Trust",
    "SQQQ": "ProShares UltraPro Short QQQ",
    "SOXL": "Direxion Daily Semiconductor Bull 3X",
    "SOXS": "Direxion Daily Semiconductor Bear 3X",
    "IWM": "iShares Russell 2000 ETF",
    "MSTR": "MicroStrategy",
    "ARM": "Arm Holdings",
    "HOOD": "Robinhood",
}

_WATCH_AUTHOR_ORDER = ("hana-macro", "signal-loom", "jay-rotation", "sol-defense", "ivy-events")
_BUY_AUTHOR_ORDER = ("signal-loom", "theo-options", "jay-rotation", "nova-revert", "ivy-events", "rex-reverse")
_SELL_AUTHOR_ORDER = ("mina-tape", "signal-loom", "theo-options", "rex-reverse", "nova-revert")
_WATCH_LABELS_KO = (
    "아직 안 삽니다. 조금 더 지켜봅니다.",
    "바로 사기보다 한 번 더 확인합니다.",
    "지금은 관망 쪽이 더 낫다고 봅니다.",
)
_BUY_LABELS_KO = (
    "지금 사볼 만하다고 봅니다.",
    "다시 매수 쪽으로 기울었습니다.",
    "오늘은 매수 판단으로 올립니다.",
)
_SELL_LABELS_KO = (
    "여기서 정리했습니다.",
    "이번 흐름은 여기서 마무리했습니다.",
    "욕심내지 않고 이 구간에서 팔았습니다.",
)
_WATCH_LABELS_EN = (
    "is still a watch, not a buy.",
    "needs one more confirmation before it becomes a buy.",
    "looks better as a wait-and-see setup for now.",
)
_BUY_LABELS_EN = (
    "moved back into a buy zone.",
    "looks buyable again here.",
    "earned a fresh buy post today.",
)
_SELL_LABELS_EN = (
    "was closed here.",
    "was trimmed and closed here.",
    "was sold into strength here.",
)


def _compact_metric(value: int) -> str:
    if value >= 1000:
        whole = value / 1000
        return f"{whole:.1f}K".replace(".0K", "K")
    return str(value)


def _sparkline(seed: int, direction: int) -> list[int]:
    base = 18 + (seed % 6) * 4
    current = base
    points: list[int] = []
    for step in range(9):
        drift = direction * (2 + ((seed + step) % 3))
        wobble = ((seed + step * 5) % 5) - 2
        current = max(9, current + drift + wobble)
        points.append(current)
    return points


def _author_index() -> dict[str, dict]:
    return {author["id"]: author for author in AUTHORS}


def _thread_metrics(seed: int, weight: int) -> dict[str, str]:
    reads = 1800 + weight * 420 + (seed % 7) * 185
    saves = 90 + weight * 28 + (seed % 5) * 13
    follows = 22 + weight * 7 + (seed % 3) * 4
    return {
        "reads": _compact_metric(reads),
        "saves": _compact_metric(saves),
        "follows": _compact_metric(follows),
    }


def _buy_copy(ticker: str, company: str, entry: float, risk: float, focus: float, variant: int) -> dict:
    headline_ko = (
        f"{ticker}는 {_BUY_LABELS_KO[variant % len(_BUY_LABELS_KO)]}"
    )
    summary_ko = (
        f"{company} 흐름이 다시 위로 열렸고, 지금은 ${entry:.2f} 부근에서 사는 쪽이 더 낫다고 봤습니다. "
        f"대신 ${risk:.2f} 아래로 밀리면 생각을 바로 접습니다."
    )
    beats_ko = [
        "가격이 다시 올라오고 거래량도 붙는지를 먼저 확인했습니다.",
        f"지금은 목표보다 ${focus:.2f}까지 얼마나 무리 없이 가는지가 더 중요합니다.",
        "글은 길게 쓰기보다 지금 왜 사는지와 어디서 틀리면 나오는지만 남겼습니다.",
    ]
    headline_en = f"{ticker} {_BUY_LABELS_EN[variant % len(_BUY_LABELS_EN)]}"
    summary_en = (
        f"{company} reclaimed the key range, so the desk marked ${entry:.2f} as the buy zone. "
        f"If price slips below ${risk:.2f}, the idea is considered broken."
    )
    beats_en = [
        "The desk waited for price and participation to confirm the same move.",
        f"The first target is not perfection. It is whether price can travel cleanly toward ${focus:.2f}.",
        "The note is kept simple so people can read the plan in one pass.",
    ]
    return {
        "en": {
            "headline": headline_en,
            "summary": summary_en,
            "beats": beats_en,
            "footer": "If the move keeps working, the next update should feel easy to follow.",
        },
        "ko": {
            "headline": headline_ko,
            "summary": summary_ko,
            "beats": beats_ko,
            "footer": "흐름이 이어지면 같은 종목에 후속 글이 다시 붙습니다.",
        },
    }


def _watch_copy(ticker: str, company: str, watch: float, trigger: float, variant: int) -> dict:
    headline_ko = f"{ticker}는 {_WATCH_LABELS_KO[variant % len(_WATCH_LABELS_KO)]}"
    summary_ko = (
        f"지금은 바로 사기보다 ${watch:.2f} 부근이 유지되는지 먼저 봅니다. "
        f"${trigger:.2f} 위로 다시 올라오면 그때 사는 쪽으로 다시 판단합니다."
    )
    beats_ko = [
        "지금은 사는 글보다 기다리는 이유를 먼저 적어두는 편이 낫습니다.",
        "뉴스보다 가격이 다시 살아나는지가 더 중요합니다.",
        "관망 글은 나중에 매수 글이 나왔을 때 덜 헷갈리게 해줍니다.",
    ]
    headline_en = f"{ticker} {_WATCH_LABELS_EN[variant % len(_WATCH_LABELS_EN)]}"
    summary_en = (
        f"The desk is watching whether {company} can keep holding ${watch:.2f}. "
        f"A move back above ${trigger:.2f} would be the point where the idea becomes actionable again."
    )
    beats_en = [
        "Waiting notes work best when they tell readers what must change before a buy is allowed.",
        "The key is price reclaim, not noise from every small headline.",
        "A clear watch note makes the later entry note easier to trust.",
    ]
    return {
        "en": {
            "headline": headline_en,
            "summary": summary_en,
            "beats": beats_en,
            "footer": "For this kind of setup, patience matters more than speed.",
        },
        "ko": {
            "headline": headline_ko,
            "summary": summary_ko,
            "beats": beats_ko,
            "footer": "이런 자리는 서두르지 않는 편이 결국 더 낫습니다.",
        },
    }


def _sell_copy(ticker: str, company: str, entry: float, exit_price: float, return_pct: float, variant: int) -> dict:
    headline_ko = f"{ticker}는 {_SELL_LABELS_KO[variant % len(_SELL_LABELS_KO)]} 수익률은 +{return_pct:.1f}%였습니다."
    summary_ko = (
        f"{company} 흐름이 둔해져서 ${exit_price:.2f}에서 정리했습니다. "
        f"처음 산 가격은 ${entry:.2f}였고, 이번 기록은 결과를 분명하게 남기는 데 더 의미가 있습니다."
    )
    beats_ko = [
        "사는 글만큼 파는 글도 분명해야 다음 기록이 쌓입니다.",
        "이 정도 수익이면 더 욕심내기보다 결과를 남기는 편이 낫습니다.",
        "나중에 다시 볼 사람을 위해 어디서 팔았는지 바로 적어둡니다.",
    ]
    headline_en = f"{ticker} {_SELL_LABELS_EN[variant % len(_SELL_LABELS_EN)]} Result: +{return_pct:.1f}%."
    summary_en = (
        f"The move cooled, so the desk closed {company} at ${exit_price:.2f}. "
        f"The original entry sat near ${entry:.2f}, and the public recap matters as much as the trade itself."
    )
    beats_en = [
        "A feed becomes believable when exits are posted as clearly as entries.",
        "The goal here is to leave a clean public result, not chase a final extra push.",
        "Readers should know exactly where the trade ended and why.",
    ]
    return {
        "en": {
            "headline": headline_en,
            "summary": summary_en,
            "beats": beats_en,
            "footer": "The next setup matters more when the last one is closed in public.",
        },
        "ko": {
            "headline": headline_ko,
            "summary": summary_ko,
            "beats": beats_ko,
            "footer": "이전 결과가 분명해야 다음 매수 글도 더 쉽게 읽힙니다.",
        },
    }


def _historical_thread(
    *,
    now: datetime,
    week_index: int,
    slot_offset: int,
    ticker: str,
    kind: str,
    author_id: str,
    variant: int,
) -> dict:
    author = _author_index()[author_id]
    company = TICKER_COMPANIES[ticker]
    created_at = now - timedelta(days=week_index * 7 + slot_offset, hours=(variant % 5) * 2 + 1)
    seed = week_index * 17 + slot_offset * 11 + variant * 7
    entry = round(92 + (seed % 230) * 3.15, 2)
    risk = round(entry * (0.955 - (variant % 2) * 0.01), 2)
    trigger = round(entry * 1.018, 2)
    focus = round(entry * (1.055 + (variant % 4) * 0.01), 2)
    exit_price = round(entry * (1.028 + (variant % 5) * 0.018), 2)
    return_pct = round(((exit_price - entry) / entry) * 100, 1)
    hold_days = 2 + (variant % 8)

    if kind == "buy":
        price_map = [
            {"label": "Entry", "value": f"${entry:.2f}"},
            {"label": "Risk", "value": f"${risk:.2f}"},
            {"label": "Focus", "value": f"${focus:.2f}"},
        ]
        copy = _buy_copy(ticker, company, entry, risk, focus, variant)
        direction = 1
        tags = ["Breakout", "Trend follow", "Public note"]
    elif kind == "watch":
        price_map = [
            {"label": "Watch", "value": f"${entry:.2f}"},
            {"label": "Trigger", "value": f"${trigger:.2f}"},
        ]
        copy = _watch_copy(ticker, company, entry, trigger, variant)
        direction = 1 if variant % 2 == 0 else 0
        tags = ["Watch", "Reclaim", "Wait for proof"]
    else:
        price_map = [
            {"label": "Entry", "value": f"${entry:.2f}"},
            {"label": "Exit", "value": f"${exit_price:.2f}"},
            {"label": "Return", "value": f"+{return_pct:.1f}%"},
            {"label": "Hold", "value": f"{hold_days}d"},
        ]
        copy = _sell_copy(ticker, company, entry, exit_price, return_pct, variant)
        direction = -1
        tags = ["Exit", "Receipts", "Risk off"]

    return {
        "id": f"{ticker.lower()}-{kind}-{created_at.strftime('%Y%m%d')}-{author_id.replace('-', '')}",
        "kind": kind,
        "ticker": ticker,
        "company": company,
        "time": f"{max(1, round((now - created_at).total_seconds() / 86400))}d",
        "age_minutes": max(1, round((now - created_at).total_seconds() / 60)),
        "created_at": created_at.isoformat(),
        "author_id": author_id,
        "author": author["name"],
        "handle": author["handle"],
        "avatar": author["avatar"],
        "metrics": _thread_metrics(seed, 3 if kind == "buy" else 2 if kind == "sell" else 1),
        "sparkline": _sparkline(seed, direction),
        "tags": tags,
        "price_map": price_map,
        "copy": copy,
    }


def _historical_threads() -> list[dict]:
    now = datetime.now(timezone.utc)
    tickers = tuple(TICKER_COMPANIES.keys())
    items: list[dict] = []
    weekly_plan = (
        ("watch", 0, _WATCH_AUTHOR_ORDER, 0),
        ("buy", 1, _BUY_AUTHOR_ORDER, 3),
        ("watch", 2, _WATCH_AUTHOR_ORDER, 6),
        ("buy", 2, _BUY_AUTHOR_ORDER, 9),
        ("sell", 3, _SELL_AUTHOR_ORDER, 12),
        ("buy", 4, _BUY_AUTHOR_ORDER, 15),
        ("watch", 5, _WATCH_AUTHOR_ORDER, 18),
        ("sell", 6, _SELL_AUTHOR_ORDER, 21),
    )

    for week_index in range(104):
        for slot_index, (kind, slot_offset, author_order, ticker_offset) in enumerate(weekly_plan):
            variant = week_index * len(weekly_plan) + slot_index
            items.append(
                _historical_thread(
                    now=now,
                    week_index=week_index,
                    slot_offset=slot_offset,
                    ticker=tickers[(week_index * 2 + ticker_offset + slot_index) % len(tickers)],
                    kind=kind,
                    author_id=author_order[variant % len(author_order)],
                    variant=variant,
                )
            )

    items.sort(key=lambda thread: thread["created_at"], reverse=True)
    return items


THREADS = THREADS + _historical_threads()


def _creator_payload() -> dict:
    creator = deepcopy(CREATOR)
    documented_threads = len(THREADS)
    exit_recaps = sum(1 for thread in THREADS if thread["kind"] == "sell")
    creator["stats"] = [
        {"value": creator["stats"][0]["value"], "label": "Followers"},
        {"value": f"{documented_threads}", "label": "Documented threads"},
        {"value": f"{exit_recaps}", "label": "Exit recaps"},
    ]
    return creator


AI_ROUNDTABLE = {
    "defaults": {
        "ticker": "NVDA",
        "company": "NVIDIA",
        "copy": {
            "en": {
                "question": "What do the major AI desks think about NVDA here?",
            },
            "ko": {
                "question": "지금 NVDA를 AI들은 어떻게 보고 있나요?",
            },
        },
    },
    "suggestions": [
        {
            "id": "setup",
            "copy": {
                "en": {
                    "label": "Explain the setup in simple terms",
                },
                "ko": {
                    "label": "이 종목의 자리를 쉽게 설명해 주세요",
                },
            },
        },
        {
            "id": "risk",
            "copy": {
                "en": {
                    "label": "What would make the idea fail?",
                },
                "ko": {
                    "label": "어떤 상황이면 이 아이디어가 깨지나요?",
                },
            },
        },
        {
            "id": "wait-or-act",
            "copy": {
                "en": {
                    "label": "Is this a buy now, a watch, or a pass?",
                },
                "ko": {
                    "label": "지금 매수인지, 관망인지, 패스인지 알려주세요",
                },
            },
        },
    ],
    "models": [
        {
            "id": "gpt",
            "name": "GPT",
            "copy": {
                "en": {
                    "style": "Structure-first",
                    "tagline": "Turns the setup into a clean thesis with entry, risk, and next steps.",
                },
                "ko": {
                    "style": "구조 정리형",
                    "tagline": "진입, 리스크, 다음 체크포인트를 한눈에 정리합니다.",
                },
            },
        },
        {
            "id": "gemini",
            "name": "Gemini",
            "copy": {
                "en": {
                    "style": "Cross-checking",
                    "tagline": "Compares market context, related names, and broad scenario branches.",
                },
                "ko": {
                    "style": "맥락 비교형",
                    "tagline": "시장 배경과 관련 종목을 함께 놓고 비교합니다.",
                },
            },
        },
        {
            "id": "claude",
            "name": "Claude",
            "copy": {
                "en": {
                    "style": "Risk-first",
                    "tagline": "Leans toward caution, invalidation zones, and clean reasoning.",
                },
                "ko": {
                    "style": "리스크 우선형",
                    "tagline": "무리한 해석보다 기준선과 위험 구간을 먼저 봅니다.",
                },
            },
        },
        {
            "id": "grok",
            "name": "Grok",
            "copy": {
                "en": {
                    "style": "Momentum radar",
                    "tagline": "Focuses on heat, narrative speed, and whether the move still has fuel.",
                },
                "ko": {
                    "style": "모멘텀 레이더형",
                    "tagline": "지금 시장이 얼마나 뜨거운지, 힘이 남았는지 살핍니다.",
                },
            },
        },
    ],
}


def build_platform_blueprint() -> dict:
    """Return the complete platform payload for the frontend."""
    return {
        "meta": {
            "title": "Signal Loom",
            "subtitle": "A monetization operating system for trading-content businesses with legal posture controls built in.",
            "disclaimer": (
                "This blueprint is strategic product guidance, not legal advice. "
                "Any filing-gated or partner-only offer should be reviewed before launch."
            ),
        },
        "creator": _creator_payload(),
        "authors": AUTHORS,
        "proof_points": PROOF_POINTS,
        "pipeline": PIPELINE_STEPS,
        "loops": RETURN_LOOPS,
        "watchlist": WATCHLIST,
        "world_news": get_world_news(),
        "ai_roundtable": AI_ROUNDTABLE,
        "threads": THREADS,
        "ideas": IDEAS,
        "modules": MODULES,
        "guardrails": GUARDRAILS,
        "phases": PHASES,
        "presets": PRESETS,
        "postures": POSTURE_INFO,
    }
