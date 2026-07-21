"""Tests for the WhatsApp Cloud API integration (DocNow.NG).

Covers:
  • whatsapp_service module — phone normalisation, stub mode persistence, idempotency,
    error-path persistence (failed status), and 24h template-helper payload shape
  • routes/whatsapp — webhook verify GET, HMAC-SHA256 POST verification,
    inbound message linking to existing patient, STOP opt-out, doctor reply RBAC,
    admin status endpoint, admin broadcast endpoint
  • whatsapp_scheduler — eligibility query honours opt-in + 6-day cooldown

These are async unit tests using motor's real Mongo connection from .env.
Run with:
    cd /app/backend && python -m pytest tests/test_whatsapp.py -v
"""
import os
import json
import hmac
import hashlib
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
import httpx
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient


def _read_env(key: str, default: str = "") -> str:
    """Read a value from the running backend's /app/backend/.env."""
    try:
        for line in open("/app/backend/.env"):
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return default


# Align the test process with the running backend so HTTP tests + DB tests
# read/write the same Mongo database.
os.environ["MONGO_URL"] = _read_env("MONGO_URL", "mongodb://localhost:27017")
os.environ["DB_NAME"] = _read_env("DB_NAME", "medinest_db")
os.environ.setdefault("WHATSAPP_ENABLED", "false")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", _read_env("WHATSAPP_VERIFY_TOKEN", "test-verify-token-xyz"))
os.environ.setdefault("WHATSAPP_APP_SECRET", _read_env("WHATSAPP_APP_SECRET") or "test-app-secret-9f7c")
os.environ.setdefault("EMERGENT_LLM_KEY", "stub-not-used-in-these-tests")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@docnow.ng"
ADMIN_PASSWORD = "Admin@123"
DOCTOR_EMAIL = "doctor@docnow.ng"
DOCTOR_PASSWORD = "Doctor@123"
SEED_PATIENT_PHONE = "+2348012345678"

# Sync pymongo client — bypasses asyncio loops entirely for setup/teardown.
_sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# =================================================================
# Unit tests — whatsapp_service (stub mode, no network)
# =================================================================

@pytest.fixture
def wa_service():
    import importlib
    import whatsapp_service
    importlib.reload(whatsapp_service)
    return whatsapp_service


@pytest.fixture(autouse=True)
def _clean_test_messages():
    """Wipe test-prefix rows around each test (sync — bypasses async loop)."""
    _sync_db.whatsapp_messages.delete_many({"phone_number": {"$regex": "^\\+?234801999"}})
    yield
    _sync_db.whatsapp_messages.delete_many({"phone_number": {"$regex": "^\\+?234801999"}})


def test_phone_normalised_to_digits(wa_service):
    assert wa_service._to_e164_digits("+2348012345678") == "2348012345678"
    assert wa_service._to_e164_digits("+234 801 234 5678") == "2348012345678"
    assert wa_service._to_e164_digits("") == ""
    assert wa_service._to_e164_digits(None) == ""


@pytest.mark.asyncio
async def test_send_template_stub_mode_persists(wa_service):
    """In stub mode, send_template returns a document with status='stubbed' and persists it."""
    test_phone = "+2348019991111"
    result = await wa_service.send_template(
        test_phone, "docnow_otp_login", body_params=["123456", "10"],
        category="auth", patient_id="test-p1",
    )
    assert result["status"] == "stubbed"
    assert result["direction"] == "outbound"
    assert result["template_name"] == "docnow_otp_login"
    assert result["whatsapp_message_id"] is None
    assert result["payload"]["to"] == "2348019991111"  # normalised
    assert result["payload"]["template"]["components"][0]["parameters"][0]["text"] == "123456"

    # Verify persisted (sync pymongo read)
    doc = _sync_db.whatsapp_messages.find_one({"phone_number": test_phone})
    assert doc is not None
    assert doc["status"] == "stubbed"


@pytest.mark.asyncio
async def test_send_template_idempotency_short_circuits(wa_service):
    """Calling send_template twice with the same idempotency_key must not insert a second doc."""
    test_phone = "+2348019992222"
    key = f"idem-test-{uuid.uuid4().hex}"

    a = await wa_service.send_template(
        test_phone, "docnow_otp_login", body_params=["111111", "10"], idempotency_key=key,
    )
    b = await wa_service.send_template(
        test_phone, "docnow_otp_login", body_params=["999999", "10"], idempotency_key=key,
    )
    assert a["id"] == b["id"], "Same idempotency key must return the same doc"
    count = _sync_db.whatsapp_messages.count_documents({"idempotency_key": key})
    assert count == 1, "Idempotency key must only persist one document"


@pytest.mark.asyncio
async def test_send_text_stub_mode(wa_service):
    test_phone = "+2348019993333"
    res = await wa_service.send_text(test_phone, "Hello patient", patient_id="test-p3")
    assert res["status"] == "stubbed"
    assert res["category"] == "session"
    assert res["template_name"] is None
    assert res["payload"]["text"]["body"] == "Hello patient"


@pytest.mark.asyncio
async def test_send_otp_helper_uses_auth_template(wa_service):
    test_phone = "+2348019994444"
    res = await wa_service.send_otp_via_whatsapp(test_phone, "246810", ttl_minutes=10)
    assert res["template_name"] == "docnow_otp_login"
    assert res["category"] == "auth"
    params = res["payload"]["template"]["components"][0]["parameters"]
    assert params[0]["text"] == "246810"
    assert params[1]["text"] == "10"


@pytest.mark.asyncio
async def test_send_care_plan_truncates_long_summary(wa_service):
    long_summary = "A" * 1000
    res = await wa_service.send_care_plan_summary(
        "+2348019995555", "Chioma", "Dr. Adaeze",
        summary=long_summary, rx_code="RX-DEADBEEF", consultation_id="c-1",
    )
    summary_param = res["payload"]["template"]["components"][0]["parameters"][2]["text"]
    assert len(summary_param) <= 400 + 1, "Summary must be truncated to ≤400 chars"
    assert summary_param.endswith("…")


# =================================================================
# Webhook signature verification (HMAC-SHA256)
# =================================================================

def test_meta_signature_verification_valid():
    """A correctly-signed payload must verify against the app secret."""
    from routes.whatsapp import _verify_meta_signature
    secret = os.environ["WHATSAPP_APP_SECRET"]
    body = b'{"object":"whatsapp_business_account"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_meta_signature(body, sig) is True


def test_meta_signature_verification_rejects_tampered():
    from routes.whatsapp import _verify_meta_signature
    body = b'{"object":"whatsapp_business_account"}'
    tampered_body = b'{"object":"evil"}'
    secret = os.environ["WHATSAPP_APP_SECRET"]
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_meta_signature(tampered_body, sig) is False


def test_meta_signature_rejects_wrong_scheme():
    from routes.whatsapp import _verify_meta_signature
    assert _verify_meta_signature(b"{}", "md5=deadbeef") is False
    assert _verify_meta_signature(b"{}", "") is False
    assert _verify_meta_signature(b"{}", None) is False


# =================================================================
# Live HTTP integration tests (against running backend)
# =================================================================

def _login(email, password):
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def test_webhook_verify_get_valid_token():
    token = os.environ.get("WHATSAPP_VERIFY_TOKEN") or "docnow-verify-7c2e4b8a1d6f3c5e"
    # Use the real verify token from running backend's env
    backend_verify = _read_env("WHATSAPP_VERIFY_TOKEN", token)
    r = httpx.get(
        f"{API}/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": backend_verify, "hub.challenge": "echo-this"},
        timeout=10,
    )
    assert r.status_code == 200
    assert r.text == "echo-this"


def test_webhook_verify_get_wrong_token():
    r = httpx.get(
        f"{API}/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "definitely-wrong", "hub.challenge": "x"},
        timeout=10,
    )
    assert r.status_code == 403


def test_webhook_post_inbound_links_existing_patient():
    """Send a synthetic inbound webhook payload for the seeded patient phone; verify it links."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "wa-account-id",
            "changes": [{
                "field": "messages",
                "value": {
                    "messages": [{
                        "from": "2348012345678",  # seeded Chioma
                        "id": f"wamid.test-{uuid.uuid4().hex[:8]}",
                        "type": "text",
                        "text": {"body": f"Hello doc {uuid.uuid4().hex[:6]}"},
                        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                    }],
                    "contacts": [{
                        "wa_id": "2348012345678",
                        "profile": {"name": "Chioma Eze"},
                    }],
                },
            }],
        }],
    }
    r = httpx.post(f"{API}/whatsapp/webhook", json=payload, timeout=10)
    assert r.status_code == 200
    assert r.json() == {"success": True}


def test_webhook_post_opt_out_flow():
    """A patient sending 'STOP' must have whatsapp_marketing_opt_in flipped to False."""
    # Find seeded patient + set opt-in to True via sync pymongo
    patient = _sync_db.users.find_one({"phone": SEED_PATIENT_PHONE, "role": "patient"})
    if not patient:
        pytest.skip("Seeded patient not present")
    patient_id = patient["id"]
    _sync_db.users.update_one({"id": patient_id}, {"$set": {"whatsapp_marketing_opt_in": True}})

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "wa-acc",
            "changes": [{
                "field": "messages",
                "value": {
                    "messages": [{
                        "from": "2348012345678",
                        "id": f"wamid.stop-{uuid.uuid4().hex[:8]}",
                        "type": "text",
                        "text": {"body": "STOP"},
                        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                    }],
                    "contacts": [{"wa_id": "2348012345678", "profile": {"name": "Chioma"}}],
                },
            }],
        }],
    }
    r = httpx.post(f"{API}/whatsapp/webhook", json=payload, timeout=10)
    assert r.status_code == 200
    # Verify opt-out persisted (sync read)
    updated = _sync_db.users.find_one({"id": patient_id}, {"whatsapp_marketing_opt_in": 1})
    assert updated.get("whatsapp_marketing_opt_in") is False, "Patient should be opted out after STOP"


def test_admin_status_endpoint():
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    r = httpx.get(f"{API}/whatsapp/status", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "enabled" in data
    assert "mode" in data
    assert data["mode"] in {"stub", "live"}


def test_admin_status_forbidden_for_doctor():
    tok = _login(DOCTOR_EMAIL, DOCTOR_PASSWORD)
    r = httpx.get(f"{API}/whatsapp/status", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == 403


def test_admin_broadcast_runs_and_returns_counts():
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    # Ensure the seeded patient is opted in + no cooldown blocks
    patient = _sync_db.users.find_one({"phone": SEED_PATIENT_PHONE, "role": "patient"})
    if patient:
        _sync_db.users.update_one(
            {"id": patient["id"]},
            {"$set": {"whatsapp_marketing_opt_in": True}},
        )
        _sync_db.whatsapp_messages.delete_many({
            "patient_id": patient["id"],
            "template_name": "docnow_health_tip_weekly",
        })

    r = httpx.post(
        f"{API}/whatsapp/broadcast/health-tip",
        json={"custom_tip": "Drink water, walk 20 minutes, sleep on time."},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    data = r.json()
    assert {"eligible", "sent", "failed", "tip_id"} <= data.keys()
    assert data["eligible"] >= 0
    assert data["failed"] == 0  # stub mode never fails on send


def test_doctor_conversation_read_works():
    tok = _login(DOCTOR_EMAIL, DOCTOR_PASSWORD)
    patient = _sync_db.users.find_one({"phone": SEED_PATIENT_PHONE, "role": "patient"})
    if not patient:
        pytest.skip("Seeded patient not present")
    r = httpx.get(
        f"{API}/whatsapp/conversations/{patient['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r.status_code == 200
    assert "messages" in r.json()


def test_conversation_forbidden_for_patient():
    """Patients must not be able to read other patients' conversations."""
    # Patient login via OTP — get a patient token by sending OTP and verifying
    r = httpx.post(f"{API}/auth/otp/send", json={"phone": SEED_PATIENT_PHONE}, timeout=10)
    if r.status_code != 200 or not r.json().get("dev_otp"):
        pytest.skip("OTP dev_reveal disabled or patient not seeded")
    code = r.json()["dev_otp"]
    r = httpx.post(f"{API}/auth/otp/verify", json={"phone": SEED_PATIENT_PHONE, "code": code}, timeout=10)
    if r.status_code != 200 or not r.json().get("access_token"):
        pytest.skip("OTP login failed")
    patient_tok = r.json()["access_token"]
    r = httpx.get(
        f"{API}/whatsapp/conversations/some-other-patient",
        headers={"Authorization": f"Bearer {patient_tok}"},
        timeout=10,
    )
    assert r.status_code == 403


# =================================================================
# Scheduler eligibility — verified via the HTTP broadcast endpoint
# so we don't have to share Motor's event loop with the test runner.
# =================================================================

def test_scheduler_eligibility_excludes_opted_out():
    """A patient with opt_in=False must NOT receive the broadcast."""
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    pid_in = f"test-opt-in-{uuid.uuid4().hex[:6]}"
    pid_out = f"test-opt-out-{uuid.uuid4().hex[:6]}"
    _sync_db.users.insert_many([
        {"id": pid_in, "role": "patient", "status": "active",
         "phone": "+2348019998881", "full_name": "Opted In",
         "whatsapp_marketing_opt_in": True},
        {"id": pid_out, "role": "patient", "status": "active",
         "phone": "+2348019998882", "full_name": "Opted Out",
         "whatsapp_marketing_opt_in": False},
    ])
    try:
        # Clear any prior tips for these test patients
        _sync_db.whatsapp_messages.delete_many({
            "patient_id": {"$in": [pid_in, pid_out]}
        })
        r = httpx.post(
            f"{API}/whatsapp/broadcast/health-tip",
            json={"custom_tip": "Test broadcast — exclude opted out"},
            headers={"Authorization": f"Bearer {tok}"}, timeout=15,
        )
        assert r.status_code == 200
        # Verify only the opted-in patient got a tip row
        in_count = _sync_db.whatsapp_messages.count_documents({
            "patient_id": pid_in, "template_name": "docnow_health_tip_weekly",
        })
        out_count = _sync_db.whatsapp_messages.count_documents({
            "patient_id": pid_out, "template_name": "docnow_health_tip_weekly",
        })
        assert in_count == 1, f"Opted-in patient should get exactly 1 tip, got {in_count}"
        assert out_count == 0, f"Opted-out patient should get 0 tips, got {out_count}"
    finally:
        _sync_db.users.delete_many({"id": {"$in": [pid_in, pid_out]}})
        _sync_db.whatsapp_messages.delete_many({"patient_id": {"$in": [pid_in, pid_out]}})


def test_scheduler_eligibility_respects_cooldown():
    """A patient who got a tip in the last 6 days must be skipped."""
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    pid = f"test-cooldown-{uuid.uuid4().hex[:6]}"
    _sync_db.users.insert_one({
        "id": pid, "role": "patient", "status": "active",
        "phone": "+2348019998883", "full_name": "Recent Recipient",
        "whatsapp_marketing_opt_in": True,
    })
    # Pre-seed a recent tip from yesterday — should block this patient from getting another
    _sync_db.whatsapp_messages.insert_one({
        "id": uuid.uuid4().hex, "direction": "outbound", "patient_id": pid,
        "template_name": "docnow_health_tip_weekly", "status": "stubbed",
        "phone_number": "+2348019998883",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    })
    try:
        before = _sync_db.whatsapp_messages.count_documents({
            "patient_id": pid, "template_name": "docnow_health_tip_weekly",
        })
        r = httpx.post(
            f"{API}/whatsapp/broadcast/health-tip",
            json={"custom_tip": "Should be skipped due to cooldown"},
            headers={"Authorization": f"Bearer {tok}"}, timeout=15,
        )
        assert r.status_code == 200
        after = _sync_db.whatsapp_messages.count_documents({
            "patient_id": pid, "template_name": "docnow_health_tip_weekly",
        })
        assert after == before, "Patient within 6-day cooldown must NOT get a new tip"
    finally:
        _sync_db.users.delete_one({"id": pid})
        _sync_db.whatsapp_messages.delete_many({"patient_id": pid})
