"""Tests for new appointment booking + notifications system.

Covers:
- GET /api/appointments/slots
- POST /api/appointments (book, mode validation, slot conflict 409)
- GET /api/appointments/mine (RBAC)
- POST /api/appointments/{id}/start (doctor only, pending doctor 403)
- POST /api/appointments/{id}/cancel
- POST /api/payments/verify with flow=scheduled (case → scheduled, doctor notified)
- POST /api/consultations/{id}/complete (completes appointment, notifies patient)
- GET /api/notifications, mark read, read-all
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://patient-first-26.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@docnow.ng", "password": "Admin@123"}
DOCTOR = {"email": "doctor@docnow.ng", "password": "Doctor@123"}
DOCTOR_PENDING = {"email": "doctor.pending@docnow.ng", "password": "Doctor@123"}
PATIENT = {"email": "patient@docnow.ng", "password": "Patient@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed {creds['email']}: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s, data["user"]


@pytest.fixture(scope="module")
def patient_ctx():
    s, u = _login(PATIENT)
    return {"s": s, "u": u}


@pytest.fixture(scope="module")
def doctor_ctx():
    s, u = _login(DOCTOR)
    return {"s": s, "u": u}


@pytest.fixture(scope="module")
def pending_doctor_ctx():
    s, u = _login(DOCTOR_PENDING)
    return {"s": s, "u": u}


# ----------------- Slots -----------------
class TestSlots:
    def test_slots_default_5(self, patient_ctx):
        r = patient_ctx["s"].get(f"{API}/appointments/slots?count=5", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "slots" in data
        slots = data["slots"]
        assert len(slots) == 5, f"Expected 5 slots, got {len(slots)}"
        for slot in slots:
            assert "scheduled_for" in slot
            assert "doctor" in slot
            d = slot["doctor"]
            for k in ("id", "full_name", "specialty", "consultation_fee"):
                assert k in d, f"Missing doctor.{k}"

    def test_slots_specialty_fallback(self, patient_ctx):
        r = patient_ctx["s"].get(
            f"{API}/appointments/slots?count=3&specialty=Nonexistent_X",
            timeout=15,
        )
        assert r.status_code == 200
        slots = r.json()["slots"]
        # Fallback should still return slots if any approved doctor exists
        assert len(slots) >= 1, "Expected fallback to any approved doctor"

    def test_slots_count_validation(self, patient_ctx):
        r = patient_ctx["s"].get(f"{API}/appointments/slots?count=100", timeout=10)
        assert r.status_code == 422

    def test_slots_requires_patient(self, doctor_ctx):
        r = doctor_ctx["s"].get(f"{API}/appointments/slots?count=5", timeout=10)
        assert r.status_code == 403


# ----------------- E2E appointment flow -----------------
class TestAppointmentE2E:
    """Full scheduled flow: triage → case → book → pay → verify → start → complete + notifications."""

    @pytest.fixture(scope="class")
    def ctx(self):
        return {}

    def test_01_login(self, ctx):
        ctx["patient_s"], ctx["patient"] = _login(PATIENT)
        ctx["doctor_s"], ctx["doctor"] = _login(DOCTOR)

    def test_02_triage(self, ctx):
        r = ctx["patient_s"].post(f"{API}/triage", json={
            "symptoms": "mild cough for a week", "duration": "7 days",
            "severity": "low", "notes": "",
        }, timeout=90)
        assert r.status_code == 200
        ctx["triage"] = r.json()

    def test_03_create_case(self, ctx):
        r = ctx["patient_s"].post(f"{API}/cases", json={
            "symptoms": "mild cough for a week", "duration": "7 days",
            "severity": "low", "notes": "", "triage": ctx["triage"],
        }, timeout=15)
        assert r.status_code == 200
        ctx["case_id"] = r.json()["id"]

    def test_04_fetch_slots(self, ctx):
        r = ctx["patient_s"].get(f"{API}/appointments/slots?count=12", timeout=15)
        assert r.status_code == 200
        slots = r.json()["slots"]
        assert len(slots) >= 1
        # Find a slot paired with OUR seeded doctor (multiple approved doctors may exist from prior test runs)
        our_doc_id = ctx["doctor"]["id"]
        matching = [s for s in slots if s["doctor"]["id"] == our_doc_id]
        assert matching, f"No slot paired with seeded doctor {our_doc_id}. Got: {[s['doctor']['id'] for s in slots]}"
        ctx["slot"] = matching[0]
        # Save remaining matching slots for cancel-flow test
        ctx["alt_slot"] = matching[1] if len(matching) > 1 else None

    def test_05_book_invalid_mode(self, ctx):
        r = ctx["patient_s"].post(f"{API}/appointments", json={
            "case_id": ctx["case_id"],
            "doctor_id": ctx["slot"]["doctor"]["id"],
            "scheduled_for": ctx["slot"]["scheduled_for"],
            "mode": "telepathy",
        }, timeout=10)
        assert r.status_code == 400

    def test_06_book_appointment(self, ctx):
        r = ctx["patient_s"].post(f"{API}/appointments", json={
            "case_id": ctx["case_id"],
            "doctor_id": ctx["slot"]["doctor"]["id"],
            "scheduled_for": ctx["slot"]["scheduled_for"],
            "mode": "video",
        }, timeout=10)
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["status"] == "scheduled"
        assert a["mode"] == "video"
        assert a["doctor_id"] == ctx["slot"]["doctor"]["id"]
        ctx["appt_id"] = a["id"]

    def test_07_duplicate_slot_409(self, ctx):
        # Try booking same doctor + slot again
        r = ctx["patient_s"].post(f"{API}/appointments", json={
            "case_id": ctx["case_id"],
            "doctor_id": ctx["slot"]["doctor"]["id"],
            "scheduled_for": ctx["slot"]["scheduled_for"],
            "mode": "call",
        }, timeout=10)
        assert r.status_code == 409, f"Expected 409 got {r.status_code}: {r.text}"

    def test_08_case_flow_scheduled(self, ctx):
        r = ctx["patient_s"].get(f"{API}/cases/{ctx['case_id']}", timeout=10)
        assert r.status_code == 200
        c = r.json()
        assert c.get("flow") == "scheduled"
        assert c.get("appointment_id") == ctx["appt_id"]

    def test_09_pay(self, ctx):
        r = ctx["patient_s"].post(f"{API}/payments/initialize", json={
            "case_id": ctx["case_id"], "amount": 5000.0, "currency": "NGN",
        }, timeout=15)
        assert r.status_code == 200
        ctx["ref"] = r.json()["reference"]

    def test_10_verify_payment_case_scheduled(self, ctx):
        r = ctx["patient_s"].post(f"{API}/payments/verify",
                                  json={"reference": ctx["ref"]}, timeout=15)
        assert r.status_code == 200
        # Case should be 'scheduled', NOT 'queued'
        r2 = ctx["patient_s"].get(f"{API}/cases/{ctx['case_id']}", timeout=10)
        assert r2.json()["status"] == "scheduled", (
            f"Expected case status=scheduled, got {r2.json()['status']}"
        )

    def test_11_doctor_notified_appointment_booked(self, ctx):
        # Doctor should have an appointment.booked notification
        time.sleep(0.5)
        r = ctx["doctor_s"].get(f"{API}/notifications", timeout=10)
        assert r.status_code == 200
        data = r.json()
        types = [n["type"] for n in data["items"]]
        assert "appointment.booked" in types, f"Doctor missing appointment.booked notif. Types: {types}"
        assert data["unread"] >= 1

    def test_12_mine_rbac(self, ctx):
        # Patient sees their own
        r = ctx["patient_s"].get(f"{API}/appointments/mine", timeout=10)
        assert r.status_code == 200
        assert any(a["id"] == ctx["appt_id"] for a in r.json())
        # Doctor sees their own
        r2 = ctx["doctor_s"].get(f"{API}/appointments/mine", timeout=10)
        assert r2.status_code == 200
        assert any(a["id"] == ctx["appt_id"] for a in r2.json())

    def test_13_get_appointment_rbac(self, ctx):
        # Patient can fetch their appointment
        r = ctx["patient_s"].get(f"{API}/appointments/{ctx['appt_id']}", timeout=10)
        assert r.status_code == 200
        # Doctor can fetch
        r2 = ctx["doctor_s"].get(f"{API}/appointments/{ctx['appt_id']}", timeout=10)
        assert r2.status_code == 200

    def test_14_pending_doctor_cannot_start(self, ctx, pending_doctor_ctx):
        r = pending_doctor_ctx["s"].post(
            f"{API}/appointments/{ctx['appt_id']}/start", timeout=10
        )
        assert r.status_code == 403, f"Pending doctor should be 403, got {r.status_code}"

    def test_15_doctor_starts_appointment(self, ctx):
        r = ctx["doctor_s"].post(f"{API}/appointments/{ctx['appt_id']}/start", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "consultation_id" in data
        ctx["consultation_id"] = data["consultation_id"]
        # Appointment status -> in_progress
        assert data["appointment"]["status"] == "in_progress"

    def test_16_patient_notified_appointment_starting(self, ctx):
        time.sleep(0.5)
        r = ctx["patient_s"].get(f"{API}/notifications", timeout=10)
        assert r.status_code == 200
        types = [n["type"] for n in r.json()["items"]]
        assert "appointment.starting" in types, f"Patient missing appointment.starting notif. Types: {types}"

    def test_17_start_again_idempotent(self, ctx):
        # Starting again should reuse the same consultation
        r = ctx["doctor_s"].post(f"{API}/appointments/{ctx['appt_id']}/start", timeout=10)
        assert r.status_code == 200
        assert r.json()["consultation_id"] == ctx["consultation_id"]

    def test_18_case_in_consultation(self, ctx):
        r = ctx["patient_s"].get(f"{API}/cases/{ctx['case_id']}", timeout=10)
        assert r.json()["status"] == "in_consultation"

    def test_19_doctor_prescription_and_complete(self, ctx):
        # Prescription
        r = ctx["doctor_s"].post(
            f"{API}/consultations/{ctx['consultation_id']}/prescription",
            json={
                "items": [{"medication": "Paracetamol", "dosage": "500mg",
                           "frequency": "BID", "duration": "5 days",
                           "instructions": "after meals"}],
                "recommended_tests": [],
            }, timeout=10,
        )
        assert r.status_code == 200
        # Complete
        r2 = ctx["doctor_s"].post(
            f"{API}/consultations/{ctx['consultation_id']}/complete",
            json={"final_notes": "Rest and hydrate"}, timeout=120,
        )
        assert r2.status_code == 200, r2.text

    def test_20_appointment_completed(self, ctx):
        r = ctx["doctor_s"].get(f"{API}/appointments/{ctx['appt_id']}", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_21_patient_notified_care_plan_ready(self, ctx):
        time.sleep(0.5)
        r = ctx["patient_s"].get(f"{API}/notifications", timeout=10)
        types = [n["type"] for n in r.json()["items"]]
        assert "consultation.completed" in types, f"Missing consultation.completed. Types: {types}"

    def test_22_mark_one_read(self, ctx):
        r = ctx["patient_s"].get(f"{API}/notifications", timeout=10)
        items = r.json()["items"]
        nid = items[0]["id"]
        r2 = ctx["patient_s"].post(f"{API}/notifications/{nid}/read", timeout=10)
        assert r2.status_code == 200
        # Confirm read
        r3 = ctx["patient_s"].get(f"{API}/notifications", timeout=10)
        item = next(i for i in r3.json()["items"] if i["id"] == nid)
        assert item["read"] is True

    def test_23_mark_all_read(self, ctx):
        r = ctx["patient_s"].post(f"{API}/notifications/read-all", timeout=10)
        assert r.status_code == 200
        r2 = ctx["patient_s"].get(f"{API}/notifications", timeout=10)
        assert r2.json()["unread"] == 0

    def test_24_cannot_cancel_completed(self, ctx):
        r = ctx["patient_s"].post(f"{API}/appointments/{ctx['appt_id']}/cancel", timeout=10)
        assert r.status_code == 400


# ----------------- Cancel flow (separate appointment) -----------------
class TestCancelFlow:
    @pytest.fixture(scope="class")
    def ctx(self):
        return {}

    def test_01_setup_appt(self, ctx):
        ctx["patient_s"], _ = _login(PATIENT)
        ctx["doctor_s"], _ = _login(DOCTOR)
        # Triage + case
        r = ctx["patient_s"].post(f"{API}/triage", json={
            "symptoms": "headache", "duration": "1 day", "severity": "low", "notes": "",
        }, timeout=90)
        triage = r.json()
        r2 = ctx["patient_s"].post(f"{API}/cases", json={
            "symptoms": "headache", "duration": "1 day", "severity": "low",
            "notes": "", "triage": triage,
        }, timeout=15)
        case_id = r2.json()["id"]
        slots = ctx["patient_s"].get(f"{API}/appointments/slots?count=12", timeout=15).json()["slots"]
        # Pick a slot from the seeded doctor's slots not used by prior test
        doctor_id = ctx["doctor_s"].get(f"{API}/doctors/me", timeout=10).json()["id"]
        matching = [s for s in slots if s["doctor"]["id"] == doctor_id]
        assert matching, "No matching slots for seeded doctor"
        # Try several slots to find one not yet booked
        booked = None
        for slot in matching:
            rb = ctx["patient_s"].post(f"{API}/appointments", json={
                "case_id": case_id, "doctor_id": slot["doctor"]["id"],
                "scheduled_for": slot["scheduled_for"], "mode": "call",
            }, timeout=10)
            if rb.status_code == 200:
                booked = rb.json()
                break
        assert booked, "Could not book any matching slot"
        ctx["appt_id"] = booked["id"]
        ctx["doctor_id"] = doctor_id

    def test_02_patient_cancels(self, ctx):
        r = ctx["patient_s"].post(f"{API}/appointments/{ctx['appt_id']}/cancel", timeout=10)
        assert r.status_code == 200

    def test_03_doctor_notified_cancel(self, ctx):
        time.sleep(0.5)
        r = ctx["doctor_s"].get(f"{API}/notifications", timeout=10)
        types = [n["type"] for n in r.json()["items"]]
        assert "appointment.cancelled" in types

    def test_04_cannot_cancel_twice(self, ctx):
        r = ctx["patient_s"].post(f"{API}/appointments/{ctx['appt_id']}/cancel", timeout=10)
        assert r.status_code == 400


# ----------------- Notifications auth -----------------
class TestNotificationsAuth:
    def test_requires_auth(self):
        r = requests.get(f"{API}/notifications", timeout=10)
        assert r.status_code == 401

    def test_read_nonexistent(self, patient_ctx):
        r = patient_ctx["s"].post(f"{API}/notifications/{uuid.uuid4()}/read", timeout=10)
        assert r.status_code == 404
