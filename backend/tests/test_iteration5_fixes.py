"""Targeted regression for iteration-5 fixes:
1) Multiple OTP patient registrations (no users.email null collision).
2) /profile/me lazily recomputes derived_signals for fresh OTP patient.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://patient-first-26.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _new_phone() -> str:
    return f"+23470{uuid.uuid4().int % 100000000:08d}"


def _register_otp_patient():
    sess = requests.Session()
    phone = _new_phone()
    r = sess.post(f"{API}/auth/otp/send", json={"phone": phone})
    assert r.status_code == 200, r.text
    code = r.json()["dev_otp"]
    rv = sess.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code})
    assert rv.status_code == 200, rv.text
    reg = rv.json()["registration_token"]
    payload = {
        "phone": phone,
        "full_name": f"TEST_OTP_{uuid.uuid4().hex[:6]}",
        "dob": "1990-05-20",
        "gender": "Female",
        "state": "Lagos",
        "language": "English",
        "consents": {"care_delivery": True, "analytics": False,
                     "model_training": False, "research": False},
    }
    rr = sess.post(f"{API}/auth/register/patient", json=payload,
                   headers={"X-Registration-Token": reg})
    return sess, rr, payload


# ---------- FIX #1: multiple registrations succeed ----------
def test_register_three_otp_patients_in_a_row():
    results = []
    for _ in range(3):
        _, rr, payload = _register_otp_patient()
        assert rr.status_code == 200, f"Registration failed: {rr.status_code} {rr.text}"
        data = rr.json()
        # access_token + user object present
        assert data.get("access_token"), "missing access_token"
        user = data["user"]
        assert user["role"] == "patient"
        assert user["phone"] == payload["phone"]
        # 'email' must NOT be present (not even null)
        assert "email" not in user, f"Unexpected email field in response: {user.get('email')!r}"
        # _id must not leak
        assert "_id" not in user
        results.append(user["id"])
    # all 3 unique
    assert len(set(results)) == 3


# ---------- FIX #2: /profile/me lazy recompute ----------
def test_profile_me_signals_non_null_for_fresh_otp_patient():
    sess, rr, _ = _register_otp_patient()
    assert rr.status_code == 200, rr.text
    token = rr.json()["access_token"]
    sess.headers.update({"Authorization": f"Bearer {token}"})

    r = sess.get(f"{API}/profile/me")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "signals" in data
    sig = data["signals"]
    assert sig is not None, "signals should be lazily recomputed, got None"
    for k in ("risk_score", "triage_priority", "care_segment", "next_best_actions"):
        assert k in sig, f"signal missing key {k}: {sig}"
    # next_best_actions must be a list
    assert isinstance(sig["next_best_actions"], list)
