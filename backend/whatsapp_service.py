"""WhatsApp Cloud API service for DocNow.NG.

Two modes (controlled by WHATSAPP_ENABLED env):
  - stub  → log payload + persist to `whatsapp_messages` with status='stubbed'.
            Used in dev when Meta credentials aren't set yet.
  - live  → POST to https://graph.facebook.com/{vN}/{phone_number_id}/messages
            with bearer token, retry on 5xx, idempotency keyed in Mongo.

Templates are referenced by name (must be pre-approved in Meta Business Manager).
The phone E.164 format (e.g., +2348012345678) is normalised to digits-only on send
(Meta wants "2348012345678" without the leading +).

Idempotency: outbound calls accept an optional idempotency_key. If the same key
has already produced a wamid, the existing message doc is returned and no
duplicate is sent — prevents double-reminders on retry storms.
"""
import os
import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from db import db

log = logging.getLogger(__name__)

WHATSAPP_ENABLED = os.environ.get("WHATSAPP_ENABLED", "false").lower() == "true"
API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v22.0")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")

BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}" if PHONE_NUMBER_ID else None

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


# ---------- Phone normalisation ----------
def _to_e164_digits(phone: str) -> str:
    """Convert +2348012345678 → 2348012345678. Meta wants digits-only."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


# ---------- HTTP client (lazy singleton) ----------
_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    return _client


async def shutdown_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------- Idempotency ----------
async def _check_idempotency(idempotency_key: str) -> Optional[dict]:
    existing = await db.whatsapp_messages.find_one({"idempotency_key": idempotency_key})
    if existing:
        existing.pop("_id", None)
        return existing
    return None


# ---------- Core send ----------
async def _post_to_meta(payload: dict) -> dict:
    """POST to Meta with retries on 5xx. Raises on terminal error."""
    if not BASE_URL or not ACCESS_TOKEN:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN not configured")
    client = await _get_client()
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post(f"{BASE_URL}/messages", json=payload, headers=headers)
            if 500 <= resp.status_code < 600:
                last_err = RuntimeError(f"Meta {resp.status_code}: {resp.text[:200]}")
            else:
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            last_err = e
        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    assert last_err is not None
    raise last_err


async def _persist_outbound(
    to_phone: str,
    payload: dict,
    *,
    template_name: Optional[str],
    category: str,
    patient_id: Optional[str],
    doctor_id: Optional[str],
    idempotency_key: str,
    wamid: Optional[str],
    status: str,
    error: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid.uuid4()),
        "direction": "outbound",
        "whatsapp_message_id": wamid,
        "phone_number": to_phone,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "template_name": template_name,
        "category": category,  # auth | utility | marketing | session
        "payload": payload,
        "status": status,      # stubbed | sent | failed
        "error": error,
        "status_history": [{"status": status, "timestamp": now.isoformat(), "source": "client"}],
        "idempotency_key": idempotency_key,
        "created_at": now.isoformat(),
    }
    await db.whatsapp_messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def send_template(
    to_phone: str,
    template_name: str,
    *,
    language_code: str = "en_US",
    body_params: Optional[list[str]] = None,
    button_url_params: Optional[list[str]] = None,
    category: str = "utility",
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Send a pre-approved template message.

    body_params: positional substitutions for {{1}}, {{2}}, … in the template body.
    button_url_params: substitutions for URL-button suffixes (if template has them).
    """
    idempotency_key = idempotency_key or f"tpl:{template_name}:{to_phone}:{uuid.uuid4()}"
    if (existing := await _check_idempotency(idempotency_key)):
        return existing

    components: list[dict] = []
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_params],
        })
    if button_url_params:
        for i, p in enumerate(button_url_params):
            components.append({
                "type": "button", "sub_type": "url", "index": str(i),
                "parameters": [{"type": "text", "text": str(p)}],
            })

    payload = {
        "messaging_product": "whatsapp",
        "to": _to_e164_digits(to_phone),
        "type": "template",
        "template": {"name": template_name, "language": {"code": language_code}},
    }
    if components:
        payload["template"]["components"] = components

    if not WHATSAPP_ENABLED:
        log.info("[WA stub] template %s → %s | params=%s", template_name, to_phone, body_params)
        return await _persist_outbound(
            to_phone, payload, template_name=template_name, category=category,
            patient_id=patient_id, doctor_id=doctor_id, idempotency_key=idempotency_key,
            wamid=None, status="stubbed",
        )

    try:
        resp = await _post_to_meta(payload)
        wamid = (resp.get("messages") or [{}])[0].get("id")
        return await _persist_outbound(
            to_phone, payload, template_name=template_name, category=category,
            patient_id=patient_id, doctor_id=doctor_id, idempotency_key=idempotency_key,
            wamid=wamid, status="sent",
        )
    except Exception as e:
        log.exception("WhatsApp template send failed: %s", template_name)
        return await _persist_outbound(
            to_phone, payload, template_name=template_name, category=category,
            patient_id=patient_id, doctor_id=doctor_id, idempotency_key=idempotency_key,
            wamid=None, status="failed", error=str(e),
        )


async def send_text(
    to_phone: str,
    body: str,
    *,
    preview_url: bool = False,
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Send a free-form text — only valid within the 24h customer-care window."""
    idempotency_key = idempotency_key or f"txt:{to_phone}:{uuid.uuid4()}"
    if (existing := await _check_idempotency(idempotency_key)):
        return existing

    payload = {
        "messaging_product": "whatsapp",
        "to": _to_e164_digits(to_phone),
        "type": "text",
        "text": {"body": body, "preview_url": preview_url},
    }

    if not WHATSAPP_ENABLED:
        log.info("[WA stub] text → %s | %s", to_phone, body[:80])
        return await _persist_outbound(
            to_phone, payload, template_name=None, category="session",
            patient_id=patient_id, doctor_id=doctor_id, idempotency_key=idempotency_key,
            wamid=None, status="stubbed",
        )

    try:
        resp = await _post_to_meta(payload)
        wamid = (resp.get("messages") or [{}])[0].get("id")
        return await _persist_outbound(
            to_phone, payload, template_name=None, category="session",
            patient_id=patient_id, doctor_id=doctor_id, idempotency_key=idempotency_key,
            wamid=wamid, status="sent",
        )
    except Exception as e:
        log.exception("WhatsApp text send failed")
        return await _persist_outbound(
            to_phone, payload, template_name=None, category="session",
            patient_id=patient_id, doctor_id=doctor_id, idempotency_key=idempotency_key,
            wamid=None, status="failed", error=str(e),
        )


# ---------- DocNow-NG specific helpers ----------
# Templates that must exist in Meta Business Manager before WHATSAPP_ENABLED=true:
#   • docnow_otp_login           (auth)        {{1}} = 6-digit code, {{2}} = minutes
#   • docnow_appointment_confirm (utility)     {{1}} = patient name, {{2}} = doctor, {{3}} = date, {{4}} = time
#   • docnow_appointment_remind  (utility)     {{1}} = patient name, {{2}} = doctor, {{3}} = time
#   • docnow_careplan_summary    (utility)     {{1}} = patient, {{2}} = doctor, {{3}} = summary, {{4}} = rx code
#   • docnow_questionnaire_link  (utility)     {{1}} = patient name, {{2}} = URL slug
#   • docnow_health_tip_weekly   (marketing)   {{1}} = patient name, {{2}} = tip body

async def send_otp_via_whatsapp(phone: str, code: str, ttl_minutes: int = 10, patient_id: Optional[str] = None) -> dict:
    return await send_template(
        phone, "docnow_otp_login",
        language_code="en", category="auth",
        body_params=[code, str(ttl_minutes)],
        patient_id=patient_id,
        idempotency_key=f"otp:{phone}:{code}",
    )


async def send_appointment_confirmation(
    phone: str, patient_name: str, doctor_name: str, when_iso: str, appointment_id: str,
    patient_id: Optional[str] = None, doctor_id: Optional[str] = None,
) -> dict:
    dt = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
    return await send_template(
        phone, "docnow_appointment_confirm",
        body_params=[patient_name, doctor_name, dt.strftime("%a %d %b %Y"), dt.strftime("%I:%M %p")],
        patient_id=patient_id, doctor_id=doctor_id,
        idempotency_key=f"appt-confirm:{appointment_id}",
    )


async def send_appointment_reminder(
    phone: str, patient_name: str, doctor_name: str, when_iso: str, appointment_id: str,
    patient_id: Optional[str] = None, doctor_id: Optional[str] = None,
) -> dict:
    dt = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
    return await send_template(
        phone, "docnow_appointment_remind",
        body_params=[patient_name, doctor_name, dt.strftime("%I:%M %p")],
        patient_id=patient_id, doctor_id=doctor_id,
        idempotency_key=f"appt-remind:{appointment_id}",
    )


async def send_care_plan_summary(
    phone: str, patient_name: str, doctor_name: str, summary: str, rx_code: str, consultation_id: str,
    patient_id: Optional[str] = None, doctor_id: Optional[str] = None,
) -> dict:
    # Keep summary tight — WA template bodies have ~1024 char limits.
    short = (summary or "").strip().replace("\n", " ")
    if len(short) > 400:
        short = short[:397] + "…"
    return await send_template(
        phone, "docnow_careplan_summary",
        body_params=[patient_name, doctor_name, short, rx_code or "—"],
        patient_id=patient_id, doctor_id=doctor_id,
        idempotency_key=f"careplan:{consultation_id}",
    )


async def send_questionnaire_link(
    phone: str, patient_name: str, url_slug: str, code: str, patient_id: str,
) -> dict:
    return await send_template(
        phone, "docnow_questionnaire_link",
        body_params=[patient_name, url_slug],
        patient_id=patient_id,
        idempotency_key=f"qx:{code}:{patient_id}",
    )


async def send_health_tip(phone: str, patient_name: str, tip_body: str, patient_id: str, tip_id: str) -> dict:
    return await send_template(
        phone, "docnow_health_tip_weekly",
        category="marketing",
        body_params=[patient_name, tip_body],
        patient_id=patient_id,
        idempotency_key=f"tip:{tip_id}:{patient_id}",
    )
