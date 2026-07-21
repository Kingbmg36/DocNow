"""Paystack payments for DocNow.NG.

Live/stub dual-mode via `paystack_service` (see PAYSTACK_ENABLED + PAYSTACK_SECRET_KEY):
  - initialize → creates a transaction and returns a checkout `authorization_url`.
  - verify     → confirms with Paystack (client-initiated, on redirect return).
  - webhook    → Paystack -> us, HMAC-SHA512 verified; the AUTHORITATIVE fulfilment
                 path (never trust the client alone). Both verify and webhook funnel
                 through `_fulfil_payment`, which is idempotent.

Money is stored in naira (float); conversion to/from kobo happens only at the
Paystack boundary. `_fulfil_payment` re-checks the paid amount against the expected
amount to reject tampering (a client paying less than the case fee).
"""
import os
import uuid
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from db import db
from models import InitPaymentIn, VerifyPaymentIn
from auth_utils import require_role, log_audit
import paystack_service as ps

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

PLATFORM_SHARE = 0.30
DOCTOR_SHARE = 0.70

FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
CALLBACK_URL = os.environ.get("PAYSTACK_CALLBACK_URL") or (f"{FRONTEND_URL}/patient" if FRONTEND_URL else None)


def _paystack_email(user: dict) -> str:
    """Paystack requires an email. OTP-only patients may not have one — synthesise a
    stable, deliverable-shaped address so checkout still works."""
    return user.get("email") or f"patient+{user['id']}@docnow.ng"


@router.post("/initialize")
async def initialize_payment(payload: InitPaymentIn, user: dict = Depends(require_role("patient"))):
    case = await db.health_cases.find_one({"id": payload.case_id})
    if not case or case["patient_id"] != user["id"]:
        raise HTTPException(404, "Case not found")

    reference = f"DN-{uuid.uuid4().hex[:14].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    metadata = {"case_id": payload.case_id, "patient_id": user["id"], "reference": reference}

    try:
        init = await ps.initialize_transaction(
            email=_paystack_email(user),
            amount_major=payload.amount,
            reference=reference,
            currency=payload.currency,
            callback_url=CALLBACK_URL,
            metadata=metadata,
        )
    except Exception as e:
        log.exception("Paystack initialize failed for case %s", payload.case_id)
        raise HTTPException(502, f"Payment provider error: {e}")

    doc = {
        "id": str(uuid.uuid4()),
        "reference": reference,
        "case_id": payload.case_id,
        "patient_id": user["id"],
        "email": _paystack_email(user),
        "amount": payload.amount,
        "currency": payload.currency,
        "status": "pending",  # pending | success | failed
        "provider": ps.provider_name(),
        "provider_reference": init.get("reference", reference),
        "authorization_url": init.get("authorization_url"),
        "access_code": init.get("access_code"),
        "doctor_share": round(payload.amount * DOCTOR_SHARE, 2),
        "platform_share": round(payload.amount * PLATFORM_SHARE, 2),
        "created_at": now,
        "updated_at": now,
    }
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    return {
        "reference": reference,
        "authorization_url": init.get("authorization_url"),
        "access_code": init.get("access_code"),
        "amount": payload.amount,
        "currency": payload.currency,
        "live": init.get("live", False),
        "payment": doc,
    }


async def _fulfil_payment(reference: str, *, source: str, paid_amount_major: float | None = None) -> dict:
    """Idempotently mark a payment successful and advance its case.

    `source` is 'verify' or 'webhook' (audit trail). `paid_amount_major`, when known,
    is checked against the expected amount to reject underpayment/tampering.
    Returns {"status": "success", "already": bool}.
    """
    pay = await db.payments.find_one({"reference": reference})
    if not pay:
        raise HTTPException(404, "Payment not found")

    # Amount tampering guard — compare in integer kobo to avoid float wobble.
    if paid_amount_major is not None:
        expected = ps.to_subunit(pay["amount"])
        got = ps.to_subunit(paid_amount_major)
        if got < expected:
            await db.payments.update_one(
                {"reference": reference},
                {"$set": {"status": "failed", "failure_reason": "amount_mismatch",
                          "paid_amount": paid_amount_major,
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            log.warning("Payment %s amount mismatch: expected %s, got %s", reference, expected, got)
            raise HTTPException(400, "Paid amount does not match the expected fee")

    now = datetime.now(timezone.utc).isoformat()
    # Atomic flip: only the first caller (verify OR webhook) transitions the case.
    res = await db.payments.update_one(
        {"reference": reference, "status": {"$ne": "success"}},
        {"$set": {"status": "success", "verified_at": now, "verified_via": source, "updated_at": now}},
    )
    if res.modified_count == 0:
        return {"status": "success", "already": True}

    case = await db.health_cases.find_one({"id": pay["case_id"]})
    if case and case.get("status") == "pending_payment":
        new_status = "scheduled" if case.get("flow") == "scheduled" else "queued"
        await db.health_cases.update_one(
            {"id": pay["case_id"]},
            {"$set": {"status": new_status, "updated_at": now}},
        )
        if new_status == "scheduled" and case.get("doctor_id"):
            from notify import notify  # local import to avoid cycle
            await notify(
                case["doctor_id"],
                "appointment.booked",
                "New appointment booked",
                f"A patient booked you for {case.get('scheduled_for', '')}",
                "",
                {"case_id": pay["case_id"], "appointment_id": case.get("appointment_id")},
            )
    await log_audit(pay["patient_id"], "payment.success", reference, {"amount": pay["amount"], "source": source})
    return {"status": "success", "already": False}


@router.post("/verify")
async def verify_payment(payload: VerifyPaymentIn, user: dict = Depends(require_role("patient"))):
    pay = await db.payments.find_one({"reference": payload.reference})
    if not pay or pay["patient_id"] != user["id"]:
        raise HTTPException(404, "Payment not found")

    try:
        result = await ps.verify_transaction(payload.reference)
    except Exception as e:
        log.exception("Paystack verify failed for %s", payload.reference)
        raise HTTPException(502, f"Payment provider error: {e}")

    if result.get("status") != "success":
        raise HTTPException(402, f"Payment not completed (status: {result.get('status')})")

    await _fulfil_payment(payload.reference, source="verify", paid_amount_major=result.get("amount_major"))
    return {"status": "success", "reference": payload.reference}


@router.post("/webhook")
async def paystack_webhook(request: Request):
    """Paystack server-to-server events. Authenticated by HMAC-SHA512 signature,
    not by a user session. Always returns 200 so Paystack stops retrying."""
    raw = await request.body()
    sig = request.headers.get("x-paystack-signature", "")

    # Enforce the signature whenever a secret is configured; skip only in keyless dev.
    if ps.SECRET_KEY and not ps.verify_signature(raw, sig):
        raise HTTPException(401, "Invalid Paystack signature")

    try:
        event = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    if event.get("event") != "charge.success":
        return {"status": "ignored", "event": event.get("event")}

    data = event.get("data", {}) or {}
    reference = data.get("reference")
    if not reference:
        return {"status": "ignored", "reason": "no reference"}

    paid_major = ps.from_subunit(data.get("amount", 0)) if data.get("amount") is not None else None
    try:
        await _fulfil_payment(reference, source="webhook", paid_amount_major=paid_major)
    except HTTPException as e:
        # Acknowledge to Paystack (200) but record why we didn't fulfil.
        log.warning("Webhook fulfilment skipped for %s: %s", reference, e.detail)
        return {"status": "acknowledged", "note": e.detail}
    return {"status": "success", "reference": reference}


@router.get("/mine")
async def my_payments(user: dict = Depends(require_role("patient"))):
    items = await db.payments.find({"patient_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items
