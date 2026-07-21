"""Admin routes: approvals, suspensions, analytics."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from db import db
from models import DoctorApprovalIn
from auth_utils import require_role, log_audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(role: str | None = None, status: str | None = None,
                       user: dict = Depends(require_role("admin"))):
    q: dict = {}
    if role:
        q["role"] = role
    if status:
        q["status"] = status
    items = await db.users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/doctors/pending")
async def pending_doctors(user: dict = Depends(require_role("admin"))):
    items = await db.users.find(
        {"role": "doctor", "status": "pending"}, {"_id": 0, "password_hash": 0}
    ).sort("created_at", -1).to_list(200)
    return items


@router.post("/doctors/{doctor_id}/decision")
async def decide_doctor(doctor_id: str, payload: DoctorApprovalIn,
                          user: dict = Depends(require_role("admin"))):
    if payload.action not in ("approve", "reject", "suspend", "reinstate"):
        raise HTTPException(400, "Invalid action")
    target = await db.users.find_one({"id": doctor_id, "role": "doctor"})
    if not target:
        raise HTTPException(404, "Doctor not found")
    status_map = {"approve": "approved", "reject": "rejected",
                  "suspend": "suspended", "reinstate": "approved"}
    updates = {"status": status_map[payload.action],
               "updated_at": datetime.now(timezone.utc).isoformat()}
    # Reflect the verification decision on the license document, if one was uploaded.
    if target.get("license_document"):
        if payload.action in ("approve", "reinstate"):
            updates["license_document.status"] = "verified"
        elif payload.action == "reject":
            updates["license_document.status"] = "rejected"
    await db.users.update_one({"id": doctor_id}, {"$set": updates})
    await log_audit(user["id"], f"doctor.{payload.action}", doctor_id, {"reason": payload.reason})
    return {"ok": True, "status": status_map[payload.action]}


@router.get("/consultations")
async def all_consultations(user: dict = Depends(require_role("admin"))):
    items = await db.consultations.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/payments")
async def all_payments(user: dict = Depends(require_role("admin"))):
    items = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/audit-logs")
async def audit_logs(user: dict = Depends(require_role("admin"))):
    items = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/analytics")
async def analytics(user: dict = Depends(require_role("admin"))):
    patients = await db.users.count_documents({"role": "patient"})
    doctors = await db.users.count_documents({"role": "doctor"})
    pending_doctors_count = await db.users.count_documents({"role": "doctor", "status": "pending"})
    approved_doctors = await db.users.count_documents({"role": "doctor", "status": "approved"})
    total_cases = await db.health_cases.count_documents({})
    completed_cases = await db.health_cases.count_documents({"status": "completed"})
    queued_cases = await db.health_cases.count_documents({"status": "queued"})
    payments_success = await db.payments.find({"status": "success"}, {"_id": 0}).to_list(2000)
    revenue = sum(p["amount"] for p in payments_success)
    platform_revenue = sum(p.get("platform_share", 0) for p in payments_success)
    return {
        "patients": patients,
        "doctors": doctors,
        "pending_doctors": pending_doctors_count,
        "approved_doctors": approved_doctors,
        "total_cases": total_cases,
        "completed_cases": completed_cases,
        "queued_cases": queued_cases,
        "total_revenue": revenue,
        "platform_revenue": round(platform_revenue, 2),
    }
