"""SMS delivery for DocNow.NG via Termii (Nigeria-focused SMS gateway).

Two modes (controlled by SMS_ENABLED + TERMII_API_KEY), mirroring
whatsapp_service.py / paystack_service.py / email_service.py:
  - stub → log + persist to `sms_messages` with status='stubbed'. No network.
  - live → POST https://api.ng.termii.com/api/sms/send, retry on 5xx.

Termii wants the recipient in digits-only international format (no leading +),
same normalisation as whatsapp_service._to_e164_digits.
"""
import os
import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
from db import db

log = logging.getLogger(__name__)

SMS_ENABLED = os.environ.get("SMS_ENABLED", "false").lower() == "true"
TERMII_API_KEY = os.environ.get("TERMII_API_KEY", "")
TERMII_SENDER_ID = os.environ.get("TERMII_SENDER_ID", "DocNow")
BASE_URL = "https://api.ng.termii.com"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


def has_credentials() -> bool:
    return bool(TERMII_API_KEY)


def is_live() -> bool:
    return SMS_ENABLED and has_credentials()


def provider_name() -> str:
    return "termii" if is_live() else "termii_stub"


def _to_digits(phone: str) -> str:
    """+2348012345678 -> 2348012345678. Termii wants digits-only, no leading +."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


# ---------- HTTP client (lazy singleton) ----------
_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(15.0, connect=5.0))
    return _client


async def shutdown_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------- Idempotency + persistence ----------
async def _check_idempotency(idempotency_key: str) -> Optional[dict]:
    existing = await db.sms_messages.find_one({"idempotency_key": idempotency_key})
    if existing:
        existing.pop("_id", None)
        return existing
    return None


async def _persist(
    to_phone: str, body: str, *, status: str, category: str,
    idempotency_key: str, provider_message_id: Optional[str] = None, error: Optional[str] = None,
) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "phone_number": to_phone,
        "body": body,
        "category": category,           # otp | notification
        "status": status,               # stubbed | sent | failed
        "provider": provider_name(),
        "provider_message_id": provider_message_id,
        "error": error,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sms_messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _post_to_termii(payload: dict) -> dict:
    if not TERMII_API_KEY:
        raise RuntimeError("TERMII_API_KEY not configured")
    client = await _get_client()
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post("/api/sms/send", json=payload)
            if 500 <= resp.status_code < 600:
                last_err = RuntimeError(f"Termii {resp.status_code}: {resp.text[:200]}")
            else:
                data = resp.json()
                # Termii returns {"code": "ok", ...} on success; anything else is an error.
                if not resp.is_success or data.get("code") not in (None, "ok"):
                    raise RuntimeError(f"Termii error: {data.get('message', resp.text[:200])}")
                return data
        except httpx.HTTPError as e:
            last_err = e
        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    assert last_err is not None
    raise last_err


async def send_sms(
    to_phone: str, body: str, *, category: str = "notification", idempotency_key: Optional[str] = None,
) -> dict:
    idempotency_key = idempotency_key or f"sms:{category}:{to_phone}:{uuid.uuid4()}"
    if (existing := await _check_idempotency(idempotency_key)):
        return existing

    if not is_live():
        log.info("[SMS stub] to=%s | %s", to_phone, body[:80])
        return await _persist(to_phone, body, status="stubbed", category=category, idempotency_key=idempotency_key)

    payload = {
        "to": _to_digits(to_phone),
        "from": TERMII_SENDER_ID,
        "sms": body,
        "type": "plain",
        "channel": "generic",
        "api_key": TERMII_API_KEY,
    }
    try:
        resp = await _post_to_termii(payload)
        return await _persist(
            to_phone, body, status="sent", category=category, idempotency_key=idempotency_key,
            provider_message_id=resp.get("message_id"),
        )
    except Exception as e:
        log.exception("SMS send failed to %s", to_phone)
        return await _persist(to_phone, body, status="failed", category=category,
                               idempotency_key=idempotency_key, error=str(e))


async def send_otp_via_sms(phone: str, code: str, ttl_minutes: int = 10) -> dict:
    body = f"Your DocNow.NG verification code is {code}. It expires in {ttl_minutes} minutes. Do not share this code."
    return await send_sms(phone, body, category="otp", idempotency_key=f"otp-sms:{phone}:{code}")
