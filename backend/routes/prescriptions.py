"""Prescription read endpoints (write happens in consultations)."""
from fastapi import APIRouter, Depends, HTTPException
from db import db
from auth_utils import get_current_user

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.get("/mine")
async def my_prescriptions(user: dict = Depends(get_current_user)):
    if user["role"] == "patient":
        q = {"patient_id": user["id"]}
    elif user["role"] == "doctor":
        q = {"doctor_id": user["id"]}
    else:
        q = {}
    items = await db.prescriptions.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@router.get("/{prescription_id}")
async def get_prescription(prescription_id: str, user: dict = Depends(get_current_user)):
    p = await db.prescriptions.find_one({"id": prescription_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    if user["role"] == "patient" and p["patient_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    if user["role"] == "doctor" and p["doctor_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    return p
