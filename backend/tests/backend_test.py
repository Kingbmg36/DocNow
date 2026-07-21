"""End-to-end backend tests for DocNow.NG. Uses public REACT_APP_BACKEND_URL."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://patient-first-26.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@docnow.ng", "password": "Admin@123"}
DOCTOR = {"email": "doctor@docnow.ng", "password": "Doctor@123"}
DOCTOR_PENDING = {"email": "doctor.pending@docnow.ng", "password": "Doctor@123"}
PATIENT = {"email": "patient@docnow.ng", "password": "Patient@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text}"
    data = r.json()
    token = data["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s, data["user"], token


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_session():
    s, user, token = _login(ADMIN)
    return {"session": s, "user": user, "token": token}


@pytest.fixture(scope="session")
def doctor_session():
    s, user, token = _login(DOCTOR)
    return {"session": s, "user": user, "token": token}


@pytest.fixture(scope="session")
def patient_session():
    s, user, token = _login(PATIENT)
    return {"session": s, "user": user, "token": token}


# ---------- Health ----------
class TestHealth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_health(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"


# ---------- Auth ----------
class TestAuth:
    def test_login_admin(self, admin_session):
        assert admin_session["user"]["role"] == "admin"
        assert admin_session["token"]

    def test_login_doctor(self, doctor_session):
        assert doctor_session["user"]["role"] == "doctor"
        assert doctor_session["user"]["status"] == "approved"

    def test_login_patient(self, patient_session):
        assert patient_session["user"]["role"] == "patient"

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "nobody@docnow.ng", "password": "wrong"}, timeout=10)
        assert r.status_code in (401, 429)

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401

    def test_me_with_token(self, patient_session):
        r = patient_session["session"].get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == PATIENT["email"]

    def test_register_patient(self):
        email = f"test_pat_{uuid.uuid4().hex[:8]}@docnow.ng"
        payload = {
            "email": email, "password": "Test@1234", "full_name": "Test Patient",
            "role": "patient", "phone": "+2348012345678", "age": 30, "gender": "Male",
            "country": "Nigeria", "state": "Lagos",
        }
        r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["email"] == email
        assert data["user"]["role"] == "patient"
        assert "access_token" in data
        # Duplicate
        r2 = requests.post(f"{API}/auth/register", json=payload, timeout=10)
        assert r2.status_code == 400

    def test_register_doctor_pending(self):
        email = f"test_doc_{uuid.uuid4().hex[:8]}@docnow.ng"
        payload = {
            "email": email, "password": "Test@1234", "full_name": "Test Doctor",
            "role": "doctor", "phone": "+2348012345678", "specialty": "Cardiologist",
            "license_number": "MDCN-2024-X", "years_experience": 6, "consultation_fee": 7000.0,
        }
        r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["status"] == "pending"

    def test_forgot_password_always_ok(self):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": "anyone@docnow.ng"}, timeout=10)
        assert r.status_code == 200
        assert "message" in r.json()

    def test_logout(self, patient_session):
        # Don't use the session token to avoid affecting other tests
        s, _, _ = _login(PATIENT)
        r = s.post(f"{API}/auth/logout", timeout=10)
        assert r.status_code == 200


# ---------- RBAC ----------
class TestRBAC:
    def test_patient_cannot_admin(self, patient_session):
        r = patient_session["session"].get(f"{API}/admin/users", timeout=10)
        assert r.status_code == 403

    def test_doctor_cannot_patient_route(self, doctor_session):
        r = doctor_session["session"].get(f"{API}/patients/me", timeout=10)
        assert r.status_code == 403

    def test_patient_cannot_doctor_route(self, patient_session):
        r = patient_session["session"].get(f"{API}/doctors/me", timeout=10)
        assert r.status_code == 403


# ---------- Profiles ----------
class TestProfiles:
    def test_patient_me(self, patient_session):
        r = patient_session["session"].get(f"{API}/patients/me", timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == PATIENT["email"]

    def test_patient_update(self, patient_session):
        r = patient_session["session"].put(f"{API}/patients/me", json={"state": "Abuja"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["state"] == "Abuja"

    def test_doctor_me(self, doctor_session):
        r = doctor_session["session"].get(f"{API}/doctors/me", timeout=10)
        assert r.status_code == 200

    def test_doctor_list_public(self):
        r = requests.get(f"{API}/doctors", timeout=10)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert all(d["status"] == "approved" for d in items)


# ---------- Triage (AI - may take time) ----------
class TestTriage:
    def test_triage_returns_schema(self, patient_session):
        payload = {
            "symptoms": "fever and headache for 2 days, also feeling nauseous",
            "duration": "2 days", "severity": "moderate", "notes": "in Lagos",
        }
        r = patient_session["session"].post(f"{API}/triage", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("summary", "urgency", "red_flags", "recommended_specialty", "next_steps", "doctor_questions", "disclaimer"):
            assert k in data, f"Missing key {k} in triage response"
        assert data["urgency"] in ("Emergency", "High", "Moderate", "Low")


# ---------- E2E happy path ----------
class TestE2E:
    """End-to-end: patient → triage → case → pay → doctor accept → chat → notes → prescription → complete → care plan → feedback."""

    @pytest.fixture(scope="class")
    def ctx(self):
        return {}

    def test_01_patient_login(self, ctx):
        s, user, token = _login(PATIENT)
        ctx["patient_s"] = s
        ctx["patient"] = user

    def test_02_triage(self, ctx):
        r = ctx["patient_s"].post(f"{API}/triage", json={
            "symptoms": "persistent cough with chest pain", "duration": "5 days",
            "severity": "moderate", "notes": "",
        }, timeout=90)
        assert r.status_code == 200
        ctx["triage"] = r.json()
        assert ctx["triage"]["urgency"] in ("Emergency", "High", "Moderate", "Low")

    def test_03_create_case(self, ctx):
        r = ctx["patient_s"].post(f"{API}/cases", json={
            "symptoms": "persistent cough with chest pain", "duration": "5 days",
            "severity": "moderate", "notes": "", "triage": ctx["triage"],
        }, timeout=15)
        assert r.status_code == 200, r.text
        case = r.json()
        assert case["status"] == "pending_payment"
        ctx["case_id"] = case["id"]

    def test_04_init_payment(self, ctx):
        r = ctx["patient_s"].post(f"{API}/payments/initialize", json={
            "case_id": ctx["case_id"], "amount": 5000.0, "currency": "NGN",
        }, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "authorization_url" in data
        assert data["reference"].startswith("MDN-")
        ctx["ref"] = data["reference"]

    def test_05_verify_payment(self, ctx):
        r = ctx["patient_s"].post(f"{API}/payments/verify", json={"reference": ctx["ref"]}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "success"
        # Verify case moved to queued
        r2 = ctx["patient_s"].get(f"{API}/cases/{ctx['case_id']}", timeout=10)
        assert r2.json()["status"] == "queued"

    def test_06_doctor_sees_queue(self, ctx):
        s, user, _ = _login(DOCTOR)
        ctx["doctor_s"] = s
        ctx["doctor"] = user
        r = s.get(f"{API}/cases/queue", timeout=10)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert ctx["case_id"] in ids

    def test_07_doctor_accepts(self, ctx):
        r = ctx["doctor_s"].post(f"{API}/consultations/accept/{ctx['case_id']}", timeout=15)
        assert r.status_code == 200, r.text
        c = r.json()
        ctx["consultation_id"] = c["id"]
        assert c["status"] == "in_consultation"
        # Accepting again should fail (not queued anymore)
        r2 = ctx["doctor_s"].post(f"{API}/consultations/accept/{ctx['case_id']}", timeout=10)
        assert r2.status_code == 400

    def test_08_messages_both_sides(self, ctx):
        r1 = ctx["doctor_s"].post(f"{API}/consultations/{ctx['consultation_id']}/messages",
                                    json={"text": "Hello, please describe your cough"}, timeout=10)
        assert r1.status_code == 200
        r2 = ctx["patient_s"].post(f"{API}/consultations/{ctx['consultation_id']}/messages",
                                    json={"text": "Dry cough, worse at night"}, timeout=10)
        assert r2.status_code == 200
        # Fetch consultation
        r3 = ctx["doctor_s"].get(f"{API}/consultations/{ctx['consultation_id']}", timeout=10)
        assert r3.status_code == 200
        msgs = r3.json()["messages"]
        assert len(msgs) >= 2

    def test_09_notes(self, ctx):
        r = ctx["doctor_s"].put(f"{API}/consultations/{ctx['consultation_id']}/notes",
                                 json={"notes": "Likely viral bronchitis"}, timeout=10)
        assert r.status_code == 200

    def test_10_prescription(self, ctx):
        r = ctx["doctor_s"].post(f"{API}/consultations/{ctx['consultation_id']}/prescription", json={
            "items": [{"medication": "Paracetamol", "dosage": "500mg", "frequency": "TID",
                       "duration": "5 days", "instructions": "after meals"}],
            "recommended_tests": ["Chest X-ray"],
        }, timeout=10)
        assert r.status_code == 200
        ctx["prescription_id"] = r.json()["id"]

    def test_11_complete_consultation(self, ctx):
        # Snapshot doctor earnings before
        r_before = ctx["doctor_s"].get(f"{API}/doctors/me", timeout=10)
        earnings_before = r_before.json().get("earnings_total", 0)
        r = ctx["doctor_s"].post(f"{API}/consultations/{ctx['consultation_id']}/complete",
                                  json={"final_notes": "Rest and hydrate."}, timeout=120)
        assert r.status_code == 200, r.text
        cp = r.json()
        for k in ("consultation_summary", "doctor_advice", "warning_signs", "follow_up", "health_tips"):
            assert k in cp
        ctx["care_plan_id"] = cp["id"]
        # Doctor earnings credited (70% of 5000 = 3500)
        r_after = ctx["doctor_s"].get(f"{API}/doctors/me", timeout=10)
        earnings_after = r_after.json().get("earnings_total", 0)
        assert earnings_after - earnings_before == pytest.approx(3500.0, abs=0.01), (
            f"Doctor earnings not credited: before={earnings_before}, after={earnings_after}"
        )

    def test_12_patient_prescription_and_care_plan(self, ctx):
        r1 = ctx["patient_s"].get(f"{API}/prescriptions/mine", timeout=10)
        assert r1.status_code == 200
        assert any(p["id"] == ctx["prescription_id"] for p in r1.json())
        r2 = ctx["patient_s"].get(f"{API}/care-plans/mine", timeout=10)
        assert r2.status_code == 200
        assert any(p["id"] == ctx["care_plan_id"] for p in r2.json())

    def test_13_feedback_updates_rating(self, ctx):
        # Fetch doctor rating before
        doctors = requests.get(f"{API}/doctors", timeout=10).json()
        doc = next(d for d in doctors if d["id"] == ctx["doctor"]["id"])
        before_count = doc.get("rating_count", 0)
        r = ctx["patient_s"].post(f"{API}/feedback", json={
            "consultation_id": ctx["consultation_id"], "rating": 5, "comment": "Excellent",
        }, timeout=10)
        assert r.status_code == 200
        doctors2 = requests.get(f"{API}/doctors", timeout=10).json()
        doc2 = next(d for d in doctors2 if d["id"] == ctx["doctor"]["id"])
        assert doc2["rating_count"] == before_count + 1
        # Duplicate feedback should fail
        r2 = ctx["patient_s"].post(f"{API}/feedback", json={
            "consultation_id": ctx["consultation_id"], "rating": 4, "comment": "again",
        }, timeout=10)
        assert r2.status_code == 400


# ---------- Vitals ----------
class TestVitals:
    def test_add_list_delete(self, patient_session):
        s = patient_session["session"]
        r = s.post(f"{API}/vitals", json={"type": "heart_rate", "value": 72, "unit": "bpm"}, timeout=10)
        assert r.status_code == 200
        vid = r.json()["id"]
        r2 = s.get(f"{API}/vitals/mine", timeout=10)
        assert any(v["id"] == vid for v in r2.json())
        r3 = s.delete(f"{API}/vitals/{vid}", timeout=10)
        assert r3.status_code == 200


# ---------- Admin ----------
class TestAdmin:
    def test_admin_list_users(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/users", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_pending_doctors(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/doctors/pending", timeout=10)
        assert r.status_code == 200
        emails = [d["email"] for d in r.json()]
        assert DOCTOR_PENDING["email"] in emails

    def test_admin_analytics(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/analytics", timeout=10)
        assert r.status_code == 200
        data = r.json()
        for k in ("patients", "doctors", "pending_doctors", "approved_doctors",
                  "total_cases", "completed_cases", "queued_cases", "total_revenue", "platform_revenue"):
            assert k in data

    def test_admin_audit_logs(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/audit-logs", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_consultations(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/consultations", timeout=10)
        assert r.status_code == 200

    def test_admin_payments(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/payments", timeout=10)
        assert r.status_code == 200

    def test_admin_doctor_approval_flow(self, admin_session):
        # Register a fresh pending doctor
        email = f"test_pend_{uuid.uuid4().hex[:8]}@docnow.ng"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "Test@1234", "full_name": "Pend Doc",
            "role": "doctor", "specialty": "GP", "license_number": "X",
            "years_experience": 1, "consultation_fee": 3000.0,
        }, timeout=15)
        assert reg.status_code == 200
        doc_id = reg.json()["user"]["id"]
        # Approve
        r = admin_session["session"].post(f"{API}/admin/doctors/{doc_id}/decision",
                                            json={"action": "approve"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        # Suspend
        r2 = admin_session["session"].post(f"{API}/admin/doctors/{doc_id}/decision",
                                             json={"action": "suspend", "reason": "test"}, timeout=10)
        assert r2.status_code == 200
        # Suspended user cannot login
        r3 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"}, timeout=10)
        assert r3.status_code == 403, f"Suspended user should not login: {r3.status_code}"


# ---------- Health tips ----------
class TestHealthTips:
    def test_tips(self, patient_session):
        r = patient_session["session"].get(f"{API}/health-tips", timeout=90)
        assert r.status_code == 200
        data = r.json()
        assert "tips" in data and isinstance(data["tips"], list)
        assert len(data["tips"]) >= 1
        assert "disclaimer" in data
