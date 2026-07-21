"""Consultation flow: doctor accepts case, chat messages, notes, completion."""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from db import db
from models import MessageIn, ConsultationNotesIn, PrescriptionIn, CompleteConsultationIn
from auth_utils import require_role, get_current_user, require_approved_doctor, log_audit
from ai_service import generate_care_plan
from notify import notify
from unlock_service import maybe_unlock_post_consultation, maybe_unlock_post_prescription

router = APIRouter(prefix="/consultations", tags=["consultations"])


@router.post("/accept/{case_id}")
async def accept_case(case_id: str, user: dict = Depends(require_approved_doctor())):
    case = await db.health_cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(404, "Case not found")
    if case["status"] != "queued":
        raise HTTPException(400, f"Case not in queue (status={case['status']})")
    consultation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    patient = await db.users.find_one({"id": case["patient_id"]}, {"_id": 0, "password_hash": 0})
    consultation = {
        "id": consultation_id,
        "case_id": case_id,
        "patient_id": case["patient_id"],
        "patient_name": patient.get("full_name") if patient else "",
        "patient_phone": patient.get("phone") if patient else "",
        "doctor_id": user["id"],
        "doctor_name": user.get("full_name"),
        "status": "in_consultation",  # in_consultation | completed
        "notes": "",
        "started_at": now,
        "ended_at": None,
        "created_at": now,
    }
    await db.consultations.insert_one(consultation)
    await db.health_cases.update_one(
        {"id": case_id},
        {"$set": {"doctor_id": user["id"], "status": "in_consultation",
                  "consultation_id": consultation_id, "updated_at": now}},
    )
    await log_audit(user["id"], "consultation.accept", consultation_id)
    consultation.pop("_id", None)
    return consultation


@router.get("/{consultation_id}")
async def get_consultation(consultation_id: str, user: dict = Depends(get_current_user)):
    c = await db.consultations.find_one({"id": consultation_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    if user["role"] == "patient" and c["patient_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    if user["role"] == "doctor" and c["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    # Attach case + messages
    c["case"] = await db.health_cases.find_one({"id": c["case_id"]}, {"_id": 0})
    c["messages"] = await db.messages.find(
        {"consultation_id": consultation_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    c["prescription"] = await db.prescriptions.find_one(
        {"consultation_id": consultation_id}, {"_id": 0}
    )
    c["care_plan"] = await db.care_plans.find_one(
        {"consultation_id": consultation_id}, {"_id": 0}
    )
    return c


@router.post("/{consultation_id}/messages")
async def send_message(consultation_id: str, payload: MessageIn, user: dict = Depends(get_current_user)):
    c = await db.consultations.find_one({"id": consultation_id})
    if not c:
        raise HTTPException(404, "Not found")
    if user["id"] not in (c["patient_id"], c["doctor_id"]):
        raise HTTPException(403, "Forbidden")
    msg = {
        "id": str(uuid.uuid4()),
        "consultation_id": consultation_id,
        "sender_id": user["id"],
        "sender_role": user["role"],
        "sender_name": user.get("full_name"),
        "text": payload.text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(msg)
    msg.pop("_id", None)
    return msg


@router.put("/{consultation_id}/notes")
async def update_notes(consultation_id: str, payload: ConsultationNotesIn,
                        user: dict = Depends(require_approved_doctor())):
    c = await db.consultations.find_one({"id": consultation_id})
    if not c or c["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    await db.consultations.update_one(
        {"id": consultation_id},
        {"$set": {"notes": payload.notes}},
    )
    return {"ok": True}


@router.post("/{consultation_id}/prescription")
async def issue_prescription(consultation_id: str, payload: PrescriptionIn,
                              user: dict = Depends(require_approved_doctor())):
    c = await db.consultations.find_one({"id": consultation_id})
    if not c or c["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    prescription_id = str(uuid.uuid4())
    code = f"RX-{prescription_id[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": prescription_id,
        "code": code,
        "consultation_id": consultation_id,
        "case_id": c["case_id"],
        "patient_id": c["patient_id"],
        "patient_name": c.get("patient_name"),
        "doctor_id": user["id"],
        "doctor_name": user.get("full_name"),
        "items": [item.model_dump() for item in payload.items],
        "recommended_tests": payload.recommended_tests or [],
        "created_at": now,
    }
    # Upsert (overwrite if doctor edits)
    await db.prescriptions.update_one(
        {"consultation_id": consultation_id},
        {"$set": doc},
        upsert=True,
    )
    await log_audit(user["id"], "prescription.create", prescription_id)
    # Gate 3: unlock pharmacy prefs after a Rx is issued
    await maybe_unlock_post_prescription(c["patient_id"])
    doc.pop("_id", None)
    return doc


@router.post("/{consultation_id}/complete")
async def complete_consultation(consultation_id: str, payload: CompleteConsultationIn,
                                  user: dict = Depends(require_approved_doctor())):
    c = await db.consultations.find_one({"id": consultation_id})
    if not c or c["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    case = await db.health_cases.find_one({"id": c["case_id"]})
    prescription = await db.prescriptions.find_one({"consultation_id": consultation_id})
    now = datetime.now(timezone.utc).isoformat()
    final_notes = payload.final_notes or c.get("notes", "")
    # Generate care plan
    cp = await generate_care_plan(
        triage=(case or {}).get("triage", {}),
        notes=final_notes,
        prescription_items=(prescription or {}).get("items", []),
    )
    care_plan_id = str(uuid.uuid4())
    care_plan = {
        "id": care_plan_id,
        "consultation_id": consultation_id,
        "case_id": c["case_id"],
        "patient_id": c["patient_id"],
        "doctor_id": user["id"],
        "doctor_name": user.get("full_name"),
        "consultation_summary": cp.get("consultation_summary", ""),
        "doctor_advice": cp.get("doctor_advice", final_notes),
        "warning_signs": cp.get("warning_signs", []),
        "recommended_tests": cp.get("recommended_tests", (prescription or {}).get("recommended_tests", [])),
        "follow_up": cp.get("follow_up", ""),
        "health_tips": cp.get("health_tips", []),
        "prescription_id": (prescription or {}).get("id"),
        "created_at": now,
    }
    await db.care_plans.insert_one(care_plan)
    await db.consultations.update_one(
        {"id": consultation_id},
        {"$set": {"status": "completed", "ended_at": now, "notes": final_notes}},
    )
    await db.health_cases.update_one(
        {"id": c["case_id"]},
        {"$set": {"status": "completed", "updated_at": now}},
    )
    # Mark appointment completed if this consultation came from one
    appt_id = c.get("appointment_id")
    if appt_id:
        await db.appointments.update_one(
            {"id": appt_id},
            {"$set": {"status": "completed", "updated_at": now}},
        )
    # Notify patient that the care plan is ready
    await notify(
        c["patient_id"],
        "consultation.completed",
        "Care plan ready",
        f"Dr. {user.get('full_name')} completed your consultation. View your care plan.",
        "",
        {"consultation_id": consultation_id, "care_plan_id": care_plan_id},
    )
    # Deliver care plan summary + prescription code via WhatsApp and email.
    patient_user = await db.users.find_one({"id": c["patient_id"]}, {"phone": 1, "full_name": 1, "email": 1})
    rx_code = (prescription or {}).get("code") or "—"
    cp_summary = cp.get("consultation_summary", "") or cp.get("doctor_advice", "")
    if patient_user and patient_user.get("phone"):
        try:
            from whatsapp_service import send_care_plan_summary
            await send_care_plan_summary(
                patient_user["phone"],
                patient_name=patient_user.get("full_name") or "Patient",
                doctor_name=user.get("full_name") or "Doctor",
                summary=cp_summary,
                rx_code=rx_code,
                consultation_id=consultation_id,
                patient_id=c["patient_id"],
                doctor_id=user["id"],
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("WA care plan failed: %s", e)
    if patient_user and patient_user.get("email"):
        try:
            import email_service
            view_url = f"{os.environ.get('FRONTEND_URL', '').rstrip('/')}/patient"
            await email_service.send_consultation_complete(
                patient_user["email"],
                patient_name=patient_user.get("full_name") or "Patient",
                doctor_name=user.get("full_name") or "Doctor",
                summary=cp_summary,
                rx_code=rx_code,
                view_url=view_url,
                consultation_id=consultation_id,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Email care plan failed: %s", e)
    # Gate 3: after first completed consultation, unlock lifestyle + healthcare access
    await maybe_unlock_post_consultation(c["patient_id"])
    # Credit doctor earnings (70% of case payment if any)
    payment = await db.payments.find_one({"case_id": c["case_id"], "status": "success"})
    if payment:
        share = round(payment["amount"] * 0.7, 2)
        await db.users.update_one(
            {"id": user["id"]},
            {"$inc": {"earnings_total": share}},
        )
    await log_audit(user["id"], "consultation.complete", consultation_id)
    care_plan.pop("_id", None)
    return care_plan


@router.get("/mine/history")
async def my_consultation_history(user: dict = Depends(get_current_user)):
    if user["role"] == "patient":
        q = {"patient_id": user["id"]}
    elif user["role"] == "doctor":
        q = {"doctor_id": user["id"]}
    else:
        q = {}
    items = await db.consultations.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items
