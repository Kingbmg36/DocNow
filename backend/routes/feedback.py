"""Feedback & ratings."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from db import db
from models import FeedbackIn
from auth_utils import require_role, get_current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(payload: FeedbackIn, user: dict = Depends(require_role("patient"))):
    consultation = await db.consultations.find_one({"id": payload.consultation_id})
    if not consultation or consultation["patient_id"] != user["id"]:
        raise HTTPException(404, "Consultation not found")
    existing = await db.feedback.find_one({"consultation_id": payload.consultation_id})
    if existing:
        raise HTTPException(400, "Feedback already submitted")
    doc = {
        "id": str(uuid.uuid4()),
        "consultation_id": payload.consultation_id,
        "patient_id": user["id"],
        "patient_name": user.get("full_name"),
        "doctor_id": consultation["doctor_id"],
        "rating": payload.rating,
        "comment": payload.comment or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.feedback.insert_one(doc)
    # Update doctor rating
    doctor = await db.users.find_one({"id": consultation["doctor_id"]})
    if doctor:
        count = doctor.get("rating_count", 0) + 1
        avg = ((doctor.get("rating_avg", 0.0) * doctor.get("rating_count", 0)) + payload.rating) / count
        await db.users.update_one(
            {"id": doctor["id"]},
            {"$set": {"rating_avg": round(avg, 2), "rating_count": count}},
        )
    doc.pop("_id", None)
    return doc


@router.get("/doctor/me")
async def doctor_feedback(user: dict = Depends(require_role("doctor"))):
    items = await db.feedback.find({"doctor_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@router.get("/all")
async def all_feedback(user: dict = Depends(require_role("admin"))):
    items = await db.feedback.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items
