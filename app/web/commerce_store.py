"""File-backed commerce state for credits, unlocks, and subscriptions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4


SECTION_COSTS = {
    "model-briefs": 3,
    "entry-window": 5,
    "objective-data": 6,
    "risk-map": 4,
    "scenario-tree": 4,
    "model-notes": 7,
    "decision-sheet": 3,
}

PRODUCT_COSTS = {
    "membership": 12,
    "desk-pass": 7,
    "follow-pass": 4,
    "alerts": 4,
    "recent-rank": 3,
    "bundle": max(9, round(sum(SECTION_COSTS.values()) * 0.4)),
    "archive": 6,
}

CREDIT_PACKS = {
    "starter": {"credits": 24, "price_krw": 3900, "bonus_credits": 0},
    "plus": {"credits": 70, "price_krw": 8900, "bonus_credits": 10},
    "pro": {"credits": 180, "price_krw": 18900, "bonus_credits": 30},
}

PAYMENT_METHODS = {
    "bank-transfer": {
        "kind": "manual",
        "settles_in": "same-day",
    },
    "manual-card-request": {
        "kind": "manual",
        "settles_in": "review",
    },
}

STARTER_CREDITS = 24
MEMBERSHIP_CREDIT_TOPUP = 30
MEMBERSHIP_DAYS = 30


def _default_store_path() -> Path:
    configured = os.getenv("PLATFORM_COMMERCE_STORE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "output" / "platform" / "commerce_state.json"


def _default_state() -> dict[str, Any]:
    return {"accounts": {}}


def _normalize_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _normalize_ticker(value: Any) -> str:
    return _normalize_text(value, 12).upper()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _payment_method_details() -> dict[str, dict[str, Any]]:
    bank_name = _normalize_text(os.getenv("PLATFORM_BANK_NAME", "입금 계좌 안내"), 80)
    account_number = _normalize_text(os.getenv("PLATFORM_BANK_ACCOUNT", "운영자 설정 필요"), 80)
    account_holder = _normalize_text(os.getenv("PLATFORM_BANK_HOLDER", "Signal Loom"), 80)
    support_note = _normalize_text(
        os.getenv("PLATFORM_PAYMENT_SUPPORT_NOTE", "입금 확인 후 최대 1영업일 안에 크레딧이 반영됩니다."),
        160,
    )
    card_note = _normalize_text(
        os.getenv("PLATFORM_CARD_REQUEST_NOTE", "카드 결제 요청을 남기면 운영자가 수동 결제 안내를 보냅니다."),
        160,
    )
    return {
        "bank-transfer": {
            "title": "국내 계좌이체",
            "lines": [bank_name, account_number, account_holder],
            "note": support_note,
        },
        "manual-card-request": {
            "title": "국내 카드 결제 요청",
            "lines": ["운영자 수동 안내", "별도 결제 링크 또는 요청 응답"],
            "note": card_note,
        },
    }


def _account_state() -> dict[str, Any]:
    return {
        "credits_balance": STARTER_CREDITS,
        "membership_active": False,
        "membership_expires_at": "",
        "membership_days_left": 0,
        "alerts_active": False,
        "archive_active": False,
        "recent_rank_active": False,
        "follow_pass_active": False,
        "desk_passes": [],
        "bundle_tickers": [],
        "unlocked_sections": {},
        "payment_requests": [],
        "alert_preferences": {
            "buy": True,
            "watch": True,
            "sell": True,
            "research": False,
        },
        "transactions": [],
    }


class CommerceStore:
    """Persist platform credits and unlocks in JSON."""

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
            "accounts": data.get("accounts", {}) if isinstance(data.get("accounts"), dict) else {},
        }

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ensure_account(self, state: dict[str, Any], account_id: str) -> dict[str, Any]:
        clean_account_id = _normalize_text(account_id, 64)
        if not clean_account_id:
            raise ValueError("Account id is required.")

        if clean_account_id not in state["accounts"] or not isinstance(state["accounts"][clean_account_id], dict):
            state["accounts"][clean_account_id] = _account_state()
        else:
            current = state["accounts"][clean_account_id]
            merged = _account_state()
            merged.update(current)
            merged["desk_passes"] = current.get("desk_passes", []) if isinstance(current.get("desk_passes"), list) else []
            merged["bundle_tickers"] = current.get("bundle_tickers", []) if isinstance(current.get("bundle_tickers"), list) else []
            merged["unlocked_sections"] = current.get("unlocked_sections", {}) if isinstance(current.get("unlocked_sections"), dict) else {}
            merged["payment_requests"] = current.get("payment_requests", []) if isinstance(current.get("payment_requests"), list) else []
            merged["alert_preferences"] = {
                **_account_state()["alert_preferences"],
                **(current.get("alert_preferences", {}) if isinstance(current.get("alert_preferences"), dict) else {}),
            }
            merged["transactions"] = current.get("transactions", []) if isinstance(current.get("transactions"), list) else []
            state["accounts"][clean_account_id] = merged

        return state["accounts"][clean_account_id]

    def _normalize_account_runtime(self, account: dict[str, Any]) -> None:
        now = _now()
        membership_days_left = 0
        expiry_raw = _normalize_text(account.get("membership_expires_at", ""), 64)

        if expiry_raw:
            try:
                expiry = datetime.fromisoformat(expiry_raw)
            except ValueError:
                expiry = None
            if expiry and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry and expiry > now:
                seconds_left = max((expiry - now).total_seconds(), 0)
                membership_days_left = max(1, int((seconds_left + 86399) // 86400))
                account["membership_active"] = True
                account["membership_expires_at"] = expiry.isoformat()
            else:
                account["membership_active"] = False
                account["membership_expires_at"] = ""

        account["membership_days_left"] = membership_days_left

        normalized_requests = []
        for raw_request in account.get("payment_requests", []):
            if not isinstance(raw_request, dict):
                continue
            request = {
                "id": _normalize_text(raw_request.get("id"), 48) or f"pay-{uuid4().hex[:12]}",
                "account_id": _normalize_text(raw_request.get("account_id"), 64),
                "pack_id": _normalize_text(raw_request.get("pack_id"), 24),
                "method": _normalize_text(raw_request.get("method"), 32),
                "status": _normalize_text(raw_request.get("status"), 24) or "pending",
                "credits": int(raw_request.get("credits") or 0),
                "bonus_credits": int(raw_request.get("bonus_credits") or 0),
                "amount_krw": int(raw_request.get("amount_krw") or 0),
                "depositor_name": _normalize_text(raw_request.get("depositor_name"), 80),
                "note": _normalize_text(raw_request.get("note"), 180),
                "reference": _normalize_text(raw_request.get("reference"), 32),
                "created_at": _normalize_text(raw_request.get("created_at"), 64),
                "expires_at": _normalize_text(raw_request.get("expires_at"), 64),
                "reviewed_at": _normalize_text(raw_request.get("reviewed_at"), 64),
                "review_note": _normalize_text(raw_request.get("review_note"), 180),
            }

            expiry_raw = request["expires_at"]
            if request["status"] == "pending" and expiry_raw:
                try:
                    expiry = datetime.fromisoformat(expiry_raw)
                except ValueError:
                    expiry = None
                if expiry and expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry and expiry <= now:
                    request["status"] = "expired"

            normalized_requests.append(request)

        account["payment_requests"] = normalized_requests[:20]

    def _record_transaction(
        self,
        account: dict[str, Any],
        *,
        kind: str,
        title: str,
        credits_delta: int,
        ticker: str = "",
        author_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        account["transactions"].insert(
            0,
            {
                "id": f"txn-{uuid4().hex[:12]}",
                "kind": kind,
                "title": title,
                "credits_delta": credits_delta,
                "ticker": ticker,
                "author_id": author_id,
                "metadata": metadata or {},
                "created_at": _now_iso(),
            },
        )
        account["transactions"] = account["transactions"][:30]

    def catalog(self) -> dict[str, Any]:
        return {
            "section_costs": deepcopy(SECTION_COSTS),
            "product_costs": deepcopy(PRODUCT_COSTS),
            "starter_credits": STARTER_CREDITS,
            "membership_credit_topup": MEMBERSHIP_CREDIT_TOPUP,
            "credit_packs": [
                {
                    "id": pack_id,
                    "credits": pack["credits"],
                    "bonus_credits": pack["bonus_credits"],
                    "total_credits": pack["credits"] + pack["bonus_credits"],
                    "price_krw": pack["price_krw"],
                }
                for pack_id, pack in CREDIT_PACKS.items()
            ],
            "payment_methods": [
                {
                    "id": method_id,
                    "kind": method["kind"],
                    "settles_in": method["settles_in"],
                    "details": _payment_method_details().get(method_id, {}),
                }
                for method_id, method in PAYMENT_METHODS.items()
            ],
        }

    def snapshot(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            account = self._ensure_account(state, account_id)
            self._normalize_account_runtime(account)
            self._write(state)
            return deepcopy(account)

    def unlock_sections(self, *, account_id: str, ticker: str, section_ids: list[str]) -> dict[str, Any]:
        clean_ticker = _normalize_ticker(ticker)
        if not clean_ticker:
            raise ValueError("Ticker is required.")

        normalized_sections = []
        for section_id in section_ids:
            clean_id = _normalize_text(section_id, 40)
            if clean_id in SECTION_COSTS and clean_id not in normalized_sections:
                normalized_sections.append(clean_id)

        if not normalized_sections:
            raise ValueError("Select at least one paid research section.")

        with self._lock:
            state = self._read()
            account = self._ensure_account(state, account_id)
            self._normalize_account_runtime(account)
            unlocked_for_ticker = set(account["unlocked_sections"].get(clean_ticker, []))
            pending = [section_id for section_id in normalized_sections if section_id not in unlocked_for_ticker]
            if not pending:
                return deepcopy(account)

            total_cost = sum(SECTION_COSTS[section_id] for section_id in pending)
            if account["credits_balance"] < total_cost:
                raise ValueError("Not enough credits.")

            account["credits_balance"] -= total_cost
            unlocked_for_ticker.update(pending)
            account["unlocked_sections"][clean_ticker] = sorted(unlocked_for_ticker)
            self._record_transaction(
                account,
                kind="section-unlock",
                title=f"{clean_ticker} premium sections",
                credits_delta=-total_cost,
                ticker=clean_ticker,
                metadata={"section_ids": pending},
            )
            self._write(state)
            return deepcopy(account)

    def purchase_product(
        self,
        *,
        account_id: str,
        product_id: str,
        ticker: str = "",
        author_id: str = "",
    ) -> dict[str, Any]:
        clean_product_id = _normalize_text(product_id, 32)
        clean_ticker = _normalize_ticker(ticker)
        clean_author_id = _normalize_text(author_id, 64)
        if clean_product_id not in PRODUCT_COSTS:
            raise ValueError("Unsupported product.")

        with self._lock:
            state = self._read()
            account = self._ensure_account(state, account_id)
            self._normalize_account_runtime(account)

            if clean_product_id == "desk-pass" and not clean_author_id:
                raise ValueError("Desk pass requires an AI desk.")
            if clean_product_id == "bundle" and not clean_ticker:
                raise ValueError("Bundle purchase requires a ticker.")

            # Idempotent entitlements should not charge twice.
            if clean_product_id == "alerts" and account["alerts_active"]:
                return deepcopy(account)
            if clean_product_id == "archive" and account["archive_active"]:
                return deepcopy(account)
            if clean_product_id == "recent-rank" and account["recent_rank_active"]:
                return deepcopy(account)
            if clean_product_id == "follow-pass" and account["follow_pass_active"]:
                return deepcopy(account)
            if clean_product_id == "desk-pass" and clean_author_id in account["desk_passes"]:
                return deepcopy(account)
            if clean_product_id == "bundle" and clean_ticker in account["bundle_tickers"]:
                return deepcopy(account)

            cost = PRODUCT_COSTS[clean_product_id]
            if account["credits_balance"] < cost:
                raise ValueError("Not enough credits.")

            account["credits_balance"] -= cost

            if clean_product_id == "membership":
                existing_expiry = account.get("membership_expires_at") or ""
                base_time = _now()
                if existing_expiry:
                    try:
                        parsed = datetime.fromisoformat(existing_expiry)
                        if parsed > base_time:
                            base_time = parsed
                    except ValueError:
                        pass
                account["membership_active"] = True
                account["membership_expires_at"] = (base_time + timedelta(days=MEMBERSHIP_DAYS)).isoformat()
                account["credits_balance"] += MEMBERSHIP_CREDIT_TOPUP
                self._record_transaction(
                    account,
                    kind="membership",
                    title="Monthly membership",
                    credits_delta=MEMBERSHIP_CREDIT_TOPUP - cost,
                    metadata={"credits_added": MEMBERSHIP_CREDIT_TOPUP},
                )
            elif clean_product_id == "desk-pass":
                account["desk_passes"] = sorted(set(account["desk_passes"]) | {clean_author_id})
                self._record_transaction(
                    account,
                    kind="desk-pass",
                    title="AI desk pass",
                    credits_delta=-cost,
                    author_id=clean_author_id,
                )
            elif clean_product_id == "alerts":
                account["alerts_active"] = True
                self._record_transaction(
                    account,
                    kind="alerts",
                    title="Live alert unlock",
                    credits_delta=-cost,
                )
            elif clean_product_id == "recent-rank":
                account["recent_rank_active"] = True
                self._record_transaction(
                    account,
                    kind="recent-rank",
                    title="Recent return ranking unlock",
                    credits_delta=-cost,
                )
            elif clean_product_id == "follow-pass":
                account["follow_pass_active"] = True
                self._record_transaction(
                    account,
                    kind="follow-pass",
                    title="Following feed unlock",
                    credits_delta=-cost,
                )
            elif clean_product_id == "bundle":
                unlocked = set(account["unlocked_sections"].get(clean_ticker, []))
                unlocked.update(SECTION_COSTS.keys())
                account["unlocked_sections"][clean_ticker] = sorted(unlocked)
                account["bundle_tickers"] = sorted(set(account["bundle_tickers"]) | {clean_ticker})
                self._record_transaction(
                    account,
                    kind="bundle",
                    title=f"{clean_ticker} research bundle",
                    credits_delta=-cost,
                    ticker=clean_ticker,
                    metadata={"section_ids": sorted(SECTION_COSTS)},
                )
            elif clean_product_id == "archive":
                account["archive_active"] = True
                self._record_transaction(
                    account,
                    kind="archive",
                    title="Result archive unlock",
                    credits_delta=-cost,
                )

            self._write(state)
            return deepcopy(account)

    def update_alert_preferences(self, *, account_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            account = self._ensure_account(state, account_id)
            self._normalize_account_runtime(account)
            normalized = {}
            for key in ("buy", "watch", "sell", "research"):
                if key in preferences:
                    normalized[key] = bool(preferences[key])
            account["alert_preferences"] = {
                **account["alert_preferences"],
                **normalized,
            }
            self._write(state)
            return deepcopy(account)

    def create_payment_request(
        self,
        *,
        account_id: str,
        pack_id: str,
        method: str,
        depositor_name: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        clean_pack_id = _normalize_text(pack_id, 24)
        clean_method = _normalize_text(method, 32)
        clean_depositor = _normalize_text(depositor_name, 80)
        clean_note = _normalize_text(note, 180)

        if clean_pack_id not in CREDIT_PACKS:
            raise ValueError("Unsupported credit pack.")
        if clean_method not in PAYMENT_METHODS:
            raise ValueError("Unsupported payment method.")
        if clean_method == "bank-transfer" and not clean_depositor:
            raise ValueError("Depositor name is required for bank transfer.")

        with self._lock:
            state = self._read()
            account = self._ensure_account(state, account_id)
            self._normalize_account_runtime(account)

            pack = CREDIT_PACKS[clean_pack_id]
            request = {
                "id": f"pay-{uuid4().hex[:12]}",
                "account_id": account_id,
                "pack_id": clean_pack_id,
                "method": clean_method,
                "status": "pending",
                "credits": pack["credits"],
                "bonus_credits": pack["bonus_credits"],
                "amount_krw": pack["price_krw"],
                "depositor_name": clean_depositor,
                "note": clean_note,
                "reference": uuid4().hex[:8].upper(),
                "created_at": _now_iso(),
                "expires_at": (_now() + timedelta(days=2)).isoformat(),
            }
            account["payment_requests"].insert(0, request)
            account["payment_requests"] = account["payment_requests"][:20]
            self._record_transaction(
                account,
                kind="payment-request",
                title=f"{pack['credits'] + pack['bonus_credits']} credit top-up request",
                credits_delta=0,
                metadata={
                    "pack_id": clean_pack_id,
                    "method": clean_method,
                    "amount_krw": pack["price_krw"],
                    "reference": request["reference"],
                },
            )
            self._write(state)
            return deepcopy(account)

    def list_payment_requests(self) -> list[dict[str, Any]]:
        with self._lock:
            state = self._read()
            requests: list[dict[str, Any]] = []
            for account_id, raw_account in state["accounts"].items():
                if not isinstance(raw_account, dict):
                    continue
                account = self._ensure_account(state, account_id)
                self._normalize_account_runtime(account)
                for request in account.get("payment_requests", []):
                    if not isinstance(request, dict):
                        continue
                    requests.append(
                        {
                            **deepcopy(request),
                            "account_id": account_id,
                            "credits_total": int(request.get("credits", 0)) + int(request.get("bonus_credits", 0)),
                        }
                    )
            self._write(state)
            requests.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            return requests

    def review_payment_request(self, *, request_id: str, decision: str, note: str = "") -> dict[str, Any]:
        clean_request_id = _normalize_text(request_id, 48)
        clean_decision = _normalize_text(decision, 16).lower()
        clean_note = _normalize_text(note, 180)
        if clean_decision not in {"approved", "rejected"}:
            raise ValueError("Unsupported decision.")
        if not clean_request_id:
            raise ValueError("Payment request id is required.")

        with self._lock:
            state = self._read()
            for account_id in list(state["accounts"].keys()):
                account = self._ensure_account(state, account_id)
                self._normalize_account_runtime(account)
                for request in account.get("payment_requests", []):
                    if request.get("id") != clean_request_id:
                        continue
                    if request.get("status") != "pending":
                        return {
                            "account": deepcopy(account),
                            "request": deepcopy(request),
                        }

                    request["status"] = clean_decision
                    request["reviewed_at"] = _now_iso()
                    request["review_note"] = clean_note

                    if clean_decision == "approved":
                        credits_total = int(request.get("credits", 0)) + int(request.get("bonus_credits", 0))
                        account["credits_balance"] += credits_total
                        self._record_transaction(
                            account,
                            kind="payment-approved",
                            title=f"{credits_total} credit top-up approved",
                            credits_delta=credits_total,
                            metadata={
                                "request_id": clean_request_id,
                                "amount_krw": int(request.get("amount_krw", 0)),
                                "method": request.get("method", ""),
                                "reference": request.get("reference", ""),
                            },
                        )
                    else:
                        self._record_transaction(
                            account,
                            kind="payment-rejected",
                            title="Top-up request rejected",
                            credits_delta=0,
                            metadata={
                                "request_id": clean_request_id,
                                "reference": request.get("reference", ""),
                                "note": clean_note,
                            },
                        )

                    self._write(state)
                    return {
                        "account": deepcopy(account),
                        "request": deepcopy(request),
                    }

        raise ValueError("Payment request not found.")


commerce_store = CommerceStore()
