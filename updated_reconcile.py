#!/usr/bin/env python3
"""Payment reconciliation.

Reads payments.jsonl and works out how much money we actually collected.
Run:  python3 reconcile.py
"""
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

EPOCH_MIN = datetime.min.replace(tzinfo=timezone.utc)


def parse_ts(value):
    """Parse a UTC timestamp (ISO string or epoch) into an aware datetime."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 1e11 else value  # ms vs s
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        s = str(value).strip()
        if not s:
            return None
        try:
            seconds = float(s)
            seconds = seconds / 1000 if seconds > 1e11 else seconds
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except ValueError:
            pass
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s.replace(" ", "T", 1) if "T" not in s else s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def parse_amount(raw):
    """Exact Decimal from 1500, 1500.5, '1,500.50', '₦1500'. None if unusable."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.replace(",", "").replace("₦", "").strip()
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


# txn_id -> (sort_key, status, amount); keep only the latest attempt.
latest = {}

with open("payments.jsonl", encoding="utf-8-sig", errors="replace") as f:
    for line_no, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        txn_id = event.get("txn_id")
        if txn_id is None or str(txn_id).strip() == "":
            continue
        txn_id = str(txn_id).strip()

        status = str(event.get("status", "")).strip().lower()
        ts = parse_ts(event.get("ts")) or EPOCH_MIN
        # Later ts wins; if ts ties, the later line in the file wins.
        key = (ts, line_no)

        if txn_id not in latest or key > latest[txn_id][0]:
            latest[txn_id] = (key, status, parse_amount(event.get("amount")))

total = Decimal("0")
count = 0
for _key, status, amount in latest.values():
    if status == "success":
        count += 1
        if amount is not None:
            total += amount

with open("expected.txt") as f:
    expected = int(f.read().strip())

if count != expected:
    print(f"Check failed: counted {count} successful payments, expected {expected}.")
    print("Something in the data isn't being handled the way the README describes.")
else:
    print(f"Check passed: {count} successful payments.")
    print(f"Your code: KOYA-{int(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))}")
