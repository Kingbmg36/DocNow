"""Paystack payments service for DocNow.NG.

Two modes (controlled by PAYSTACK_ENABLED + PAYSTACK_SECRET_KEY):
  - stub → no external call. `initialize_transaction` returns a local mock checkout
           URL and `verify_transaction` reports success. Used in dev before real keys.
  - live → calls https://api.paystack.co with the secret key (Bearer auth), retrying
           on 5xx. Webhook signatures are verified with HMAC-SHA512 of the raw body.

Money: Paystack works in the smallest currency unit (kobo for NGN). The rest of the
app stores naira (float), so conversion happens only at the Paystack boundary via
`to_subunit` / `from_subunit`.

This mirrors the stub/live + retry + idempotency shape of `whatsapp_service.py`.
"""
import os
import hmac
import hashlib
import logging
import asyncio
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

PAYSTACK_ENABLED = os.environ.get("PAYSTACK_ENABLED", "false").lower() == "true"
SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
BASE_URL = "https://api.paystack.co"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


# ---------- Mode helpers ----------
def has_credentials() -> bool:
    return bool(SECRET_KEY)


def is_live() -> bool:
    """Live only when explicitly enabled AND a secret key is present."""
    return PAYSTACK_ENABLED and has_credentials()


def provider_name() -> str:
    return "paystack" if is_live() else "paystack_stub"


# ---------- Money conversion ----------
def to_subunit(amount_major: float) -> int:
    """Naira → kobo. Paystack expects an integer in the smallest unit."""
    return int(round(float(amount_major) * 100))


def from_subunit(amount_minor: int) -> float:
    """Kobo → naira."""
    return round(int(amount_minor) / 100, 2)


# ---------- Webhook signature ----------
def verify_signature(raw_body: bytes, signature: str) -> bool:
    """Verify Paystack's x-paystack-signature (HMAC-SHA512 of the raw body,
    keyed with the secret key). Constant-time comparison."""
    if not signature or not SECRET_KEY:
        return False
    expected = hmac.new(SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(signature, expected)


# ---------- HTTP client (lazy singleton) ----------
_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
    return _client


async def shutdown_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _request(method: str, path: str, *, json: Optional[dict] = None) -> dict:
    """Call Paystack with retries on 5xx / network errors. Raises on terminal error."""
    if not SECRET_KEY:
        raise RuntimeError("PAYSTACK_SECRET_KEY not configured")
    client = await _get_client()
    headers = {
        "Authorization": f"Bearer {SECRET_KEY}",
        "Content-Type": "application/json",
    }
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.request(method, path, json=json, headers=headers)
            if 500 <= resp.status_code < 600:
                last_err = RuntimeError(f"Paystack {resp.status_code}: {resp.text[:200]}")
            else:
                # 4xx carries an actionable Paystack message — surface it, don't retry.
                data = resp.json()
                if not resp.is_success or not data.get("status"):
                    raise RuntimeError(f"Paystack error: {data.get('message', resp.text[:200])}")
                return data
        except httpx.HTTPError as e:
            last_err = e
        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    assert last_err is not None
    raise last_err


# ---------- Public operations ----------
async def initialize_transaction(
    *,
    email: str,
    amount_major: float,
    reference: str,
    currency: str = "NGN",
    callback_url: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Start a transaction. Returns {authorization_url, access_code, reference, live}.

    In stub mode returns a local mock checkout URL so the dev flow works with no keys.
    """
    if not is_live():
        log.info("[Paystack stub] initialize %s → %.2f %s", reference, amount_major, currency)
        return {
            "authorization_url": f"/mock-paystack?ref={reference}",
            "access_code": f"stub_{reference}",
            "reference": reference,
            "live": False,
        }

    payload: dict[str, Any] = {
        "email": email,
        "amount": to_subunit(amount_major),
        "reference": reference,
        "currency": currency,
    }
    if callback_url:
        payload["callback_url"] = callback_url
    if metadata:
        payload["metadata"] = metadata

    data = await _request("POST", "/transaction/initialize", json=payload)
    d = data.get("data", {}) or {}
    return {
        "authorization_url": d.get("authorization_url"),
        "access_code": d.get("access_code"),
        "reference": d.get("reference", reference),
        "live": True,
    }


async def verify_transaction(reference: str) -> dict:
    """Verify a transaction with Paystack. Returns a normalised dict:
    {status, amount_major, currency, paid_at, gateway_response, raw}.

    In stub mode reports success (dev). `status` is Paystack's transaction status
    string ("success", "failed", "abandoned", …).
    """
    if not is_live():
        log.info("[Paystack stub] verify %s → success", reference)
        return {
            "status": "success",
            "amount_major": None,   # unknown in stub; caller skips the amount check
            "currency": "NGN",
            "paid_at": None,
            "gateway_response": "Successful (stub)",
            "raw": {"stub": True},
        }

    data = await _request("GET", f"/transaction/verify/{reference}")
    d = data.get("data", {}) or {}
    return {
        "status": d.get("status"),
        "amount_major": from_subunit(d.get("amount", 0)),
        "currency": d.get("currency", "NGN"),
        "paid_at": d.get("paid_at"),
        "gateway_response": d.get("gateway_response"),
        "raw": d,
    }
