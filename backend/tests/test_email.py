"""Tests for the email integration (DocNow.NG / Resend).

Covers:
  • email_service — stub mode reported, stub send persists to `emails`, idempotency
    (same key → no duplicate), template helpers (subject + persistence), HTML wrapper.

Stub-mode sends use motor's real Mongo from .env (same pattern as test_whatsapp.py).
Run with:
    cd /app/backend && python -m pytest tests/test_email.py -v
"""
import os
import uuid
import importlib

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
os.environ.setdefault("EMAIL_ENABLED", "false")  # stub mode — no network
os.environ.setdefault("EMERGENT_LLM_KEY", "stub-not-used-in-these-tests")

_sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def es():
    import email_service
    importlib.reload(email_service)
    return email_service


@pytest.fixture(autouse=True)
def _clean_test_emails():
    _sync_db.emails.delete_many({"to": {"$regex": "@unit.test$"}})
    yield
    _sync_db.emails.delete_many({"to": {"$regex": "@unit.test$"}})


def test_stub_mode_reported(es):
    assert es.is_live() is False
    assert es.provider_name() == "resend_stub"


def test_wrap_contains_title_and_brand(es):
    html = es._wrap("My Title", "<p>hello</p>")
    assert "My Title" in html
    assert "DocNow.NG" in html
    assert "<p>hello</p>" in html


@pytest.mark.asyncio
async def test_stub_send_persists(es):
    to = f"a-{uuid.uuid4().hex[:6]}@unit.test"
    out = await es.send_email(to, "Hello", "<p>hi</p>")
    assert out["status"] == "stubbed"
    assert out["provider"] == "resend_stub"
    assert _sync_db.emails.count_documents({"to": to, "status": "stubbed"}) == 1


@pytest.mark.asyncio
async def test_idempotency_no_duplicate(es):
    to = f"b-{uuid.uuid4().hex[:6]}@unit.test"
    key = f"unit-key-{uuid.uuid4().hex[:8]}"
    first = await es.send_email(to, "One", "<p>1</p>", idempotency_key=key)
    second = await es.send_email(to, "One", "<p>1</p>", idempotency_key=key)
    assert first["id"] == second["id"]
    assert _sync_db.emails.count_documents({"idempotency_key": key}) == 1


@pytest.mark.asyncio
async def test_password_reset_helper(es):
    to = f"c-{uuid.uuid4().hex[:6]}@unit.test"
    out = await es.send_password_reset(to, "https://app.docnow.ng/reset-password?token=abc", "Chioma")
    assert out["subject"] == "Reset your DocNow.NG password"
    assert out["category"] == "transactional"
    row = _sync_db.emails.find_one({"to": to})
    assert row is not None


@pytest.mark.asyncio
async def test_consultation_complete_helper_idempotent(es):
    to = f"d-{uuid.uuid4().hex[:6]}@unit.test"
    cid = uuid.uuid4().hex
    a = await es.send_consultation_complete(
        to, patient_name="Chioma", doctor_name="Adaeze", summary="Rest & fluids",
        rx_code="RX-ABC123", view_url="https://app.docnow.ng/patient", consultation_id=cid)
    b = await es.send_consultation_complete(
        to, patient_name="Chioma", doctor_name="Adaeze", summary="Rest & fluids",
        rx_code="RX-ABC123", view_url="https://app.docnow.ng/patient", consultation_id=cid)
    assert a["id"] == b["id"]  # same consultation → deduped
    assert _sync_db.emails.count_documents({"idempotency_key": f"careplan-email:{cid}"}) == 1
