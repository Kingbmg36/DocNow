"""Care Plans read endpoints (auto-created on consultation complete)."""
from fastapi import APIRouter, Depends, HTTPException
from db import db
from auth_utils import get_current_user

router = APIRouter(prefix="/care-plans", tags=["care_plans"])


@router.get("/mine")
async def my_care_plans(user: dict = Depends(get_current_user)):
    if user["role"] == "patient":
        q = {"patient_id": user["id"]}
    elif user["role"] == "doctor":
        q = {"doctor_id": user["id"]}
    else:
        q = {}
    items = await db.care_plans.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@router.get("/{plan_id}")
async def get_plan(plan_id: str, user: dict = Depends(get_current_user)):
    p = await db.care_plans.find_one({"id": plan_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    if user["role"] == "patient" and p["patient_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    return p
