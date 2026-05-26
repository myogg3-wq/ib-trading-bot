"""Shared request language selection helpers for platform pages."""

from __future__ import annotations

from fastapi import Request


SUPPORTED_LANGUAGES = [
    {"code": "en", "label": "English"},
    {"code": "zh-CN", "label": "简体中文"},
    {"code": "hi", "label": "हिन्दी"},
    {"code": "es", "label": "Español"},
    {"code": "ar", "label": "العربية"},
    {"code": "pt", "label": "Português"},
    {"code": "ja", "label": "日本語"},
    {"code": "ko", "label": "한국어"},
    {"code": "fr", "label": "Français"},
]


def normalize_language(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return "en"

    lower = candidate.lower()
    if lower.startswith("zh"):
        return "zh-CN"

    for item in SUPPORTED_LANGUAGES:
        if item["code"].lower() == lower:
            return item["code"]

    base = lower.split("-")[0]
    for item in SUPPORTED_LANGUAGES:
        if item["code"].lower() == base:
            return item["code"]

    return "en"


def language_label(code: str) -> str:
    normalized = normalize_language(code)
    for item in SUPPORTED_LANGUAGES:
        if item["code"] == normalized:
            return item["label"]
    return "English"


def _accept_language_candidates(header: str | None) -> list[str]:
    if not header:
        return []
    candidates: list[str] = []
    for chunk in header.split(","):
        token = chunk.split(";", 1)[0].strip()
        if token:
            candidates.append(token)
    return candidates


def request_language(request: Request, *, query_param: str = "lang") -> str:
    query_language = normalize_language(request.query_params.get(query_param))
    if request.query_params.get(query_param):
        return query_language

    for candidate in _accept_language_candidates(request.headers.get("accept-language")):
        normalized = normalize_language(candidate)
        if normalized != "en" or candidate.lower().startswith("en"):
            return normalized

    return "en"
