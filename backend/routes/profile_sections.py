"""Section unlock + completion endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from db import db
from auth_utils import require_role, get_current_user
from unlock_service import (
    section_catalog, get_unlocks, mark_completed, maybe_unlock_30_days, SECTIONS,
)
from profile_service import apply_profile_update

router = APIRouter(prefix="/profile/sections", tags=["profile_sections"])


@router.get("/catalog")
async def catalog():
    """Public schema — no auth required so signup screens can introspect."""
    return {"sections": section_catalog()}


@router.get("/mine")
async def my_sections(user: dict = Depends(require_role("patient"))):
    # Run 30-day check on demand
    await maybe_unlock_30_days(user)
    unlocks = await get_unlocks(user["id"])
    keyed = {u["section_key"]: u for u in unlocks}
    sections = []
    for key, meta in SECTIONS.items():
        u = keyed.get(key)
        # Stored values from user doc
        values = {f["key"]: user.get(f["key"]) for f in meta["fields"]}
        sections.append({
            "key": key,
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "section_number": meta["section_number"],
            "fields": meta["fields"],
            "unlocked": bool(u),
            "unlocked_at": u["unlocked_at"] if u else None,
            "completed": bool(u and u.get("completed_at")),
            "completed_at": u.get("completed_at") if u else None,
            "values": values,
        })
    return {"sections": sections}


@router.post("/{section_key}")
async def save_section(section_key: str, payload: dict, user: dict = Depends(require_role("patient"))):
    if section_key not in SECTIONS:
        raise HTTPException(404, "Unknown section")
    unlock = await db.profile_unlocks.find_one({"user_id": user["id"], "section_key": section_key})
    if not unlock:
        raise HTTPException(403, "Section is not yet unlocked for you")
    allowed = {f["key"] for f in SECTIONS[section_key]["fields"]}
    clean = {k: v for k, v in payload.items() if k in allowed}
    await apply_profile_update(user["id"], clean, source="user")
    await mark_completed(user["id"], section_key)
    return {"ok": True, "section_key": section_key}
