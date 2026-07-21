"""Health vitals tracking."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from db import db
from models import VitalIn
from auth_utils import require_role

router = APIRouter(prefix="/vitals", tags=["vitals"])


@router.post("")
async def add_vital(payload: VitalIn, user: dict = Depends(require_role("patient"))):
    doc = {
        "id": str(uuid.uuid4()),
        "patient_id": user["id"],
        "type": payload.type,
        "value": payload.value,
        "unit": payload.unit,
        "note": payload.note or "",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.vitals.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/mine")
async def list_my_vitals(
    type: str | None = Query(None),
    user: dict = Depends(require_role("patient")),
):
    q = {"patient_id": user["id"]}
    if type:
        q["type"] = type
    items = await db.vitals.find(q, {"_id": 0}).sort("recorded_at", -1).to_list(500)
    return items


@router.delete("/{vital_id}")
async def delete_vital(vital_id: str, user: dict = Depends(require_role("patient"))):
    await db.vitals.delete_one({"id": vital_id, "patient_id": user["id"]})
    return {"ok": True}
