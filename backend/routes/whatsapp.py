"""WhatsApp Cloud API webhook + admin routes for DocNow.NG.

Endpoints:
  GET  /api/whatsapp/webhook   → Meta verification handshake (hub.challenge)
  POST /api/whatsapp/webhook   → Inbound messages + status events (HMAC-SHA256 verified)
  GET  /api/whatsapp/conversations/{patient_id}     → Conversation history for doctor UI
  POST /api/whatsapp/conversations/{patient_id}/send → Doctor replies via WA
  GET  /api/whatsapp/status                         → Admin: integration health
"""
import os
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from db import db
from auth_utils import get_current_user, require_role
import whatsapp_service as wa
from whatsapp_scheduler import send_weekly_tips

log = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")


# ---------- HMAC signature verification ----------
def _verify_meta_signature(raw_body: bytes, sig_header: str) -> bool:
    """Verify Meta's x-hub-signature-256 using app_secret (HMAC-SHA256)."""
    if not sig_header or not APP_SECRET:
        return False
    try:
        scheme, received = sig_header.split("=", 1)
    except ValueError:
        return False
    if scheme != "sha256":
        return False
    expected = hmac.new(APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


# ---------- GET — Meta verification handshake ----------
@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token and token == VERIFY_TOKEN and challenge:
        log.info("WhatsApp webhook verified")
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


# ---------- POST — inbound messages + status events ----------
@router.post("/webhook")
async def receive_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256", "")

    # When live (APP_SECRET set), enforce signature. When in dev (no secret), skip verification.
    if APP_SECRET and not _verify_meta_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid WhatsApp signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if payload.get("object") != "whatsapp_business_account":
        return JSONResponse({"ignored": True})

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {}) or {}
            await _handle_inbound(value.get("messages", []) or [], value.get("contacts", []) or [])
            await _handle_statuses(value.get("statuses", []) or [])

    return JSONResponse({"success": True})


async def _handle_inbound(messages: list[dict], contacts: list[dict]) -> None:
    """Store inbound patient messages and link them to a patient + open consultation if any."""
    name_by_wa = {
        c.get("wa_id"): (c.get("profile") or {}).get("name")
        for c in contacts if c.get("wa_id")
    }

    for m in messages:
        from_wa = m.get("from")  # digits-only E.164
        msg_id = m.get("id")
        msg_type = m.get("type")
        ts = m.get("timestamp")
        text_body = None
        if msg_type == "text":
            text_body = (m.get("text") or {}).get("body")
        elif msg_type == "interactive":
            interactive = m.get("interactive") or {}
            text_body = (
                (interactive.get("button_reply") or {}).get("title")
                or (interactive.get("list_reply") or {}).get("title")
                or "[interactive reply]"
            )
        elif msg_type in {"image", "audio", "video", "document"}:
            text_body = f"[{msg_type} attachment]"

        # Try to link the WhatsApp number to an existing patient
        phone_with_plus = f"+{from_wa}" if from_wa and not from_wa.startswith("+") else from_wa
        patient = await db.users.find_one(
            {"phone": {"$in": [phone_with_plus, from_wa]}, "role": "patient"},
            {"id": 1, "full_name": 1}
        )

        doc = {
            "id": __import__("uuid").uuid4().hex,
            "direction": "inbound",
            "whatsapp_message_id": msg_id,
            "phone_number": from_wa,
            "sender_name": name_by_wa.get(from_wa),
            "patient_id": (patient or {}).get("id"),
            "type": msg_type,
            "body": text_body,
            "raw": m,
            "status": "received",
            "wa_timestamp": int(ts) if ts else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.whatsapp_messages.insert_one(doc)

        # Opt-out handling — patient texts "STOP" → mark them opted out of marketing
        if text_body and text_body.strip().lower() in {"stop", "stop tips", "unsubscribe"}:
            if patient:
                await db.users.update_one(
                    {"id": patient["id"]},
                    {"$set": {"whatsapp_marketing_opt_in": False,
                              "whatsapp_marketing_opted_out_at": doc["created_at"]}},
                )
                log.info("Patient %s opted out of WA marketing", patient["id"])


async def _handle_statuses(statuses: list[dict]) -> None:
    """Update existing outbound message rows with delivery/read/failed status."""
    for s in statuses:
        wamid = s.get("id")
        status = s.get("status")
        ts = s.get("timestamp")
        if not wamid or not status:
            continue
        event = {
            "status": status,
            "timestamp": (
                datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                if ts else datetime.now(timezone.utc).isoformat()
            ),
            "source": "webhook",
            "errors": s.get("errors", []),
        }
        await db.whatsapp_messages.update_one(
            {"whatsapp_message_id": wamid},
            {"$set": {"status": status}, "$push": {"status_history": event}},
        )


# ---------- Doctor-facing: read & reply to patient WA conversation ----------
@router.get("/conversations/{patient_id}")
async def get_conversation(patient_id: str, user: dict = Depends(get_current_user)):
    """Return WhatsApp message history for a patient (doctor or admin only)."""
    if user["role"] not in {"doctor", "admin"}:
        raise HTTPException(403, "Forbidden")
    items = await (
        db.whatsapp_messages
        .find({"patient_id": patient_id})
        .sort("created_at", 1)
        .to_list(500)
    )
    for it in items:
        it.pop("_id", None)
        it.pop("raw", None)  # don't expose raw Meta payloads to UI
    return {"messages": items}


class SendTextBody(BaseModel):
    body: str


class BroadcastTipBody(BaseModel):
    custom_tip: Optional[str] = None  # if None, AI generates the tip pool


@router.post("/broadcast/health-tip")
async def trigger_health_tip_broadcast(
    payload: BroadcastTipBody,
    user: dict = Depends(require_role("admin")),
):
    """Admin: manually fire the weekly health-tip broadcast right now."""
    result = await send_weekly_tips(custom_tip=payload.custom_tip)
    return result


@router.get("/broadcasts")
async def list_broadcasts(user: dict = Depends(require_role("admin"))):
    items = await db.whatsapp_broadcasts.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"items": items}


@router.post("/conversations/{patient_id}/send")
async def send_doctor_reply(
    patient_id: str, body: SendTextBody, user: dict = Depends(get_current_user),
):
    """Doctor sends a free-form WA reply during the 24h care window."""
    if user["role"] not in {"doctor", "admin"}:
        raise HTTPException(403, "Forbidden")
    patient = await db.users.find_one({"id": patient_id, "role": "patient"}, {"phone": 1, "id": 1})
    if not patient or not patient.get("phone"):
        raise HTTPException(404, "Patient or phone not found")
    result = await wa.send_text(
        patient["phone"], body.body,
        patient_id=patient_id, doctor_id=user["id"],
    )
    return result


# ---------- Admin: integration health ----------
@router.get("/status")
async def whatsapp_status(user: dict = Depends(require_role("admin"))):
    enabled = os.environ.get("WHATSAPP_ENABLED", "false").lower() == "true"
    has_creds = all([
        os.environ.get("WHATSAPP_PHONE_NUMBER_ID"),
        os.environ.get("WHATSAPP_ACCESS_TOKEN"),
        os.environ.get("WHATSAPP_APP_SECRET"),
        os.environ.get("WHATSAPP_VERIFY_TOKEN"),
    ])
    counts = await db.whatsapp_messages.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}}}
    ]).to_list(20)
    return {
        "enabled": enabled,
        "mode": "live" if enabled and has_creds else "stub",
        "has_credentials": has_creds,
        "message_counts_by_status": {c["_id"]: c["n"] for c in counts},
    }
