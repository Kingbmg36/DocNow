"""OTP issuance + delivery for DocNow.NG.

Delivery fans out over SMS (Termii, primary — works for any Nigerian number,
no opt-in needed) and WhatsApp (secondary, requires the number to already be
WhatsApp-reachable and templates approved). Both are stub/live dual-mode and
independently best-effort: a delivery failure never blocks OTP issuance."""
import os
import secrets
import uuid
import logging
from datetime import datetime, timezone, timedelta
from db import db

log = logging.getLogger(__name__)

OTP_TTL_MIN = 10
OTP_LENGTH = 6


def _generate_code() -> str:
    # Cryptographically secure OTP — secrets.randbelow is the documented
    # standard for security-sensitive randomness (PEP 506, NIST SP 800-63B).
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


async def send_otp(phone: str, purpose: str = "auth") -> dict:
    """Generate + persist OTP. In dev mode, returns code for UI hint."""
    code = _generate_code()
    record = {
        "id": str(uuid.uuid4()),
        "phone": phone,
        "code": code,
        "purpose": purpose,
        "used": False,
        "attempts": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MIN)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Invalidate any pending OTP for this phone+purpose
    await db.otp_codes.update_many(
        {"phone": phone, "purpose": purpose, "used": False},
        {"$set": {"used": True}},
    )
    await db.otp_codes.insert_one(record)

    dev_mode = os.environ.get("DEV_OTP_REVEAL", "true").lower() == "true"
    # Never log the raw code outside dev — SMS/WhatsApp stub logs already show it
    # in stub mode; a live deploy with delivery misconfigured must not leak it here.
    if dev_mode:
        log.info(f"[OTP] phone={phone} code={code} (dev reveal)")

    # Deliver via SMS (primary — reaches any number) and WhatsApp (secondary).
    # Both are independently best-effort: a failure never blocks OTP issuance.
    try:
        from sms_service import send_otp_via_sms
        await send_otp_via_sms(phone, code, ttl_minutes=OTP_TTL_MIN)
    except Exception as e:
        log.warning("SMS OTP delivery failed for %s: %s", phone, e)
    try:
        from whatsapp_service import send_otp_via_whatsapp
        await send_otp_via_whatsapp(phone, code, ttl_minutes=OTP_TTL_MIN)
    except Exception as e:
        log.warning("WhatsApp OTP delivery failed for %s: %s", phone, e)

    return {
        "ok": True,
        "phone": phone,
        "expires_in": OTP_TTL_MIN * 60,
        "dev_otp": code if dev_mode else None,
    }


async def verify_otp(phone: str, code: str, purpose: str = "auth") -> bool:
    record = await db.otp_codes.find_one(
        {"phone": phone, "purpose": purpose, "used": False},
        sort=[("created_at", -1)],
    )
    if not record:
        return False
    expires_at = record["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return False
    if record.get("attempts", 0) >= 5:
        return False
    if record["code"] != code:
        await db.otp_codes.update_one({"id": record["id"]}, {"$inc": {"attempts": 1}})
        return False
    await db.otp_codes.update_one({"id": record["id"]}, {"$set": {"used": True}})
    return True
