"""Iteration 6 — Gate 3 contextual section unlocks.

Coverage (all backend):
  1.  GET /api/profile/sections/mine for fresh patient → 6 sections, none unlocked
  2.  Triage with pregnancy keywords → womens_health unlocked
  3.  Triage with mental-health keywords → mental_wellness unlocked
  4.  POST /sections/mental_wellness with valid payload → 200, completed=true
  5.  POST /sections/lifestyle without unlock → 403
  6.  POST /sections/foo → 404
  7.  Idempotency: triage twice → exactly one unlock row + one notification
  8.  Full consult flow: book + verify payment + accept + complete → lifestyle + healthcare_access
  9.  Prescription issued → pharmacy_prefs unlocked
  10. 30-day rule (Chioma backdated 35 days) → family_health auto-unlocked on GET /mine
  11. Extra (unknown_key) fields are silently dropped on section save
  12. Notification of type 'section.unlocked' visible in /api/notifications
  13. RBAC: doctor cannot POST /profile/sections/* → 403

Cleanup: each fresh patient is TEST_* prefixed; Chioma's profile_unlocks +
section fields are wiped at the start of every test that touches her.
"""
import os
import time
import uuid
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://patient-first-26.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "medinest_db")
_mc = MongoClient(MONGO_URL)
_db = _mc[DB_NAME]

CHIOMA_PHONE = "+2348012345678"


# ============================== helpers ==============================
def _new_phone() -> str:
    return f"+23470{uuid.uuid4().int % 100000000:08d}"


def _send_otp(phone: str):
    r = requests.post(f"{API}/auth/otp/send", json={"phone": phone})
    assert r.status_code == 200, r.text
    return r.json()


def _verify_otp(phone: str, code: str):
    r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


def _register_new_patient(complete_gate2: bool = False):
    s = requests.Session()
    phone = _new_phone()
    code = _send_otp(phone)["dev_otp"]
    reg = _verify_otp(phone, code)["registration_token"]
    payload = {
        "phone": phone,
        "full_name": f"TEST_G3_{uuid.uuid4().hex[:6]}",
        "dob": "1992-04-12",
        "gender": "Female",
        "state": "Lagos",
        "language": "English",
        "consents": {"care_delivery": True, "analytics": False,
                     "model_training": False, "research": False},
    }
    rr = s.post(f"{API}/auth/register/patient", json=payload,
                headers={"X-Registration-Token": reg})
    assert rr.status_code == 200, rr.text
    token = rr.json()["access_token"]
    user = rr.json()["user"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    if complete_gate2:
        g2 = {"genotype": "AA", "blood_group": "O+", "height_cm": 165.0,
              "weight_kg": 60.0, "chronic_conditions": ["None"],
              "current_medications": ["None"], "allergies": ["None"],
              "emergency_contact": "+2348099998888", "active_red_flags": []}
        rg = s.post(f"{API}/profile/gate2", json=g2)
        assert rg.status_code == 200, rg.text
    return s, user


def _login_doctor():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "doctor@docnow.ng", "password": "Doctor@123"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s, r.json()["user"]


def _login_chioma():
    s = requests.Session()
    code = _send_otp(CHIOMA_PHONE)["dev_otp"]
    rv = _verify_otp(CHIOMA_PHONE, code)
    # existing user → direct access_token (no registration_token)
    assert rv.get("verified") is True
    if rv.get("new_user"):
        # Should not be new — Chioma is seeded. If somehow new, register her.
        pass
    token = rv.get("access_token")
    assert token, f"No access_token for existing Chioma: {rv}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    user = rv.get("user") or {}
    return s, user


def _reset_chioma():
    """Wipe Chioma's unlocks + section fields so 30-day tests are deterministic."""
    chi = _db.users.find_one({"phone": CHIOMA_PHONE})
    if not chi:
        return None
    _db.profile_unlocks.delete_many({"user_id": chi["id"]})
    # Clear stored section field values
    all_field_keys = set()
    from unlock_service import SECTIONS  # type: ignore  # noqa
    for meta in SECTIONS.values():
        for f in meta["fields"]:
            all_field_keys.add(f["key"])
    if all_field_keys:
        _db.users.update_one(
            {"id": chi["id"]},
            {"$unset": {k: "" for k in all_field_keys}},
        )
    _db.notifications.delete_many({"user_id": chi["id"], "type": "section.unlocked"})
    return chi["id"]


def _book_pay_accept_complete(pt_s: requests.Session, doc_s: requests.Session,
                              doctor: dict, symptoms: str = "mild headache",
                              issue_prescription: bool = False):
    rc = pt_s.post(f"{API}/cases", json={
        "symptoms": symptoms, "duration": "1 day", "severity": "low"})
    assert rc.status_code == 200, rc.text
    case_id = rc.json()["id"]
    rs = pt_s.get(f"{API}/appointments/slots?count=5")
    assert rs.status_code == 200, rs.text
    slot = next(sl for sl in rs.json()["slots"] if sl["doctor"]["id"] == doctor["id"])
    rb = pt_s.post(f"{API}/appointments", json={
        "case_id": case_id, "doctor_id": doctor["id"],
        "scheduled_for": slot["scheduled_for"], "mode": "video"})
    assert rb.status_code == 200, rb.text
    appt = rb.json()
    init = pt_s.post(f"{API}/payments/initialize",
                     json={"case_id": case_id, "amount": 5000.0, "currency": "NGN"})
    assert init.status_code == 200, init.text
    ref = init.json()["reference"]
    ver = pt_s.post(f"{API}/payments/verify", json={"reference": ref})
    assert ver.status_code == 200, ver.text
    rstart = doc_s.post(f"{API}/appointments/{appt['id']}/start")
    assert rstart.status_code == 200, rstart.text
    cons = rstart.json()
    cons_id = cons.get("consultation_id") or cons.get("id")
    assert cons_id, cons
    if issue_prescription:
        rp = doc_s.post(f"{API}/consultations/{cons_id}/prescription", json={
            "items": [{"medication": "Paracetamol", "dosage": "500mg",
                       "frequency": "TID", "duration": "3 days",
                       "instructions": "with food"}],
            "recommended_tests": [],
        })
        assert rp.status_code == 200, rp.text
    rcomp = doc_s.post(f"{API}/consultations/{cons_id}/complete",
                       json={"final_notes": "OK"})
    assert rcomp.status_code == 200, rcomp.text
    return case_id, cons_id


def _sections_by_key(pt_s):
    r = pt_s.get(f"{API}/profile/sections/mine")
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()["sections"]}


# ============================== tests ==============================
# --- 1. fresh patient sees 6 sections, none unlocked ---
def test_fresh_patient_sees_six_locked_sections():
    pt_s, _ = _register_new_patient()
    sec = _sections_by_key(pt_s)
    expected = {"lifestyle", "womens_health", "mental_wellness",
                "healthcare_access", "pharmacy_prefs", "family_health"}
    assert set(sec.keys()) == expected, sec.keys()
    for k, v in sec.items():
        assert v["unlocked"] is False, f"{k} should be locked"
        assert v["completed"] is False, f"{k} should not be completed"
        assert isinstance(v["fields"], list) and v["fields"], k


# --- 2. pregnancy triage → womens_health unlocked ---
def test_triage_pregnancy_unlocks_womens_health():
    pt_s, _ = _register_new_patient()
    r = pt_s.post(f"{API}/triage", json={
        "symptoms": "I am 20 weeks pregnant with nausea",
        "duration": "1 week", "severity": "mild"})
    assert r.status_code == 200, r.text
    time.sleep(0.3)
    sec = _sections_by_key(pt_s)
    assert sec["womens_health"]["unlocked"] is True, sec["womens_health"]
    # mental_wellness should not be falsely unlocked
    assert sec["mental_wellness"]["unlocked"] is False
    # notification visible
    rn = pt_s.get(f"{API}/notifications")
    assert rn.status_code == 200
    matching = [n for n in rn.json()["items"]
                if n["type"] == "section.unlocked"
                and (n.get("meta") or {}).get("section_key") == "womens_health"]
    assert len(matching) >= 1, rn.json()["items"]


# --- 3. mental triage → mental_wellness unlocked ---
def test_triage_mental_unlocks_mental_wellness():
    pt_s, _ = _register_new_patient()
    r = pt_s.post(f"{API}/triage", json={
        "symptoms": "feeling depressed and anxious",
        "duration": "3 weeks", "severity": "moderate"})
    assert r.status_code == 200, r.text
    time.sleep(0.3)
    sec = _sections_by_key(pt_s)
    assert sec["mental_wellness"]["unlocked"] is True, sec["mental_wellness"]


# --- 4. save mental_wellness with valid payload → completed=true ---
def test_save_mental_wellness_after_unlock():
    pt_s, _ = _register_new_patient()
    r = pt_s.post(f"{API}/triage", json={
        "symptoms": "panic attacks at night",
        "duration": "2 weeks", "severity": "moderate"})
    assert r.status_code == 200, r.text
    payload = {
        "phq2_mood": 2, "phq2_interest": 1,
        "gad2_anxious": 3, "gad2_worry": 2,
        "sleep_quality": 3,
        "prior_diagnoses": "None",
        "current_therapy": False,
    }
    rs = pt_s.post(f"{API}/profile/sections/mental_wellness", json=payload)
    assert rs.status_code == 200, rs.text
    assert rs.json().get("ok") is True
    # verify persisted via GET /mine + values populated
    sec = _sections_by_key(pt_s)["mental_wellness"]
    assert sec["completed"] is True, sec
    assert sec["values"]["phq2_mood"] == 2
    assert sec["values"]["current_therapy"] is False
    # profile_events emitted (any event row for this user)
    me = pt_s.get(f"{API}/profile/events")
    assert me.status_code == 200, me.text
    events = me.json() if isinstance(me.json(), list) else me.json().get("events", [])
    assert len(events) >= 1


# --- 5. saving locked section → 403 ---
def test_save_locked_section_returns_403():
    pt_s, _ = _register_new_patient()
    r = pt_s.post(f"{API}/profile/sections/lifestyle", json={"smoking": "Never"})
    assert r.status_code == 403, r.text
    assert "unlock" in r.text.lower()


# --- 6. unknown section → 404 ---
def test_unknown_section_returns_404():
    pt_s, _ = _register_new_patient()
    r = pt_s.post(f"{API}/profile/sections/foo", json={})
    assert r.status_code == 404, r.text


# --- 7. idempotency: trigger triage twice → one unlock row, one notification ---
def test_triage_idempotent_single_unlock_and_notification():
    pt_s, user = _register_new_patient()
    for _ in range(2):
        r = pt_s.post(f"{API}/triage", json={
            "symptoms": "I am pregnant and tired",
            "duration": "1 week", "severity": "mild"})
        assert r.status_code == 200, r.text
    time.sleep(0.4)
    # Exactly one unlock row in DB
    rows = list(_db.profile_unlocks.find(
        {"user_id": user["id"], "section_key": "womens_health"}))
    assert len(rows) == 1, rows
    # Exactly one notification of this section
    rn = pt_s.get(f"{API}/notifications")
    matching = [n for n in rn.json()["items"]
                if n["type"] == "section.unlocked"
                and (n.get("meta") or {}).get("section_key") == "womens_health"]
    assert len(matching) == 1, matching


# --- 8. full consult flow → lifestyle + healthcare_access unlocked ---
def test_first_consultation_unlocks_lifestyle_and_healthcare():
    pt_s, _ = _register_new_patient(complete_gate2=True)
    doc_s, doc = _login_doctor()
    _book_pay_accept_complete(pt_s, doc_s, doc,
                              symptoms="general tiredness")
    time.sleep(0.3)
    sec = _sections_by_key(pt_s)
    assert sec["lifestyle"]["unlocked"] is True, sec["lifestyle"]
    assert sec["healthcare_access"]["unlocked"] is True, sec["healthcare_access"]


# --- 9. prescription → pharmacy_prefs unlocked ---
def test_prescription_unlocks_pharmacy_prefs():
    pt_s, _ = _register_new_patient(complete_gate2=True)
    doc_s, doc = _login_doctor()
    _book_pay_accept_complete(pt_s, doc_s, doc,
                              symptoms="cough", issue_prescription=True)
    time.sleep(0.3)
    sec = _sections_by_key(pt_s)
    assert sec["pharmacy_prefs"]["unlocked"] is True, sec["pharmacy_prefs"]


# --- 10. 30-day rule via Chioma backdate → family_health auto-unlocked ---
def test_thirty_day_rule_unlocks_family_health_for_chioma():
    chioma_id = _reset_chioma()
    assert chioma_id, "Chioma not seeded — cannot test 30-day rule"
    # Backdate created_at to 35 days ago
    from datetime import datetime, timezone, timedelta
    backdate = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
    _db.users.update_one({"id": chioma_id}, {"$set": {"created_at": backdate}})
    pt_s, _ = _login_chioma()
    sec = _sections_by_key(pt_s)
    assert sec["family_health"]["unlocked"] is True, sec["family_health"]


# --- 11. unknown fields silently dropped on save ---
def test_section_save_drops_unknown_fields():
    pt_s, user = _register_new_patient()
    r = pt_s.post(f"{API}/triage", json={
        "symptoms": "obstetric check needed",
        "duration": "1 day", "severity": "mild"})
    assert r.status_code == 200
    payload = {
        "is_pregnant": True, "weeks_pregnant": 12,
        "contraception": "None",
        "unknown_key": "EVIL", "another_bogus": 42,
    }
    rs = pt_s.post(f"{API}/profile/sections/womens_health", json=payload)
    assert rs.status_code == 200, rs.text
    # confirm unknown keys not stored
    u = _db.users.find_one({"id": user["id"]})
    assert "unknown_key" not in u, u.keys()
    assert "another_bogus" not in u
    assert u.get("is_pregnant") is True
    assert u.get("weeks_pregnant") == 12


# --- 12. section.unlocked notification appears ---
def test_section_unlocked_notification_present():
    pt_s, _ = _register_new_patient()
    pt_s.post(f"{API}/triage", json={
        "symptoms": "ante-natal visit planning",
        "duration": "1 day", "severity": "mild"})
    time.sleep(0.3)
    rn = pt_s.get(f"{API}/notifications")
    assert rn.status_code == 200
    items = rn.json()["items"]
    types = {n["type"] for n in items}
    assert "section.unlocked" in types, types


# --- 13. RBAC: doctor cannot POST to /profile/sections/* ---
def test_doctor_cannot_save_patient_sections():
    doc_s, _ = _login_doctor()
    r = doc_s.post(f"{API}/profile/sections/lifestyle", json={"smoking": "Never"})
    assert r.status_code == 403, r.text
    # GET /mine is also patient-only
    r2 = doc_s.get(f"{API}/profile/sections/mine")
    assert r2.status_code == 403, r2.text
    # Catalog is generic — allowed for any logged-in user
    r3 = doc_s.get(f"{API}/profile/sections/catalog")
    assert r3.status_code == 200, r3.text
    assert len(r3.json()["sections"]) == 6
