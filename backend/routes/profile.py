"""Patient profile gating + completeness + red flags + signals."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from db import db
from auth_utils import require_role, get_current_user
from profile_service import (
    apply_profile_update, profile_completeness, get_signals, red_flag_questions,
)

router = APIRouter(prefix="/profile", tags=["profile"])


class Gate2In(BaseModel):
    genotype: Optional[str] = None   # AA | AS | SS | AC | SC
    blood_group: Optional[str] = None  # A+ / A- / B+ / B- / AB+ / AB- / O+ / O-
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    chronic_conditions: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    emergency_contact: Optional[str] = None
    is_pregnant: Optional[bool] = None
    active_red_flags: List[str] = Field(default_factory=list)
    red_flags_screened_at: Optional[str] = None  # ISO datetime


class ConsentsIn(BaseModel):
    care_delivery: bool = True
    analytics: bool = False
    model_training: bool = False
    research: bool = False


@router.get("/me")
async def get_my_profile(user: dict = Depends(get_current_user)):
    completion = await profile_completeness(user)
    signals = await get_signals(user["id"])
    if signals is None and user.get("role") == "patient":
        from profile_service import recompute_signals
        await recompute_signals(user["id"])
        signals = await get_signals(user["id"])
    return {"user": user, "completion": completion, "signals": signals}


@router.post("/gate2")
async def save_gate2(payload: Gate2In, user: dict = Depends(require_role("patient"))):
    data = payload.model_dump(exclude_none=True)
    # Record the red flag screen timestamp if not provided
    if data.get("red_flags_screened_at") is None:
        from datetime import datetime, timezone
        data["red_flags_screened_at"] = datetime.now(timezone.utc).isoformat()
    updated = await apply_profile_update(user["id"], data, source="user")
    completion = await profile_completeness(updated)
    signals = await get_signals(user["id"])
    return {"user": updated, "completion": completion, "signals": signals}


@router.post("/consents")
async def update_consents(payload: ConsentsIn, user: dict = Depends(get_current_user)):
    if not payload.care_delivery:
        raise HTTPException(400, "Care-delivery consent is required to use DocNow.NG")
    consents = payload.model_dump()
    await db.users.update_one({"id": user["id"]}, {"$set": {"consents": consents}})
    return {"consents": consents}


@router.get("/red-flags")
async def get_red_flags():
    return {"questions": red_flag_questions()}


@router.get("/events")
async def my_profile_events(user: dict = Depends(get_current_user)):
    items = await db.profile_events.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(200).to_list(200)
    return items
