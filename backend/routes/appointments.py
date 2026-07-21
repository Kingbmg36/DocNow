"""Appointment booking flow (alternative to urgent queue).

Flow:
- Patient calls GET /appointments/slots?specialty=… to receive 5 suggested slots.
  Each slot includes a doctor_id (approved, no conflict at that time).
- Patient calls POST /appointments to book a slot — creates appointment + payment ref.
- Patient pays via /payments/verify (existing flow). Case moves to status='scheduled'.
- Doctor sees scheduled appointments in /appointments/mine.
- At appointment time, doctor POSTs /appointments/{id}/start → creates a consultation
  (status='in_consultation') and redirects to consultation room (same as queue flow).
- Consultation completion (existing flow) generates care plan and credits earnings.
"""
import uuid
import random
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from db import db
from auth_utils import require_role, get_current_user, require_approved_doctor, log_audit
from notify import notify

router = APIRouter(prefix="/appointments", tags=["appointments"])

SLOT_MINUTES = 30
SLOT_LOOKAHEAD_HOURS = 72


class BookAppointmentIn(BaseModel):
    case_id: str
    doctor_id: str
    scheduled_for: str  # ISO timestamp
    mode: str  # 'video' | 'call'


def _round_to_next_slot(dt: datetime) -> datetime:
    minutes = (dt.minute // SLOT_MINUTES + 1) * SLOT_MINUTES
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)


@router.get("/slots")
async def suggest_slots(
    specialty: str | None = Query(None),
    count: int = Query(5, ge=1, le=12),
    user: dict = Depends(require_role("patient")),
):
    """Return next N available 30-min slots, each paired with an available doctor.

    Doctors are 24/7 by default. A doctor is "unavailable" for a slot only if
    they already have a confirmed appointment exactly at that timestamp.
    """
    q = {"role": "doctor", "status": "approved"}
    if specialty:
        q["specialty"] = specialty
    doctors = await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(100)
    if not doctors and specialty:
        # Fallback to any approved doctor if no match on specialty
        doctors = await db.users.find(
            {"role": "doctor", "status": "approved"}, {"_id": 0, "password_hash": 0}
        ).to_list(100)
    if not doctors:
        return {"slots": []}

    # Pull confirmed appointments in the lookahead window
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=SLOT_LOOKAHEAD_HOURS)
    appts = await db.appointments.find(
        {
            "status": {"$in": ["scheduled", "in_progress"]},
            "scheduled_for": {"$gte": now.isoformat(), "$lte": end.isoformat()},
        },
        {"_id": 0, "doctor_id": 1, "scheduled_for": 1},
    ).to_list(1000)
    busy = {}
    for a in appts:
        busy.setdefault(a["scheduled_for"], set()).add(a["doctor_id"])

    slots = []
    cursor = _round_to_next_slot(now)
    while len(slots) < count and cursor < end:
        iso = cursor.isoformat()
        # Pick first doctor not busy at this slot; rotate to balance
        candidates = [d for d in doctors if d["id"] not in busy.get(iso, set())]
        if candidates:
            d = random.choice(candidates)
            slots.append({
                "scheduled_for": iso,
                "doctor": {
                    "id": d["id"],
                    "full_name": d.get("full_name"),
                    "specialty": d.get("specialty"),
                    "rating_avg": d.get("rating_avg", 0),
                    "consultation_fee": d.get("consultation_fee", 5000),
                },
            })
        cursor += timedelta(minutes=SLOT_MINUTES)
    return {"slots": slots}


@router.post("")
async def book_appointment(payload: BookAppointmentIn, user: dict = Depends(require_role("patient"))):
    if payload.mode not in ("video", "call"):
        raise HTTPException(400, "Mode must be 'video' or 'call'")
    case = await db.health_cases.find_one({"id": payload.case_id})
    if not case or case["patient_id"] != user["id"]:
        raise HTTPException(404, "Case not found")
    doctor = await db.users.find_one({"id": payload.doctor_id, "role": "doctor", "status": "approved"})
    if not doctor:
        raise HTTPException(404, "Doctor not found or not approved")
    # Conflict check
    conflict = await db.appointments.find_one({
        "doctor_id": payload.doctor_id,
        "scheduled_for": payload.scheduled_for,
        "status": {"$in": ["scheduled", "in_progress"]},
    })
    if conflict:
        raise HTTPException(409, "Slot just booked by someone else. Please pick another.")

    appt_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    room_id = f"docnow-{appt_id[:12]}"
    doc = {
        "id": appt_id,
        "case_id": payload.case_id,
        "patient_id": user["id"],
        "patient_name": user.get("full_name"),
        "doctor_id": payload.doctor_id,
        "doctor_name": doctor.get("full_name"),
        "specialty": doctor.get("specialty"),
        "scheduled_for": payload.scheduled_for,
        "mode": payload.mode,  # 'video' | 'call'
        "room_url": f"/room/{room_id}",  # mock placeholder
        "status": "scheduled",  # scheduled | in_progress | completed | cancelled
        "consultation_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.appointments.insert_one(doc)
    await db.health_cases.update_one(
        {"id": payload.case_id},
        {"$set": {
            "appointment_id": appt_id,
            "doctor_id": payload.doctor_id,
            "scheduled_for": payload.scheduled_for,
            "flow": "scheduled",
            "updated_at": now,
        }},
    )
    await log_audit(user["id"], "appointment.book", appt_id, {"mode": payload.mode})

    # Fire-and-forget WhatsApp confirmation (stubbed in dev, real in prod)
    if user.get("phone"):
        try:
            from whatsapp_service import send_appointment_confirmation
            await send_appointment_confirmation(
                user["phone"],
                patient_name=user.get("full_name") or "Patient",
                doctor_name=doctor.get("full_name") or "Doctor",
                when_iso=payload.scheduled_for,
                appointment_id=appt_id,
                patient_id=user["id"],
                doctor_id=payload.doctor_id,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("WA appt confirm failed: %s", e)

    doc.pop("_id", None)
    return doc


@router.get("/mine")
async def my_appointments(user: dict = Depends(get_current_user)):
    if user["role"] == "patient":
        q = {"patient_id": user["id"]}
    elif user["role"] == "doctor":
        q = {"doctor_id": user["id"]}
    else:
        q = {}
    items = await db.appointments.find(q, {"_id": 0}).sort("scheduled_for", 1).to_list(200)
    return items


@router.get("/{appt_id}")
async def get_appointment(appt_id: str, user: dict = Depends(get_current_user)):
    a = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Not found")
    if user["role"] == "patient" and a["patient_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    if user["role"] == "doctor" and a["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    return a


@router.post("/{appt_id}/start")
async def start_appointment(appt_id: str, user: dict = Depends(require_approved_doctor())):
    """Doctor opens the consultation at appointment time."""
    a = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not a or a["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    if a["status"] not in ("scheduled", "in_progress"):
        raise HTTPException(400, f"Appointment status is {a['status']}")
    # Reuse existing consultation if already started
    if a.get("consultation_id"):
        return {"consultation_id": a["consultation_id"], "appointment": a}

    case = await db.health_cases.find_one({"id": a["case_id"]})
    if not case:
        raise HTTPException(404, "Case missing")

    consultation_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    consultation = {
        "id": consultation_id,
        "case_id": a["case_id"],
        "patient_id": a["patient_id"],
        "patient_name": a["patient_name"],
        "doctor_id": user["id"],
        "doctor_name": user.get("full_name"),
        "appointment_id": appt_id,
        "mode": a["mode"],
        "room_url": a["room_url"],
        "status": "in_consultation",
        "notes": "",
        "started_at": now_iso,
        "ended_at": None,
        "created_at": now_iso,
    }
    await db.consultations.insert_one(consultation)
    await db.appointments.update_one(
        {"id": appt_id},
        {"$set": {"status": "in_progress", "consultation_id": consultation_id, "updated_at": now_iso}},
    )
    await db.health_cases.update_one(
        {"id": a["case_id"]},
        {"$set": {"status": "in_consultation", "consultation_id": consultation_id, "doctor_id": user["id"], "updated_at": now_iso}},
    )
    await notify(
        a["patient_id"],
        "appointment.starting",
        f"Dr. {user.get('full_name')} is ready",
        f"Your {a['mode']} consultation is starting now.",
        f"/consultation/{consultation_id}",
        {"appointment_id": appt_id, "consultation_id": consultation_id},
    )
    await log_audit(user["id"], "appointment.start", appt_id)
    consultation.pop("_id", None)
    return {"consultation_id": consultation_id, "appointment": {**a, "consultation_id": consultation_id, "status": "in_progress"}}


@router.post("/{appt_id}/cancel")
async def cancel_appointment(appt_id: str, user: dict = Depends(get_current_user)):
    a = await db.appointments.find_one({"id": appt_id})
    if not a:
        raise HTTPException(404, "Not found")
    if user["id"] not in (a["patient_id"], a["doctor_id"]) and user["role"] != "admin":
        raise HTTPException(403, "Forbidden")
    if a["status"] not in ("scheduled",):
        raise HTTPException(400, f"Cannot cancel — status is {a['status']}")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "cancelled", "updated_at": now_iso}})
    # Notify the other party
    other = a["doctor_id"] if user["id"] == a["patient_id"] else a["patient_id"]
    await notify(
        other,
        "appointment.cancelled",
        "Appointment cancelled",
        f"The {a['mode']} appointment on {a['scheduled_for']} was cancelled.",
        "",
        {"appointment_id": appt_id},
    )
    return {"ok": True}
