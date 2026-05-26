"""Simple file-backed auth/session store for the web platform."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
from typing import Any
from uuid import uuid4


def _default_store_path() -> Path:
    configured = os.getenv("PLATFORM_AUTH_STORE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "output" / "platform" / "auth_state.json"


def _default_state() -> dict[str, Any]:
    return {"accounts": [], "sessions": {}}


def _normalize_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _normalize_email(value: Any) -> str:
    return _normalize_text(value, 160).lower()


def _normalize_provider(value: Any) -> str:
    provider = _normalize_text(value, 24).lower()
    if provider == "twitter":
        provider = "x"
    allowed = {"local", "google", "apple", "x"}
    return provider if provider in allowed else ""


def _normalize_subject(value: Any) -> str:
    return _normalize_text(value, 160)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


REQUIRED_AGREEMENT_KEYS = (
    "terms_required",
    "privacy_required",
    "investment_notice_required",
)
OPTIONAL_AGREEMENT_KEYS = ("marketing_optional",)
AGREEMENT_VERSION = "2026-03-28"


def _hash_password(password: str, *, salt: str | None = None) -> dict[str, str]:
    raw_salt = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, 120_000)
    return {
        "salt": raw_salt.hex(),
        "hash": digest.hex(),
    }


def _verify_password(password: str, *, salt: str, expected_hash: str) -> bool:
    candidate = _hash_password(password, salt=salt)["hash"]
    return hmac.compare_digest(candidate, expected_hash)


def _agreements_complete(agreements: Any) -> bool:
    if not isinstance(agreements, dict):
        return False
    for key in REQUIRED_AGREEMENT_KEYS:
        item = agreements.get(key)
        if not isinstance(item, dict) or not item.get("accepted"):
            return False
    return True


def _agreement_payload(agreements: dict[str, Any], *, require_required: bool) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    accepted_at = _now_iso()

    for key in (*REQUIRED_AGREEMENT_KEYS, *OPTIONAL_AGREEMENT_KEYS):
        accepted = bool(agreements.get(key))
        payload[key] = {
            "accepted": accepted,
            "accepted_at": accepted_at if accepted else None,
            "required": key in REQUIRED_AGREEMENT_KEYS,
            "version": AGREEMENT_VERSION,
        }

    if require_required:
        missing = [key for key in REQUIRED_AGREEMENT_KEYS if not payload[key]["accepted"]]
        if missing:
            raise ValueError("Agree to the required terms to continue.")

    return payload


class AuthStore:
    """Persist lightweight platform accounts and sessions in JSON."""

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
        except (OSError, json.JSONDecodeError):
            data = _default_state()

        return {
            "accounts": data.get("accounts", []) if isinstance(data.get("accounts"), list) else [],
            "sessions": data.get("sessions", {}) if isinstance(data.get("sessions"), dict) else {},
        }

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _public_user(self, account: dict[str, Any]) -> dict[str, str]:
        return {
            "id": account["id"],
            "name": account["name"],
            "email": account["email"],
            "provider": account.get("provider", "local"),
        }

    def _identity_payload(self, account: dict[str, Any]) -> dict[str, Any]:
        agreements = account.get("agreements") if isinstance(account.get("agreements"), dict) else {}
        linked = account.get("linked_providers") or [account.get("provider", "local")]
        linked_providers = sorted({
            provider for provider in (_normalize_provider(item) for item in linked) if provider
        })
        accepted_timestamps = [
            item.get("accepted_at")
            for item in agreements.values()
            if isinstance(item, dict) and item.get("accepted") and item.get("accepted_at")
        ]
        latest_accepted_at = max(accepted_timestamps) if accepted_timestamps else None
        return {
            "provider": account.get("provider", "local"),
            "linked_providers": linked_providers,
            "has_local_password": bool(account.get("password_hash") and account.get("password_salt")),
            "social_only": not bool(account.get("password_hash") and account.get("password_salt")),
            "agreements": agreements,
            "required_agreements_completed": _agreements_complete(agreements),
            "agreement_version": AGREEMENT_VERSION,
            "agreement_updated_at": latest_accepted_at,
            "created_at": account.get("created_at"),
            "updated_at": account.get("updated_at") or account.get("created_at"),
        }

    def _social_identities(self, account: dict[str, Any]) -> dict[str, dict[str, Any]]:
        identities = account.get("social_identities")
        if not isinstance(identities, dict):
            return {}
        payload: dict[str, dict[str, Any]] = {}
        for raw_provider, raw_identity in identities.items():
            provider = _normalize_provider(raw_provider)
            if not provider or not isinstance(raw_identity, dict):
                continue
            subject = _normalize_subject(raw_identity.get("subject"))
            if not subject:
                continue
            payload[provider] = {
                "subject": subject,
                "email": _normalize_email(raw_identity.get("email")),
                "name": _normalize_text(raw_identity.get("name"), 60),
                "linked_at": raw_identity.get("linked_at") or account.get("created_at") or _now_iso(),
            }
        return payload

    def _account_for_social_identity(
        self,
        state: dict[str, Any],
        *,
        provider: str,
        subject: str,
    ) -> dict[str, Any] | None:
        clean_provider = _normalize_provider(provider)
        clean_subject = _normalize_subject(subject)
        if not clean_provider or not clean_subject:
            return None
        for account in state["accounts"]:
            identity = self._social_identities(account).get(clean_provider)
            if identity and identity.get("subject") == clean_subject:
                return account
        return None

    def _link_social_identity(
        self,
        account: dict[str, Any],
        *,
        provider: str,
        subject: str,
        email: str = "",
        name: str = "",
    ) -> bool:
        clean_provider = _normalize_provider(provider)
        clean_subject = _normalize_subject(subject)
        clean_email = _normalize_email(email)
        clean_name = _normalize_text(name, 60)
        if not clean_provider or not clean_subject:
            return False

        changed = False
        identities = self._social_identities(account)
        existing = identities.get(clean_provider)
        existing_email = existing.get("email", "") if existing else ""
        existing_name = existing.get("name", "") if existing else ""
        existing_linked_at = existing.get("linked_at") if existing else _now_iso()
        next_identity = {
            "subject": clean_subject,
            "email": clean_email or existing_email,
            "name": clean_name or existing_name,
            "linked_at": existing_linked_at,
        }
        if existing != next_identity:
            identities[clean_provider] = next_identity
            account["social_identities"] = identities
            changed = True

        linked = {
            item
            for item in (_normalize_provider(raw) for raw in (account.get("linked_providers") or [account.get("provider", "local")]))
            if item
        }
        if clean_provider not in linked:
            linked.add(clean_provider)
            account["linked_providers"] = sorted(linked)
            changed = True

        if clean_name and clean_name != account.get("name"):
            account["name"] = clean_name
            changed = True
        if clean_email and clean_email != account.get("email"):
            account["email"] = clean_email
            changed = True
        if (not account.get("provider") or account.get("provider") == "local") and clean_provider != "local":
            account["provider"] = clean_provider
            changed = True
        if changed:
            account["updated_at"] = _now_iso()
        return changed

    def _issue_session(self, state: dict[str, Any], account: dict[str, Any]) -> tuple[dict[str, str], str]:
        token = secrets.token_urlsafe(32)
        state["sessions"][token] = {
            "account_id": account["id"],
            "created_at": _now_iso(),
        }
        return self._public_user(account), token

    def _account_for_id(self, state: dict[str, Any], account_id: str | None) -> dict[str, Any] | None:
        clean_account_id = _normalize_text(account_id, 64)
        if not clean_account_id:
            return None
        return next((item for item in state["accounts"] if item.get("id") == clean_account_id), None)

    def register(
        self,
        *,
        name: str,
        email: str,
        password: str,
        agreements: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], str]:
        clean_name = _normalize_text(name, 60)
        clean_email = _normalize_email(email)
        clean_password = str(password or "")

        if len(clean_name) < 2:
            raise ValueError("Name must be at least 2 characters.")
        if "@" not in clean_email or "." not in clean_email:
            raise ValueError("Enter a valid email.")
        if len(clean_password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        agreement_payload = _agreement_payload(agreements or {}, require_required=True)

        with self._lock:
            state = self._read()
            if any(item.get("email") == clean_email for item in state["accounts"]):
                raise ValueError("This email is already in use.")

            password_data = _hash_password(clean_password)
            account = {
                "id": f"user-{uuid4().hex[:12]}",
                "name": clean_name,
                "email": clean_email,
                "password_hash": password_data["hash"],
                "password_salt": password_data["salt"],
                "provider": "local",
                "linked_providers": ["local"],
                "agreements": agreement_payload,
                "created_at": _now_iso(),
            }
            token = secrets.token_urlsafe(32)
            state["accounts"].append(account)
            state["sessions"][token] = {
                "account_id": account["id"],
                "created_at": _now_iso(),
            }
            self._write(state)
            return self._public_user(account), token

    def login(self, *, email: str, password: str) -> tuple[dict[str, str], str]:
        clean_email = _normalize_email(email)
        clean_password = str(password or "")

        with self._lock:
            state = self._read()
            account = next((item for item in state["accounts"] if item.get("email") == clean_email), None)
            if account is None:
                raise ValueError("No account matches this email.")
            if not account.get("password_hash") or not account.get("password_salt"):
                raise ValueError("Use a social sign-in option for this account.")
            if not _verify_password(
                clean_password,
                salt=account["password_salt"],
                expected_hash=account["password_hash"],
            ):
                raise ValueError("Password does not match.")

            token = secrets.token_urlsafe(32)
            state["sessions"][token] = {
                "account_id": account["id"],
                "created_at": _now_iso(),
            }
            self._write(state)
            return self._public_user(account), token

    def social_complete(
        self,
        *,
        provider: str,
        name: str,
        email: str,
        subject: str | None = None,
        agreements: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], str]:
        clean_provider = _normalize_provider(provider)
        clean_name = _normalize_text(name, 60)
        clean_email = _normalize_email(email)
        clean_subject = _normalize_subject(subject)

        if clean_provider not in {"google", "apple", "x"}:
            raise ValueError("Choose a supported social account.")
        if len(clean_name) < 2:
            raise ValueError("Name must be at least 2 characters.")
        if "@" not in clean_email or "." not in clean_email:
            raise ValueError("Enter a valid email.")

        with self._lock:
            state = self._read()
            account = self._account_for_social_identity(state, provider=clean_provider, subject=clean_subject)
            if account is None:
                account = next((item for item in state["accounts"] if item.get("email") == clean_email), None)
            if account is None:
                account = {
                    "id": f"user-{uuid4().hex[:12]}",
                    "name": clean_name,
                    "email": clean_email,
                    "provider": clean_provider,
                    "linked_providers": [clean_provider],
                    "agreements": _agreement_payload(agreements or {}, require_required=True),
                    "created_at": _now_iso(),
                }
                if clean_subject:
                    self._link_social_identity(
                        account,
                        provider=clean_provider,
                        subject=clean_subject,
                        email=clean_email,
                        name=clean_name,
                    )
                state["accounts"].append(account)
            else:
                if clean_subject:
                    self._link_social_identity(
                        account,
                        provider=clean_provider,
                        subject=clean_subject,
                        email=clean_email,
                        name=clean_name,
                    )
                linked = {
                    _normalize_provider(item)
                    for item in (account.get("linked_providers") or [account.get("provider", "local")])
                }
                linked = {item for item in linked if item}
                linked.add(clean_provider)
                account["linked_providers"] = sorted(linked)
                if not _agreements_complete(account.get("agreements")):
                    account["agreements"] = _agreement_payload(agreements or {}, require_required=True)
                if clean_name and len(clean_name) >= 2:
                    account["name"] = clean_name
                if not account.get("provider") or account.get("provider") == "local":
                    account["provider"] = clean_provider
                account["updated_at"] = _now_iso()

            user, token = self._issue_session(state, account)
            self._write(state)
            return user, token

    def oauth_sign_in(
        self,
        *,
        provider: str,
        subject: str,
        email: str = "",
        name: str = "",
    ) -> tuple[dict[str, str], str] | None:
        clean_provider = _normalize_provider(provider)
        clean_subject = _normalize_subject(subject)
        clean_email = _normalize_email(email)
        clean_name = _normalize_text(name, 60)

        if clean_provider not in {"google", "apple", "x"}:
            raise ValueError("Choose a supported social account.")
        if not clean_subject:
            raise ValueError("Social account identifier is missing.")

        with self._lock:
            state = self._read()
            account = self._account_for_social_identity(state, provider=clean_provider, subject=clean_subject)
            changed = False
            if account is None and clean_email:
                account = next((item for item in state["accounts"] if item.get("email") == clean_email), None)
                if account is not None:
                    changed = self._link_social_identity(
                        account,
                        provider=clean_provider,
                        subject=clean_subject,
                        email=clean_email,
                        name=clean_name,
                    ) or changed
            elif account is not None:
                changed = self._link_social_identity(
                    account,
                    provider=clean_provider,
                    subject=clean_subject,
                    email=clean_email,
                    name=clean_name,
                ) or changed

            if account is None:
                return None

            if not _agreements_complete(account.get("agreements")):
                if changed:
                    self._write(state)
                return None

            user, token = self._issue_session(state, account)
            self._write(state)
            return user, token

    def user_for_token(self, token: str | None) -> dict[str, str] | None:
        if not token:
            return None

        with self._lock:
            state = self._read()
            session = state["sessions"].get(token)
            if not isinstance(session, dict):
                return None
            account_id = session.get("account_id")
            account = next((item for item in state["accounts"] if item.get("id") == account_id), None)
            if account is None:
                return None
            return self._public_user(account)

    def user_by_id(self, account_id: str | None) -> dict[str, str] | None:
        clean_account_id = _normalize_text(account_id, 64)
        if not clean_account_id:
            return None

        with self._lock:
            state = self._read()
            account = self._account_for_id(state, clean_account_id)
            if account is None:
                return None
            return self._public_user(account)

    def account_snapshot(self, account_id: str | None) -> dict[str, Any] | None:
        with self._lock:
            state = self._read()
            account = self._account_for_id(state, account_id)
            if account is None:
                return None
            return self._identity_payload(account)

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._lock:
            state = self._read()
            accounts: list[dict[str, Any]] = []
            for raw_account in state["accounts"]:
                if not isinstance(raw_account, dict):
                    continue
                identity = self._identity_payload(raw_account)
                accounts.append(
                    {
                        **self._public_user(raw_account),
                        "provider": identity["provider"],
                        "linked_providers": identity["linked_providers"],
                        "has_local_password": identity["has_local_password"],
                        "social_only": identity["social_only"],
                        "required_agreements_completed": identity["required_agreements_completed"],
                        "agreement_version": identity["agreement_version"],
                        "agreement_updated_at": identity["agreement_updated_at"],
                        "created_at": identity["created_at"],
                        "updated_at": identity["updated_at"],
                    }
                )
            accounts.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            return accounts

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            state = self._read()
            if token in state["sessions"]:
                del state["sessions"][token]
                self._write(state)


auth_store = AuthStore()
