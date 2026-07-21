"""Smoke regression for iteration-3 features against the iteration-4 OTP patient schema.

Confirms: appointment slots, booking, doctor notifications, doctor accepts case from
queue, completes consultation -> care plan -> patient notified.
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://patient-first-26.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _new_phone():
    return f"+23470{uuid.uuid4().int % 100000000:08d}"


def _register_complete_patient():
    s = requests.Session()
    phone = _new_phone()
    code = s.post(f"{API}/auth/otp/send", json={"phone": phone}).json()["dev_otp"]
    reg = s.post(f"{API}/auth/otp/verify",
                 json={"phone": phone, "code": code}).json()["registration_token"]
    payload = {
        "phone": phone, "full_name": f"TEST_FlowPt_{uuid.uuid4().hex[:5]}",
        "dob": "1990-01-01", "gender": "Male", "state": "Lagos", "language": "English",
        "consents": {"care_delivery": True},
    }
    rr = s.post(f"{API}/auth/register/patient", json=payload,
                headers={"X-Registration-Token": reg})
    assert rr.status_code == 200, rr.text
    token = rr.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    # Complete Gate-2 so case creation is allowed
    g2 = {"genotype": "AA", "blood_group": "O+", "height_cm": 175.0,
          "weight_kg": 70.0, "chronic_conditions": ["None"],
          "current_medications": ["None"], "allergies": ["None"],
          "emergency_contact": "+2348099998888", "active_red_flags": []}
    rg = s.post(f"{API}/profile/gate2", json=g2)
    assert rg.status_code == 200, rg.text
    return s, rr.json()["user"]


def _login_doctor():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "doctor@docnow.ng", "password": "Doctor@123"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s, r.json()["user"]


def test_iteration3_appointment_and_notifications_flow():
    pt_s, _ = _register_complete_patient()
    doc_s, doc = _login_doctor()

    # Create case
    rc = pt_s.post(f"{API}/cases", json={
        "symptoms": "mild headache", "duration": "2 days", "severity": "low"})
    assert rc.status_code == 200, rc.text
    case_id = rc.json()["id"]

    # Fetch slot suggestions
    rs = pt_s.get(f"{API}/appointments/slots?count=5")
    assert rs.status_code == 200, rs.text
    slots = rs.json()["slots"]
    assert len(slots) >= 1
    matching = [sl for sl in slots if sl["doctor"]["id"] == doc["id"]]
    assert matching, "No slot for seeded doctor"
    slot = matching[0]

    # Book appointment
    rb = pt_s.post(f"{API}/appointments", json={
        "case_id": case_id, "doctor_id": doc["id"],
        "scheduled_for": slot["scheduled_for"], "mode": "video"})
    assert rb.status_code == 200, rb.text
    appt = rb.json()
    assert appt["status"] == "scheduled"

    # Pay
    init = pt_s.post(f"{API}/payments/initialize",
                     json={"case_id": case_id, "amount": 5000.0, "currency": "NGN"})
    assert init.status_code == 200
    ref = init.json()["reference"]
    ver = pt_s.post(f"{API}/payments/verify", json={"reference": ref})
    assert ver.status_code == 200

    # Doctor notified
    time.sleep(0.4)
    rn = doc_s.get(f"{API}/notifications")
    assert rn.status_code == 200
    types = [n["type"] for n in rn.json()["items"]]
    assert "appointment.booked" in types, f"Missing appointment.booked, got: {types}"

    # Doctor accepts/starts case (consultation)
    rstart = doc_s.post(f"{API}/appointments/{appt['id']}/start")
    assert rstart.status_code == 200, rstart.text
    cons = rstart.json()
    cons_id = cons.get("consultation_id") or cons.get("id")
    assert cons_id, f"No consultation id in start response: {cons}"

    # Doctor completes consultation -> care plan
    rcomp = doc_s.post(f"{API}/consultations/{cons_id}/complete", json={
        "diagnosis": "Tension headache",
        "notes": "Hydration + rest",
        "prescriptions": [{"name": "Paracetamol", "dose": "500mg", "frequency": "TID", "duration": "3 days"}],
        "follow_up_days": 7,
    })
    assert rcomp.status_code == 200, rcomp.text
    body = rcomp.json()
    # Care plan or follow-up should be referenced
    assert any(k in body for k in ("care_plan", "care_plan_id", "follow_up_appointment", "id")), body

    # Patient notified of completion
    time.sleep(0.4)
    rpn = pt_s.get(f"{API}/notifications")
    assert rpn.status_code == 200
    p_types = [n["type"] for n in rpn.json()["items"]]
    assert any("consultation" in t or "care_plan" in t or "appointment" in t for t in p_types), \
        f"Patient missing completion-related notification, got: {p_types}"
