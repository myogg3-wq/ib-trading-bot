"""Review manual credit top-up requests for the platform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.web.auth_store import auth_store
from app.web.commerce_store import commerce_store


def cmd_list() -> int:
    requests = commerce_store.list_payment_requests()
    if not requests:
        print("No payment requests.")
        return 0

    for item in requests:
        user = auth_store.user_by_id(item.get("account_id")) or {}
        print(
            " | ".join(
                [
                    item.get("id", ""),
                    item.get("status", ""),
                    user.get("email", item.get("account_id", "")),
                    f"{item.get('credits_total', 0)} credits",
                    f"₩{item.get('amount_krw', 0):,}",
                    item.get("reference", ""),
                ]
            )
        )
    return 0


def cmd_review(request_id: str, decision: str, note: str) -> int:
    result = commerce_store.review_payment_request(request_id=request_id, decision=decision, note=note)
    account = result["account"]
    request = result["request"]
    print(
        f"{decision.upper()}: {request['id']} | status={request['status']} | "
        f"balance={account['credits_balance']} | reviewed_at={request.get('reviewed_at', '')}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review platform payment requests")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all payment requests")

    approve = sub.add_parser("approve", help="Approve a request")
    approve.add_argument("request_id")
    approve.add_argument("--note", default="")

    reject = sub.add_parser("reject", help="Reject a request")
    reject.add_argument("request_id")
    reject.add_argument("--note", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "list":
        return cmd_list()
    if args.command == "approve":
        return cmd_review(args.request_id, "approved", args.note)
    if args.command == "reject":
        return cmd_review(args.request_id, "rejected", args.note)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
