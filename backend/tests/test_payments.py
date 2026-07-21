"""Tests for the Paystack payments integration (DocNow.NG).

Covers:
  • paystack_service — money conversion (naira↔kobo), HMAC-SHA512 webhook signature
    verification (valid / tampered / empty / no-secret), and stub-mode init/verify.
  • routes/payments._fulfil_payment — idempotent case advance, amount-tampering
    rejection, and the pending_payment → queued/scheduled transition.

Pure-logic tests need no network or DB. The `_fulfil_payment` tests use motor's real
Mongo connection from .env (same pattern as test_whatsapp.py).
Run with:
    cd /app/backend && python -m pytest tests/test_payments.py -v
"""
import os
import hmac
import hashlib
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


# Align with the running backend's DB, and pin a known Paystack secret so the
# signature vectors are deterministic. Set BEFORE importing paystack_service.
os.environ["MONGO_URL"] = _read_env("MONGO_URL", "mongodb://localhost:27017")
os.environ["DB_NAME"] = _read_env("DB_NAME", "docnow_db")
os.environ["JWT_SECRET"] = _read_env("JWT_SECRET", "test-jwt-secret")
os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_docnow_unit_secret"
os.environ.setdefault("PAYSTACK_ENABLED", "false")  # stub mode — no network
os.environ.setdefault("EMERGENT_LLM_KEY", "stub-not-used-in-these-tests")

TEST_SECRET = os.environ["PAYSTACK_SECRET_KEY"]

_sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def ps():
    import paystack_service
    importlib.reload(paystack_service)
    return paystack_service


# =================================================================
# Money conversion
# =================================================================
def test_to_subunit_rounds_to_kobo(ps):
    assert ps.to_subunit(5000) == 500000
    assert ps.to_subunit(5000.0) == 500000
    assert ps.to_subunit(99.99) == 9999
    assert ps.to_subunit(0.1) == 10


def test_from_subunit_roundtrip(ps):
    assert ps.from_subunit(500000) == 5000.0
    assert ps.from_subunit(9999) == 99.99
    for naira in (5000, 99.99, 1500.5, 0.1):
        assert ps.from_subunit(ps.to_subunit(naira)) == round(naira, 2)


# =================================================================
# Webhook signature (HMAC-SHA512)
# =================================================================
def _sign(body: bytes, secret: str = TEST_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()


def test_valid_signature_accepted(ps):
    body = b'{"event":"charge.success","data":{"reference":"DN-ABC123"}}'
    assert ps.verify_signature(body, _sign(body)) is True


def test_tampered_body_rejected(ps):
    body = b'{"event":"charge.success","data":{"reference":"DN-ABC123"}}'
    sig = _sign(body)
    tampered = b'{"event":"charge.success","data":{"reference":"DN-EVIL99"}}'
    assert ps.verify_signature(tampered, sig) is False


def test_wrong_secret_rejected(ps):
    body = b'{"event":"charge.success"}'
    assert ps.verify_signature(body, _sign(body, "sk_test_wrong")) is False


def test_empty_signature_rejected(ps):
    assert ps.verify_signature(b'{}', "") is False


def test_no_secret_configured_rejects(ps):
    ps.SECRET_KEY = ""  # simulate keyless dev
    body = b'{"event":"charge.success"}'
    assert ps.verify_signature(body, _sign(body)) is False


# =================================================================
# Stub mode init / verify (no network)
# =================================================================
def test_stub_mode_reported(ps):
    assert ps.is_live() is False
    assert ps.provider_name() == "paystack_stub"


@pytest.mark.asyncio
async def test_stub_initialize_returns_mock_url(ps):
    out = await ps.initialize_transaction(
        email="p@docnow.ng", amount_major=5000, reference="DN-STUB1", currency="NGN",
    )
    assert out["live"] is False
    assert out["reference"] == "DN-STUB1"
    assert "DN-STUB1" in out["authorization_url"]


@pytest.mark.asyncio
async def test_stub_verify_reports_success(ps):
    out = await ps.verify_transaction("DN-STUB1")
    assert out["status"] == "success"
    assert out["amount_major"] is None  # unknown in stub → caller skips amount check


# =================================================================
# _fulfil_payment — idempotency, amount guard, case transition (real Mongo)
# =================================================================
def _seed_case_and_payment(*, flow="urgent", amount=5000.0, status="pending_payment"):
    patient_id = f"pat-{uuid.uuid4().hex[:8]}"
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    reference = f"DN-TEST{uuid.uuid4().hex[:8].upper()}"
    _sync_db.health_cases.insert_one({
        "id": case_id, "patient_id": patient_id, "status": status, "flow": flow,
    })
    _sync_db.payments.insert_one({
        "id": str(uuid.uuid4()), "reference": reference, "case_id": case_id,
        "patient_id": patient_id, "amount": amount, "currency": "NGN", "status": "pending",
    })
    return patient_id, case_id, reference


def _cleanup(case_id, reference):
    _sync_db.health_cases.delete_many({"id": case_id})
    _sync_db.payments.delete_many({"reference": reference})
    _sync_db.audit_logs.delete_many({"target_id": reference})


@pytest.mark.asyncio
async def test_fulfil_transitions_case_and_is_idempotent():
    from routes import payments as pay_routes
    patient_id, case_id, reference = _seed_case_and_payment(flow="urgent")
    try:
        r1 = await pay_routes._fulfil_payment(reference, source="verify")
        assert r1 == {"status": "success", "already": False}
        assert _sync_db.health_cases.find_one({"id": case_id})["status"] == "queued"
        assert _sync_db.payments.find_one({"reference": reference})["status"] == "success"

        # Second call (e.g. webhook after verify) must not re-transition.
        r2 = await pay_routes._fulfil_payment(reference, source="webhook")
        assert r2 == {"status": "success", "already": True}
        # Exactly one success audit row.
        assert _sync_db.audit_logs.count_documents(
            {"target_id": reference, "action": "payment.success"}) == 1
    finally:
        _cleanup(case_id, reference)


@pytest.mark.asyncio
async def test_fulfil_scheduled_flow_transitions_to_scheduled():
    from routes import payments as pay_routes
    patient_id, case_id, reference = _seed_case_and_payment(flow="scheduled")
    try:
        await pay_routes._fulfil_payment(reference, source="webhook")
        assert _sync_db.health_cases.find_one({"id": case_id})["status"] == "scheduled"
    finally:
        _cleanup(case_id, reference)


@pytest.mark.asyncio
async def test_fulfil_rejects_underpayment():
    from fastapi import HTTPException
    from routes import payments as pay_routes
    patient_id, case_id, reference = _seed_case_and_payment(amount=5000.0)
    try:
        with pytest.raises(HTTPException) as exc:
            await pay_routes._fulfil_payment(reference, source="webhook", paid_amount_major=3000.0)
        assert exc.value.status_code == 400
        # Case must NOT advance; payment marked failed.
        assert _sync_db.health_cases.find_one({"id": case_id})["status"] == "pending_payment"
        assert _sync_db.payments.find_one({"reference": reference})["status"] == "failed"
    finally:
        _cleanup(case_id, reference)
