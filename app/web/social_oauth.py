"""Lightweight OAuth helpers for platform social sign-in."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import Request

from app.config import settings


FLOW_COOKIE_MAX_AGE_SECONDS = 60 * 15
PENDING_COOKIE_MAX_AGE_SECONDS = 60 * 60


class SocialOAuthError(ValueError):
    """Raised when a social OAuth flow cannot continue."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    profile_url: str
    scopes: tuple[str, ...]


def _normalize_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized == "twitter":
        return "x"
    return normalized


def _public_base_url(request: Request) -> str:
    configured = (settings.platform_public_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def callback_url(request: Request, provider: str) -> str:
    normalized = _normalize_provider(provider)
    public_provider = "twitter" if normalized == "x" else normalized
    return f"{_public_base_url(request)}/api/platform/auth/oauth/{public_provider}/callback"


def _secret_bytes() -> bytes:
    return (settings.platform_oauth_state_secret or "change_me_platform_oauth").encode("utf-8")


def write_signed_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_secret_bytes(), body, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
        + "."
        + base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    )


def read_signed_payload(token: str | None, *, max_age_seconds: int | None = None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    encoded_body, encoded_signature = token.split(".", 1)
    try:
        body = base64.urlsafe_b64decode(encoded_body + "=" * (-len(encoded_body) % 4))
        signature = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
    except (ValueError, binascii.Error):
        return None
    expected = hmac.new(_secret_bytes(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    created_at = float(payload.get("created_at", 0) or 0)
    if max_age_seconds and created_at:
        if time.time() - created_at > max_age_seconds:
            return None
    return payload if isinstance(payload, dict) else None


def _provider_config(provider: str) -> ProviderConfig:
    normalized = _normalize_provider(provider)
    twitter_client_id = settings.x_oauth_client_id or os.getenv("TWITTER_OAUTH_CLIENT_ID", "").strip()
    twitter_client_secret = settings.x_oauth_client_secret or os.getenv("TWITTER_OAUTH_CLIENT_SECRET", "").strip()
    configs = {
        "google": ProviderConfig(
            provider="google",
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            profile_url="https://openidconnect.googleapis.com/v1/userinfo",
            scopes=("openid", "profile", "email"),
        ),
        "x": ProviderConfig(
            provider="x",
            client_id=twitter_client_id,
            client_secret=twitter_client_secret,
            authorize_url="https://twitter.com/i/oauth2/authorize",
            token_url="https://api.twitter.com/2/oauth2/token",
            profile_url="https://api.twitter.com/2/users/me?user.fields=id,name,username",
            scopes=("users.read", "tweet.read", "offline.access"),
        ),
        "apple": ProviderConfig(
            provider="apple",
            client_id=settings.apple_oauth_client_id,
            client_secret=settings.apple_oauth_client_secret,
            authorize_url="https://appleid.apple.com/auth/authorize",
            token_url="https://appleid.apple.com/auth/token",
            profile_url="",
            scopes=("name", "email"),
        ),
    }
    config = configs.get(normalized)
    if not config:
        raise SocialOAuthError("Unsupported social provider.")
    if not config.client_id or not config.client_secret:
        raise SocialOAuthError(f"{social_provider_title(normalized)} sign-in is not configured yet.")
    return config


def google_client_id() -> str:
    return (settings.google_oauth_client_id or "").strip()


def _oauth_state(provider: str, lang: str) -> tuple[str, str]:
    state_token = secrets.token_urlsafe(24)
    normalized = _normalize_provider(provider)
    payload = {
        "provider": normalized,
        "state": state_token,
        "lang": (lang or "en").strip() or "en",
        "created_at": time.time(),
    }
    return state_token, write_signed_payload(payload)


def _x_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    challenge = hashlib.sha256(verifier.encode("utf-8")).digest()
    return verifier, base64.urlsafe_b64encode(challenge).decode("ascii").rstrip("=")


def build_authorization_redirect(provider: str, request: Request, lang: str) -> tuple[str, str]:
    config = _provider_config(provider)
    callback = callback_url(request, config.provider)
    state_token, signed_flow = _oauth_state(config.provider, lang)
    query: dict[str, str] = {
        "client_id": config.client_id,
        "redirect_uri": callback,
        "response_type": "code",
        "state": state_token,
    }

    if config.provider == "google":
        query["scope"] = " ".join(config.scopes)
        query["access_type"] = "offline"
        query["include_granted_scopes"] = "true"
        query["prompt"] = "select_account"
    elif config.provider == "x":
        verifier, challenge = _x_pkce()
        flow_payload = read_signed_payload(signed_flow) or {}
        flow_payload["code_verifier"] = verifier
        signed_flow = write_signed_payload(flow_payload)
        query["scope"] = " ".join(config.scopes)
        query["code_challenge"] = challenge
        query["code_challenge_method"] = "S256"
    elif config.provider == "apple":
        query["scope"] = " ".join(config.scopes)
        query["response_mode"] = "form_post"

    return f"{config.authorize_url}?{urlencode(query)}", signed_flow


async def _exchange_google(config: ProviderConfig, request: Request, code: str) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            config.token_url,
            data={
                "code": code,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "redirect_uri": callback_url(request, config.provider),
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not token:
            raise SocialOAuthError("Google did not return an access token.")
        profile_response = await client.get(
            config.profile_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
    return {
        "provider": config.provider,
        "subject": str(profile.get("sub") or ""),
        "email": str(profile.get("email") or ""),
        "name": str(profile.get("name") or profile.get("given_name") or ""),
    }


async def verify_google_credential(credential: str) -> dict[str, str]:
    client_id = google_client_id()
    if not client_id:
        raise SocialOAuthError("Google sign-in is not configured yet.")

    id_token = str(credential or "").strip()
    if not id_token:
        raise SocialOAuthError("Google sign-in token is missing.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()

    aud = str(payload.get("aud") or "")
    if aud != client_id:
        raise SocialOAuthError("Google sign-in audience did not match this app.")

    issuer = str(payload.get("iss") or "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise SocialOAuthError("Google sign-in issuer could not be verified.")

    if str(payload.get("email_verified") or "").lower() not in {"true", "1"}:
        raise SocialOAuthError("Google account email is not verified.")

    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise SocialOAuthError("Google did not return an account identifier.")

    email = str(payload.get("email") or "").strip()
    name = str(payload.get("name") or payload.get("given_name") or email.split("@", 1)[0] or "Google user").strip()
    return {
        "provider": "google",
        "subject": subject,
        "email": email,
        "name": name,
    }


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    encoded = parts[1]
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        return {}
    return data if isinstance(data, dict) else {}


async def _exchange_apple(config: ProviderConfig, request: Request, code: str) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            config.token_url,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_url(request, config.provider),
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        payload = token_response.json()
    id_token = str(payload.get("id_token") or "")
    if not id_token:
        raise SocialOAuthError("Apple did not return an account token.")
    claims = _decode_jwt_payload(id_token)
    email = str(claims.get("email") or "")
    display_name = email.split("@", 1)[0].replace(".", " ").strip().title() if email else "Apple user"
    return {
        "provider": config.provider,
        "subject": str(claims.get("sub") or ""),
        "email": email,
        "name": display_name,
    }


async def _exchange_x(config: ProviderConfig, request: Request, code: str, flow: dict[str, Any]) -> dict[str, str]:
    verifier = str(flow.get("code_verifier") or "")
    if not verifier:
            raise SocialOAuthError("Twitter sign-in session expired. Start again.")
    auth = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode("utf-8")).decode("ascii")
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            config.token_url,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": config.client_id,
                "redirect_uri": callback_url(request, config.provider),
                "code_verifier": verifier,
            },
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {auth}",
            },
        )
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not token:
            raise SocialOAuthError("Twitter did not return an access token.")
        profile_response = await client.get(
            config.profile_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        profile_response.raise_for_status()
        profile = profile_response.json().get("data") or {}
    return {
        "provider": config.provider,
        "subject": str(profile.get("id") or ""),
        "email": "",
        "name": str(profile.get("name") or profile.get("username") or "Twitter user"),
    }


async def complete_callback(provider: str, request: Request, code: str, state: str, flow_cookie: str | None) -> dict[str, str]:
    flow = read_signed_payload(flow_cookie, max_age_seconds=FLOW_COOKIE_MAX_AGE_SECONDS)
    if not flow:
        raise SocialOAuthError("Sign-in session expired. Start again.")
    normalized = _normalize_provider(provider)
    if flow.get("provider") != normalized or flow.get("state") != state:
        raise SocialOAuthError("Sign-in validation failed. Start again.")

    config = _provider_config(normalized)
    try:
        if normalized == "google":
            profile = await _exchange_google(config, request, code)
        elif normalized == "x":
            profile = await _exchange_x(config, request, code, flow)
        else:
            profile = await _exchange_apple(config, request, code)
    except httpx.HTTPError as error:
        raise SocialOAuthError(f"{social_provider_title(normalized)} sign-in could not be completed.") from error

    if not profile.get("subject"):
        raise SocialOAuthError(f"{social_provider_title(normalized)} did not return an account identifier.")
    return profile


def social_provider_title(provider: str) -> str:
    normalized = _normalize_provider(provider)
    labels = {
        "google": "Google",
        "x": "Twitter",
        "apple": "Apple",
    }
    return labels.get(normalized, normalized.title())


def social_provider_catalog(request: Request) -> list[dict[str, Any]]:
    """Return public provider readiness metadata for the login UI."""
    providers = [
        ("google", google_client_id(), settings.google_oauth_client_secret),
    ]
    payload: list[dict[str, Any]] = []
    for provider, client_id, client_secret in providers:
        payload.append(
            {
                "provider": provider,
                "label": social_provider_title(provider),
                "enabled": bool((client_id or "").strip() and (client_secret or "").strip()),
                "client_id": (client_id or "").strip(),
                "flow": "oauth_code",
                "callback_url": callback_url(request, provider),
            }
        )
    return payload
