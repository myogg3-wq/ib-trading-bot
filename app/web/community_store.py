"""Shared storage for community posts and follow state."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import threading
from typing import Any
from uuid import uuid4


def _default_store_path() -> Path:
    """Resolve the on-disk JSON file used for shared platform community state."""
    configured = os.getenv("PLATFORM_COMMUNITY_STORE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "output" / "platform" / "community_state.json"


def _default_state() -> dict[str, Any]:
    return {"posts": [], "follows": {}}


def _compact_metric_to_int(value: str) -> int:
    normalized = (value or "").strip().upper()
    if not normalized:
        return 0

    multiplier = 1
    if normalized.endswith("M"):
        multiplier = 1_000_000
    elif normalized.endswith("K"):
        multiplier = 1_000

    digits = "".join(character for character in normalized if character.isdigit() or character == ".")
    return int(float(digits or 0) * multiplier)


def _normalize_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]


def _normalize_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, str):
        source = raw_tags.split(",")
    elif isinstance(raw_tags, list):
        source = raw_tags
    else:
        source = []

    seen: set[str] = set()
    tags: list[str] = []
    for item in source:
        tag = _normalize_text(item, 24)
        lowered = tag.lower()
        if not tag or lowered in seen:
            continue
        tags.append(tag)
        seen.add(lowered)
        if len(tags) == 4:
            break
    return tags


def _detect_language(value: Any) -> str:
    text = str(value or "")
    if not text.strip():
        return "en"

    checks = [
        ("ko", sum(1 for character in text if "\uac00" <= character <= "\ud7a3")),
        ("ja", sum(1 for character in text if ("\u3040" <= character <= "\u30ff") or ("\u4e00" <= character <= "\u9fff"))),
        ("zh-CN", sum(1 for character in text if "\u4e00" <= character <= "\u9fff")),
        ("ar", sum(1 for character in text if "\u0600" <= character <= "\u06ff")),
        ("hi", sum(1 for character in text if "\u0900" <= character <= "\u097f")),
    ]
    language, score = max(checks, key=lambda item: item[1])
    if score > 0:
        return language
    return "en"


def _build_price_map(kind: str, levels: list[str]) -> list[dict[str, str]]:
    normalized = [_normalize_text(level, 20) for level in levels[:3]]
    while len(normalized) < 3:
        normalized.append("")

    primary, secondary, tertiary = normalized
    if kind == "sell":
        return [
            {"label": "Entry", "value": primary or "$0.00"},
            {"label": "Exit", "value": secondary or "$0.00"},
            {"label": "Return", "value": tertiary or "+0.0%"},
        ]
    if kind == "watch":
        return [
            {"label": "Watch", "value": primary or "$0.00"},
            {"label": "Trigger", "value": secondary or "$0.00"},
            {"label": "Focus", "value": tertiary or "Watching"},
        ]
    return [
        {"label": "Entry", "value": primary or "$0.00"},
        {"label": "Risk", "value": secondary or "$0.00"},
        {"label": "Focus", "value": tertiary or "$0.00"},
    ]


def _generate_sparkline(kind: str) -> list[int]:
    baseline = {
        "buy": [18, 20, 24, 29, 33, 39, 42, 46],
        "sell": [58, 61, 64, 69, 75, 72, 68, 63],
        "watch": [24, 27, 25, 31, 34, 33, 37, 40],
    }.get(kind, [18, 20, 24, 29, 33, 39, 42, 46])
    return [point + random.randint(0, 4) for point in baseline]


def _build_copy(headline: str, summary: str, source_language: str) -> dict[str, dict[str, Any]]:
    return {
        "source_language": source_language,
        source_language: {
            "headline": headline,
            "summary": summary,
        },
    }


def _normalize_contribution_type(value: Any) -> str:
    normalized = _normalize_text(value, 20).lower()
    if normalized in {"question", "counter", "evidence"}:
        return normalized
    return ""


class CommunityStore:
    """Persist community posts and follow relationships in a shared JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_store_path()
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(_default_state(), ensure_ascii=False, indent=2), encoding="utf-8")
            return _default_state()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = _default_state()

        state = _default_state()
        state["posts"] = data.get("posts", []) if isinstance(data.get("posts"), list) else []
        state["follows"] = data.get("follows", {}) if isinstance(data.get("follows"), dict) else {}
        return state

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _follower_counts(self, state: dict[str, Any], authors: list[dict[str, Any]]) -> dict[str, int]:
        counts = {author["id"]: _compact_metric_to_int(author.get("followers", "0")) for author in authors}
        for followed_ids in state["follows"].values():
            for author_id in followed_ids:
                if author_id in counts:
                    counts[author_id] += 1
        return counts

    def snapshot(self, *, viewer_id: str, authors: list[dict[str, Any]]) -> dict[str, Any]:
        viewer_key = _normalize_text(viewer_id, 80)
        with self._lock:
            state = self._read()
            following_ids = state["follows"].get(viewer_key, []) if viewer_key else []
            posts = sorted(
                deepcopy(state["posts"]),
                key=lambda item: item.get("created_at", ""),
                reverse=True,
            )
            return {
                "posts": posts,
                "following_ids": following_ids,
                "follower_counts": self._follower_counts(state, authors),
            }

    def create_post(self, payload: dict[str, Any], *, authors: list[dict[str, Any]]) -> dict[str, Any]:
        author_id = _normalize_text(payload.get("author_id"), 64)
        author_lookup = {author["id"]: author for author in authors}
        if author_id not in author_lookup:
            raise ValueError("Unknown author")

        kind = _normalize_text(payload.get("kind"), 12).lower()
        if kind not in {"buy", "sell", "watch"}:
            raise ValueError("Unsupported thread kind")
        contribution_type = _normalize_contribution_type(payload.get("contribution_type"))

        ticker = _normalize_text(payload.get("ticker"), 12).upper()
        company = _normalize_text(payload.get("company"), 48) or ticker
        headline = _normalize_text(payload.get("headline"), 160)
        summary = _normalize_text(payload.get("summary"), 420)
        tags = _normalize_tags(payload.get("tags"))
        levels = payload.get("levels") if isinstance(payload.get("levels"), list) else []

        if not ticker or not headline or not summary:
            raise ValueError("Ticker, headline, and summary are required")

        author = author_lookup[author_id]
        created_at = datetime.now(timezone.utc).isoformat()
        source_language = _detect_language(f"{headline} {summary}")

        thread = {
            "id": f"community-{uuid4().hex[:12]}",
            "kind": kind,
            "ticker": ticker,
            "company": company,
            "time": "now",
            "created_at": created_at,
            "author_id": author_id,
            "contribution_type": contribution_type,
            "metrics": {"reads": "0", "saves": "0", "follows": "0"},
            "sparkline": _generate_sparkline(kind),
            "tags": tags or [ticker],
            "price_map": _build_price_map(kind, levels),
            "copy": _build_copy(headline, summary, source_language),
        }

        with self._lock:
            state = self._read()
            state["posts"].insert(0, thread)
            self._write(state)

        return deepcopy(thread)

    def set_follow(self, *, viewer_id: str, author_id: str, following: bool, authors: list[dict[str, Any]]) -> dict[str, Any]:
        viewer_key = _normalize_text(viewer_id, 80)
        author_key = _normalize_text(author_id, 64)
        valid_authors = {author["id"] for author in authors}
        if not viewer_key:
            raise ValueError("Viewer id is required")
        if author_key not in valid_authors:
            raise ValueError("Unknown author")

        with self._lock:
            state = self._read()
            current = set(state["follows"].get(viewer_key, []))
            if following:
                current.add(author_key)
            else:
                current.discard(author_key)
            state["follows"][viewer_key] = sorted(current)
            self._write(state)
            return {
                "following_ids": state["follows"][viewer_key],
                "follower_counts": self._follower_counts(state, authors),
            }


community_store = CommunityStore()
