"""Patient profile routes."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from db import db
from models import PatientProfileIn
from auth_utils import require_role

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/me")
async def get_my_profile(user: dict = Depends(require_role("patient"))):
    return user


@router.put("/me")
async def update_profile(payload: PatientProfileIn, user: dict = Depends(require_role("patient"))):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": user["id"]}, {"$set": update})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return updated
