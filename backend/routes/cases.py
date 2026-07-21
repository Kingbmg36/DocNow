"""Health cases: created by patients after triage, queue consumed by doctors."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from db import db
from models import CaseCreateIn
from auth_utils import require_role, get_current_user, require_approved_doctor, log_audit
from profile_service import profile_completeness

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("")
async def create_case(payload: CaseCreateIn, user: dict = Depends(require_role("patient"))):
    completion = await profile_completeness(user)
    if not completion["gate_2_done"]:
        raise HTTPException(
            status_code=412,
            detail="Please complete your medical essentials (Gate 2) before starting a consultation.",
        )
    case_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": case_id,
        "patient_id": user["id"],
        "patient_name": user.get("full_name"),
        "symptoms": payload.symptoms,
        "duration": payload.duration,
        "severity": payload.severity,
        "notes": payload.notes or "",
        "triage": payload.triage or {},
        "urgency": (payload.triage or {}).get("urgency", "Moderate"),
        "status": "pending_payment",  # pending_payment -> queued -> assigned -> in_consultation -> completed
        "doctor_id": None,
        "consultation_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.health_cases.insert_one(doc)
    await log_audit(user["id"], "case.create", case_id)
    doc.pop("_id", None)
    return doc


@router.get("/mine")
async def my_cases(user: dict = Depends(require_role("patient"))):
    items = await db.health_cases.find({"patient_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@router.get("/queue")
async def doctor_queue(user: dict = Depends(require_approved_doctor())):
    """Cases waiting to be picked up (queued status, unassigned)."""
    items = await db.health_cases.find(
        {"status": "queued", "doctor_id": None},
        {"_id": 0},
    ).sort([("urgency", 1), ("created_at", 1)]).to_list(100)
    return items


@router.get("/assigned")
async def doctor_assigned(user: dict = Depends(require_approved_doctor())):
    """Cases currently assigned to me (in_consultation)."""
    items = await db.health_cases.find(
        {"doctor_id": user["id"], "status": {"$in": ["assigned", "in_consultation"]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return items


@router.get("/{case_id}")
async def get_case(case_id: str, user: dict = Depends(get_current_user)):
    case = await db.health_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    if user["role"] == "patient" and case["patient_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    if user["role"] == "doctor" and case.get("doctor_id") not in (None, user["id"]):
        raise HTTPException(403, "Case assigned to another doctor")
    return case
