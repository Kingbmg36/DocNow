"""Tests for SMS delivery (Termii) and OTP fan-out (DocNow.NG).

Covers:
  • sms_service — stub mode, phone digit-normalisation, idempotency, OTP template.
  • otp.send_otp — dev-reveal gating, delivery fan-out doesn't block issuance
    even when both channels raise.

Run with:
    cd /app/backend && python -m pytest tests/test_sms.py -v
"""
import os
import uuid
import importlib
from unittest.mock import AsyncMock, patch

import pytest
from pymongo import MongoClient


def _read_env(key: str, default: str = "") -> str:
    try:
        for line in open("/app/backend/.env"):
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return default


os.environ["MONGO_URL"] = _read_env("MONGO_URL", "mongodb://localhost:27017")
os.environ["DB_NAME"] = _read_env("DB_NAME", "docnow_db")
os.environ.setdefault("SMS_ENABLED", "false")  # stub mode — no network
os.environ.setdefault("EMERGENT_LLM_KEY", "stub-not-used-in-these-tests")

_sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def sms():
    import sms_service
    importlib.reload(sms_service)
    return sms_service


@pytest.fixture(autouse=True)
def _clean():
    _sync_db.sms_messages.delete_many({"phone_number": {"$regex": "^\\+?234801999"}})
    _sync_db.otp_codes.delete_many({"phone": {"$regex": "^\\+?234801999"}})
    yield
    _sync_db.sms_messages.delete_many({"phone_number": {"$regex": "^\\+?234801999"}})
    _sync_db.otp_codes.delete_many({"phone": {"$regex": "^\\+?234801999"}})


def test_phone_normalised_to_digits(sms):
    assert sms._to_digits("+2348012345678") == "2348012345678"
    assert sms._to_digits("+234 801 234 5678") == "2348012345678"
    assert sms._to_digits("") == ""


def test_stub_mode_reported(sms):
    assert sms.is_live() is False
    assert sms.provider_name() == "termii_stub"


@pytest.mark.asyncio
async def test_stub_send_persists(sms):
    out = await sms.send_sms("+2348019991111", "hello")
    assert out["status"] == "stubbed"
    assert _sync_db.sms_messages.count_documents({"phone_number": "+2348019991111", "status": "stubbed"}) == 1


@pytest.mark.asyncio
async def test_idempotency_no_duplicate(sms):
    key = f"unit-{uuid.uuid4().hex[:8]}"
    a = await sms.send_sms("+2348019991111", "one", idempotency_key=key)
    b = await sms.send_sms("+2348019991111", "one", idempotency_key=key)
    assert a["id"] == b["id"]
    assert _sync_db.sms_messages.count_documents({"idempotency_key": key}) == 1


@pytest.mark.asyncio
async def test_otp_template_contains_code(sms):
    out = await sms.send_otp_via_sms("+2348019991111", "482913", ttl_minutes=10)
    assert out["category"] == "otp"
    row = _sync_db.sms_messages.find_one({"idempotency_key": "otp-sms:+2348019991111:482913"})
    assert row is not None and "482913" in row["body"]


@pytest.mark.asyncio
async def test_send_otp_fans_out_and_survives_both_channels_failing():
    """otp.send_otp must still succeed and return dev_otp even if SMS and WA both raise."""
    import otp
    importlib.reload(otp)
    os.environ["DEV_OTP_REVEAL"] = "true"

    with patch("sms_service.send_otp_via_sms", new=AsyncMock(side_effect=RuntimeError("sms down"))), \
         patch("whatsapp_service.send_otp_via_whatsapp", new=AsyncMock(side_effect=RuntimeError("wa down"))):
        result = await otp.send_otp("+2348019991111", purpose="auth")

    assert result["ok"] is True
    assert result["dev_otp"] is not None
    row = _sync_db.otp_codes.find_one({"phone": "+2348019991111"}, sort=[("created_at", -1)])
    assert row is not None and row["code"] == result["dev_otp"]


@pytest.mark.asyncio
async def test_send_otp_hides_code_when_dev_reveal_off():
    import otp
    importlib.reload(otp)
    os.environ["DEV_OTP_REVEAL"] = "false"
    try:
        with patch("sms_service.send_otp_via_sms", new=AsyncMock(return_value={})), \
             patch("whatsapp_service.send_otp_via_whatsapp", new=AsyncMock(return_value={})):
            result = await otp.send_otp("+2348019991111", purpose="auth")
        assert result["dev_otp"] is None
    finally:
        os.environ["DEV_OTP_REVEAL"] = "true"
