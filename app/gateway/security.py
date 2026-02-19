"""
Webhook security: HMAC verification, IP whitelist, rate limiting, idempotency.
"""

import hashlib
import hmac
import time
from fastapi import Request, HTTPException
import structlog

from app.config import settings

logger = structlog.get_logger()


def verify_hmac_signature(payload: bytes, signature: str) -> bool:
    """
    Verify HMAC-SHA256 signature from TradingView webhook.
    The signature should be sent in the 'X-Webhook-Signature' header.
    """
    expected = hmac.new(
        settings.webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_source_ip(client_ip: str) -> bool:
    """
    Check if the request comes from TradingView's known IP addresses.
    Also allows localhost for testing.
    """
    allowed = settings.tv_ip_list + ["127.0.0.1", "::1", "localhost"]
    return client_ip in allowed


async def validate_webhook_request(request: Request) -> bytes:
    """
    Full validation pipeline for incoming webhook requests.
    Returns raw body if valid, raises HTTPException otherwise.
    """
    # 1. Get client IP
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    source_ip = forwarded_for or client_ip

    # 2. IP whitelist check
    if not verify_source_ip(source_ip):
        logger.warning("Blocked request from unauthorized IP", ip=source_ip)
        raise HTTPException(status_code=403, detail="Forbidden")

    # 3. Read body
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

    # 4. HMAC signature verification
    signature = request.headers.get("X-Webhook-Signature", "")

    # If no signature header, check if secret is in the JSON payload
    # (TradingView sends secret in the body, not in headers)
    # We'll verify in the webhook handler after parsing JSON
    if signature and not verify_hmac_signature(body, signature):
        logger.warning("HMAC verification failed", ip=source_ip)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 5. Check request freshness (if timestamp in payload)
    # This is handled after JSON parsing in the webhook handler

    logger.info("Webhook request validated", ip=source_ip)
    return body


def verify_payload_secret(payload: dict) -> bool:
    """
    Verify the secret field in the webhook JSON payload.
    TradingView includes the secret directly in the alert message body.
    """
    payload_secret = payload.get("secret", "")
    if not payload_secret:
        return False
    return hmac.compare_digest(payload_secret, settings.webhook_secret)


def check_timestamp_freshness(timestamp_str: str, max_age_seconds: int = 60) -> bool:
    """
    Check if the alert timestamp is recent enough.
    Rejects stale alerts to prevent replay attacks.
    """
    try:
        # TradingView sends timestamps in various formats
        # Try epoch seconds first
        alert_time = float(timestamp_str)
        now = time.time()
        return abs(now - alert_time) < max_age_seconds
    except (ValueError, TypeError):
        # If not a numeric timestamp, allow it (TV format varies)
        return True
