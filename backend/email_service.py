"""Transactional email service for DocNow.NG (Resend).

Two modes (controlled by EMAIL_ENABLED + RESEND_API_KEY):
  - stub → log + persist to `emails` with status='stubbed'. Dev default; no network.
  - live → POST https://api.resend.com/emails with Bearer key, retry on 5xx.

Mirrors the stub/live + retry + idempotency + persistence shape of
`whatsapp_service.py` and `paystack_service.py`. All sends are best-effort: callers
wrap in try/except so a mail failure never blocks the core flow.
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

EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "DocNow.NG <no-reply@docnow.ng>")
BASE_URL = "https://api.resend.com"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


# ---------- Mode helpers ----------
def has_credentials() -> bool:
    return bool(RESEND_API_KEY)


def is_live() -> bool:
    return EMAIL_ENABLED and has_credentials()


def provider_name() -> str:
    return "resend" if is_live() else "resend_stub"


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
    existing = await db.emails.find_one({"idempotency_key": idempotency_key})
    if existing:
        existing.pop("_id", None)
        return existing
    return None


async def _persist(
    to_email: str, subject: str, *, category: str, status: str,
    idempotency_key: str, provider_id: Optional[str] = None, error: Optional[str] = None,
) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "to": to_email,
        "subject": subject,
        "category": category,          # transactional | notification
        "status": status,              # stubbed | sent | failed
        "provider": provider_name(),
        "provider_id": provider_id,
        "error": error,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.emails.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------- Core send ----------
async def _post_to_resend(payload: dict) -> dict:
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not configured")
    client = await _get_client()
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post("/emails", json=payload, headers=headers)
            if 500 <= resp.status_code < 600:
                last_err = RuntimeError(f"Resend {resp.status_code}: {resp.text[:200]}")
            else:
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            last_err = e
        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    assert last_err is not None
    raise last_err


async def send_email(
    to_email: str, subject: str, html: str, *,
    text: Optional[str] = None, category: str = "transactional",
    idempotency_key: Optional[str] = None,
) -> dict:
    """Send one email. Stub mode logs + persists without sending."""
    if not to_email:
        raise ValueError("to_email is required")
    idempotency_key = idempotency_key or f"mail:{category}:{to_email}:{uuid.uuid4()}"
    if (existing := await _check_idempotency(idempotency_key)):
        return existing

    if not is_live():
        log.info("[email stub] to=%s | subject=%s", to_email, subject)
        return await _persist(to_email, subject, category=category, status="stubbed",
                              idempotency_key=idempotency_key)

    payload = {"from": EMAIL_FROM, "to": [to_email], "subject": subject, "html": html}
    if text:
        payload["text"] = text
    try:
        resp = await _post_to_resend(payload)
        return await _persist(to_email, subject, category=category, status="sent",
                             idempotency_key=idempotency_key, provider_id=resp.get("id"))
    except Exception as e:
        log.exception("Email send failed: %s", subject)
        return await _persist(to_email, subject, category=category, status="failed",
                             idempotency_key=idempotency_key, error=str(e))


# ---------- Templates ----------
def _wrap(title: str, body_html: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#f4f7f9;padding:24px">
  <div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e3e9ee;border-radius:12px;overflow:hidden">
    <div style="background:#0f766e;color:#fff;padding:16px 24px;font-weight:800;font-size:18px">🏥 DocNow.NG</div>
    <div style="padding:24px;color:#1a2733;line-height:1.55">
      <h2 style="margin:0 0 12px;font-size:20px">{title}</h2>
      {body_html}
    </div>
    <div style="padding:16px 24px;color:#6b7c8c;font-size:12px;border-top:1px solid #eef2f5">
      DocNow.NG — trusted healthcare, one tap away. This is an automated message.
    </div>
  </div>
</div>"""


# ---------- DocNow-NG specific helpers ----------
async def send_password_reset(to_email: str, reset_url: str, name: str = "") -> dict:
    hello = f"Hi {name}," if name else "Hi,"
    body = f"""\
    <p>{hello}</p>
    <p>We received a request to reset your DocNow.NG password. Click below — the link expires in 1 hour.</p>
    <p style="margin:20px 0">
      <a href="{reset_url}" style="background:#0d9488;color:#fff;text-decoration:none;padding:12px 20px;border-radius:9px;font-weight:600;display:inline-block">Reset my password</a>
    </p>
    <p style="color:#6b7c8c;font-size:13px">If you didn't request this, you can safely ignore this email.</p>"""
    text = f"Reset your DocNow.NG password (expires in 1 hour): {reset_url}"
    return await send_email(
        to_email, "Reset your DocNow.NG password", _wrap("Password reset", body),
        text=text, category="transactional",
    )


async def send_consultation_complete(
    to_email: str, *, patient_name: str, doctor_name: str, summary: str,
    rx_code: str, view_url: str, consultation_id: str,
) -> dict:
    rx_line = f"<p><strong>Prescription code:</strong> <code>{rx_code}</code></p>" if rx_code and rx_code != "—" else ""
    body = f"""\
    <p>Hi {patient_name or 'there'},</p>
    <p>Dr. {doctor_name} has completed your consultation and prepared your care plan.</p>
    <p style="background:#f4f7f9;border-radius:9px;padding:12px 14px;color:#334155">{summary or 'Your care plan is ready to view.'}</p>
    {rx_line}
    <p style="margin:20px 0">
      <a href="{view_url}" style="background:#0d9488;color:#fff;text-decoration:none;padding:12px 20px;border-radius:9px;font-weight:600;display:inline-block">View my care plan</a>
    </p>"""
    text = f"Dr. {doctor_name} completed your consultation. View your care plan: {view_url}"
    return await send_email(
        to_email, "Your DocNow.NG care plan is ready", _wrap("Care plan ready", body),
        text=text, category="notification",
        idempotency_key=f"careplan-email:{consultation_id}",
    )
