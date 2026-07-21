"""Backend tests for the new Nigeria-focused patient_intake questionnaire (version 2).

Covers:
  * Schema fetch (7 sections, new keys)
  * GET /questionnaires/mine (patient role) — patient_intake initially pending
  * POST /questionnaires/patient_intake/submit — persists, mirrors to user profile,
    merges past_illnesses into chronic_conditions, recomputes derived signals
  * After submit, /questionnaires/mine shows completed=true
  * RBAC — patient cannot submit doctor_onboarding
  * Regression — /profile/me, /profile/sections/mine still respond OK
"""
import os
import random
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


# ---------- Helpers ----------

def _otp_register_patient(full_name: str = "TEST_Intake Patient"):
    """Create a brand-new TEST patient via mock OTP and return (token, user_id, phone)."""
    phone = f"+23470{random.randint(10000000, 99999999)}"
    r = requests.post(f"{API}/auth/otp/send", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    code = r.json()["dev_otp"]

    r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("new_user") is True
    reg_tok = data["registration_token"]

    r = requests.post(
        f"{API}/auth/register/patient",
        headers={"X-Registration-Token": reg_tok},
        json={
            "phone": phone, "full_name": full_name, "dob": "1995-06-15",
            "gender": "Female", "state": "Lagos", "language": "English",
            "consents": {"terms": True, "privacy": True},
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    j = r.json()
    return j["access_token"], j["user"]["id"], phone


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login_doctor():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "doctor@docnow.ng", "password": "Doctor@123"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------- Schema ----------

class TestSchema:
    def test_patient_intake_schema_v2(self):
        r = requests.get(f"{API}/questionnaires/patient_intake", timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert s["version"] == 2
        assert s["role"] == "patient"
        assert len(s["sections"]) == 7
        section_keys = [sec["key"] for sec in s["sections"]]
        assert section_keys == [
            "about_you", "general_health", "immunizations", "lifestyle",
            "mental_wellness", "access_and_goals", "family_health",
        ]
        # Spot-check critical field keys
        all_keys = {f["key"] for sec in s["sections"] for f in sec["fields"]}
        for k in [
            "lga", "next_of_kin_name", "past_illnesses", "malaria_last_12mo",
            "phq2_mood", "goals", "family_conditions",
        ]:
            assert k in all_keys, f"Missing field key {k}"

    def test_doctor_onboarding_schema_present(self):
        r = requests.get(f"{API}/questionnaires/doctor_onboarding", timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert s["role"] == "doctor"


# ---------- /mine + submit + mirror ----------

class TestPatientIntakeFlow:

    def test_mine_initially_pending_then_completed_and_mirrors(self):
        token, uid, _ = _otp_register_patient()

        # initial /mine
        r = requests.get(f"{API}/questionnaires/mine", headers=_h(token), timeout=15)
        assert r.status_code == 200
        items = {i["code"]: i for i in r.json()["items"]}
        assert "patient_intake" in items
        assert items["patient_intake"]["completed"] is False
        assert items["patient_intake"]["version"] == 2

        # representative payload
        payload = {
            "responses": {
                "lga": "Surulere",
                "occupation": "Teacher",
                "marital_status": "Single",
                "next_of_kin_name": "Sister Adaeze",
                "next_of_kin_phone": "+2348011112222",
                "next_of_kin_relationship": "Sibling",
                "accessibility_needs": ["None"],
                "preferred_consult_mode": "Video",
                "overall_health": "Good",
                "bp_status": "High blood pressure",
                "past_illnesses": ["Hypertension", "Diabetes"],
                "malaria_last_12mo": "No",
                "sickness_frequency": "Rarely (0–1)",
                "bad_drug_reaction": False,
                "smoking": "Never",
                "alcohol": "Never",
                "exercise_days_per_week": 3,
                "phq2_mood": 1,
                "phq2_interest": 0,
                "gad2_anxious": 1,
                "gad2_worry": 0,
                "insurance": "HMO",
                "goals": ["Quick doctor consultations", "Chronic disease management"],
                "comms_channel": ["WhatsApp"],
                "ai_triage_ok": True,
                "family_conditions": ["Hypertension", "Diabetes"],
            }
        }
        r = requests.post(
            f"{API}/questionnaires/patient_intake/submit",
            headers=_h(token), json=payload, timeout=20,
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["code"] == "patient_intake"
        assert doc["version"] == 2
        assert doc["responses"]["lga"] == "Surulere"
        assert "Hypertension" in doc["responses"]["past_illnesses"]
        assert doc["completed_at"]

        # mine now completed
        r = requests.get(f"{API}/questionnaires/mine", headers=_h(token), timeout=15)
        assert r.status_code == 200
        items = {i["code"]: i for i in r.json()["items"]}
        assert items["patient_intake"]["completed"] is True
        assert items["patient_intake"]["completed_at"]

        # profile/me mirrors selected fields
        r = requests.get(f"{API}/profile/me", headers=_h(token), timeout=15)
        assert r.status_code == 200
        prof = r.json()
        user = prof["user"]
        assert user.get("lga") == "Surulere"
        assert user.get("next_of_kin_name") == "Sister Adaeze"
        assert user.get("occupation") == "Teacher"
        assert user.get("smoking") == "Never"
        assert "Quick doctor consultations" in (user.get("goals") or [])
        # chronic_conditions should include both Hypertension + Diabetes
        chronic = user.get("chronic_conditions") or []
        assert "Hypertension" in chronic
        assert "Diabetes" in chronic
        # derived signals via /profile/me — care_segment should include diabetic + hypertensive
        signals = prof.get("signals") or {}
        seg = ",".join(signals.get("care_segment") or []) if isinstance(signals.get("care_segment"), list) else str(signals.get("care_segment") or "")
        assert "diabetic" in seg.lower(), f"care_segment missing diabetic: {signals}"
        assert "hypertensive" in seg.lower(), f"care_segment missing hypertensive: {signals}"
        # risk_score recomputed (>0 since two chronics)
        rs = signals.get("risk_score")
        assert rs is not None
        assert float(rs) > 0


# ---------- RBAC ----------

class TestRBAC:
    def test_patient_cannot_submit_doctor_onboarding(self):
        token, _, _ = _otp_register_patient()
        r = requests.post(
            f"{API}/questionnaires/doctor_onboarding/submit",
            headers=_h(token),
            json={"responses": {"attest_scope": True, "attest_telemedicine": True,
                                 "attest_conduct": True, "attest_verification": True}},
            timeout=15,
        )
        assert r.status_code == 403

    def test_doctor_onboarding_required_attestations(self):
        tok = _login_doctor()
        r = requests.post(
            f"{API}/questionnaires/doctor_onboarding/submit",
            headers=_h(tok),
            json={"responses": {"attest_scope": True, "attest_telemedicine": False,
                                 "attest_conduct": True, "attest_verification": True}},
            timeout=15,
        )
        assert r.status_code == 400


# ---------- Regression ----------

class TestRegression:
    def test_profile_me_works(self):
        token, _, _ = _otp_register_patient()
        r = requests.get(f"{API}/profile/me", headers=_h(token), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "user" in body and "completion" in body

    def test_profile_sections_mine_works(self):
        token, _, _ = _otp_register_patient()
        r = requests.get(f"{API}/profile/sections/mine", headers=_h(token), timeout=15)
        assert r.status_code == 200
        # Just verify endpoint reachable (shape can vary by implementation)
        assert isinstance(r.json(), (dict, list))
