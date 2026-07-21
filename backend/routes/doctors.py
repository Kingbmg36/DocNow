"""Doctor profile + public listing + license document routes."""
import uuid
from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import Response
from datetime import datetime, timezone
from db import db
from models import DoctorProfileIn
from auth_utils import require_role, get_current_user, log_audit
import storage_service

router = APIRouter(prefix="/doctors", tags=["doctors"])

# License documents: PDFs or images, capped so a bad upload can't exhaust memory.
LICENSE_TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
MAX_LICENSE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.get("/me")
async def get_my_profile(user: dict = Depends(require_role("doctor"))):
    return user


@router.put("/me")
async def update_profile(payload: DoctorProfileIn, user: dict = Depends(require_role("doctor"))):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": user["id"]}, {"$set": update})
    return await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})


@router.get("")
async def list_approved_doctors(specialty: str | None = Query(None)):
    q = {"role": "doctor", "status": "approved"}
    if specialty:
        q["specialty"] = specialty
    docs = await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(100)
    return docs


@router.post("/license")
async def upload_license(file: UploadFile = File(...), user: dict = Depends(require_role("doctor"))):
    """A doctor (pending or approved) uploads their license document for verification."""
    ext = LICENSE_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(400, "License must be a PDF, JPG, or PNG")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_LICENSE_BYTES:
        raise HTTPException(413, "File too large (max 10 MB)")

    key = f"licenses/{user['id']}/{uuid.uuid4().hex}.{ext}"
    await storage_service.put(key, data, file.content_type)
    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "key": key,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
        "status": "pending_review",  # pending_review | verified | rejected
        "uploaded_at": now,
        "backend": storage_service.backend_name(),
    }
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"license_document": meta, "updated_at": now}},
    )
    await log_audit(user["id"], "doctor.license.upload", user["id"], {"key": key, "size": len(data)})
    return {"license_document": meta}


@router.get("/{doctor_id}/license/file")
async def download_license(doctor_id: str, user: dict = Depends(get_current_user)):
    """Stream a doctor's license document. Visible to the doctor themselves or an admin."""
    if user["role"] != "admin" and not (user["role"] == "doctor" and user["id"] == doctor_id):
        raise HTTPException(403, "Forbidden")
    doctor = await db.users.find_one({"id": doctor_id, "role": "doctor"}, {"_id": 0})
    meta = (doctor or {}).get("license_document")
    if not meta or not meta.get("key"):
        raise HTTPException(404, "No license document uploaded")
    data = await storage_service.get_bytes(meta["key"])
    if data is None:
        raise HTTPException(404, "License file not found in storage")
    filename = meta.get("filename") or "license"
    return Response(
        content=data,
        media_type=meta.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
