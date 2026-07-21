"""Auth routes: register, login, logout, me, refresh, forgot/reset password, OTP."""
import os
import re
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel, Field
from db import db
from models import RegisterIn, LoginIn, ForgotPasswordIn, ResetPasswordIn
from auth_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, get_current_user, log_audit, _secret, JWT_ALG,
)
from otp import send_otp, verify_otp
import jwt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_MIN = 15


def _strip_sensitive(user: dict) -> dict:
    user.pop("password_hash", None)
    user.pop("_id", None)
    return user


@router.post("/register")
async def register(payload: RegisterIn, response: Response):
    if payload.role not in ("patient", "doctor"):
        raise HTTPException(status_code=400, detail="Role must be 'patient' or 'doctor'")
    email = payload.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": user_id,
        "email": email,
        "password_hash": hash_password(payload.password),
        "full_name": payload.full_name,
        "phone": payload.phone,
        "role": payload.role,
        "status": "approved" if payload.role == "patient" else "pending",
        "created_at": now,
        "updated_at": now,
    }
    if payload.role == "patient":
        doc.update({
            "age": payload.age,
            "gender": payload.gender,
            "country": payload.country or "Nigeria",
            "state": payload.state,
            "allergies": [],
            "existing_conditions": [],
            "current_medications": [],
            "emergency_contact": None,
        })
    else:  # doctor
        doc.update({
            "specialty": payload.specialty,
            "license_number": payload.license_number,
            "years_experience": payload.years_experience,
            "consultation_fee": payload.consultation_fee or 5000.0,
            "bio": "",
            "rating_avg": 0.0,
            "rating_count": 0,
            "earnings_total": 0.0,
        })
    await db.users.insert_one(doc)
    await log_audit(user_id, "user.register", user_id, {"role": payload.role})
    access = create_access_token(user_id, email, payload.role)
    refresh = create_refresh_token(user_id)
    set_auth_cookies(response, access, refresh)
    return {"user": _strip_sensitive({**doc}), "access_token": access}


@router.post("/login")
async def login(payload: LoginIn, response: Response, request: Request):
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    # Brute force check
    record = await db.login_attempts.find_one({"identifier": identifier})
    now = datetime.now(timezone.utc)
    if record and record.get("count", 0) >= LOCKOUT_THRESHOLD:
        locked_at = datetime.fromisoformat(record["locked_at"])
        if now - locked_at < timedelta(minutes=LOCKOUT_WINDOW_MIN):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
        else:
            await db.login_attempts.delete_one({"identifier": identifier})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_at": now.isoformat()}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended. Contact support.")

    await db.login_attempts.delete_one({"identifier": identifier})
    access = create_access_token(user["id"], email, user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    await log_audit(user["id"], "user.login")
    return {"user": _strip_sensitive(dict(user)), "access_token": access}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    await log_audit(user["id"], "user.logout")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALG])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        new_access = create_access_token(user["id"], user["email"], user["role"])
        new_refresh = create_refresh_token(user["id"])
        set_auth_cookies(response, new_access, new_refresh)
        return {"ok": True}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ============= PHONE OTP (patient signup + login) =============
PHONE_REGEX = re.compile(r"^\+\d{8,15}$")


class OtpSendIn(BaseModel):
    phone: str  # E.164 format e.g. +2348012345678


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=8)


class PatientRegisterIn(BaseModel):
    phone: str
    full_name: str
    dob: str  # ISO date YYYY-MM-DD
    gender: str  # Female | Male | Other
    state: str
    language: str = "English"
    consents: dict = Field(default_factory=dict)


def _normalize_phone(p: str) -> str:
    p = p.strip().replace(" ", "").replace("-", "")
    if not PHONE_REGEX.match(p):
        raise HTTPException(status_code=400, detail="Phone must be in E.164 format (e.g. +2348012345678)")
    return p


@router.post("/otp/send")
async def otp_send(payload: OtpSendIn):
    phone = _normalize_phone(payload.phone)
    result = await send_otp(phone, purpose="auth")
    user = await db.users.find_one({"phone": phone}, {"_id": 0, "id": 1, "role": 1, "status": 1})
    result["user_exists"] = bool(user)
    return result


@router.post("/otp/verify")
async def otp_verify(payload: OtpVerifyIn, response: Response):
    phone = _normalize_phone(payload.phone)
    ok = await verify_otp(phone, payload.code, purpose="auth")
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    user = await db.users.find_one({"phone": phone}, {"_id": 0, "password_hash": 0})
    if user:
        if user.get("status") == "suspended":
            raise HTTPException(status_code=403, detail="Account suspended")
        access = create_access_token(user["id"], user.get("email", ""), user["role"])
        refresh = create_refresh_token(user["id"])
        set_auth_cookies(response, access, refresh)
        await log_audit(user["id"], "user.login", meta={"method": "otp"})
        return {"verified": True, "new_user": False, "user": user, "access_token": access}
    # No user yet — issue a short-lived registration token
    reg_token = jwt.encode(
        {"phone": phone, "exp": datetime.now(timezone.utc) + timedelta(minutes=15), "type": "registration"},
        _secret(), algorithm=JWT_ALG,
    )
    return {"verified": True, "new_user": True, "registration_token": reg_token, "phone": phone}


@router.post("/register/patient")
async def register_patient(payload: PatientRegisterIn, response: Response, request: Request):
    reg_token = request.headers.get("X-Registration-Token") or request.cookies.get("registration_token")
    if not reg_token:
        raise HTTPException(status_code=401, detail="Missing registration token")
    try:
        decoded = jwt.decode(reg_token, _secret(), algorithms=[JWT_ALG])
        if decoded.get("type") != "registration":
            raise HTTPException(status_code=401, detail="Invalid token type")
        token_phone = decoded["phone"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Registration token expired — re-verify your phone")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid registration token")

    phone = _normalize_phone(payload.phone)
    if phone != token_phone:
        raise HTTPException(status_code=400, detail="Phone mismatch")
    if await db.users.find_one({"phone": phone}):
        raise HTTPException(status_code=400, detail="Phone already registered")

    consents = {
        "care_delivery": bool(payload.consents.get("care_delivery", True)),
        "analytics": bool(payload.consents.get("analytics", False)),
        "model_training": bool(payload.consents.get("model_training", False)),
        "research": bool(payload.consents.get("research", False)),
    }
    if not consents["care_delivery"]:
        raise HTTPException(status_code=400, detail="Care-delivery consent is required")

    user_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": user_id,
        "phone": phone,
        "full_name": payload.full_name.strip(),
        "dob": payload.dob,
        "gender": payload.gender,
        "country": "Nigeria",
        "state": payload.state,
        "language": payload.language,
        "role": "patient",
        "status": "approved",
        "auth_method": "otp",
        "consents": consents,
        "allergies": [],
        "chronic_conditions": [],
        "current_medications": [],
        "active_red_flags": [],
        "emergency_contact": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    # Emit profile events for initial Gate-1 fields
    from profile_service import log_profile_event, recompute_signals
    for field in ("full_name", "dob", "gender", "state", "language"):
        await log_profile_event(user_id, field, None, doc[field], source="user")
    await recompute_signals(user_id)
    await log_audit(user_id, "user.register", user_id, {"role": "patient", "method": "otp"})
    access = create_access_token(user_id, "", "patient")
    refresh = create_refresh_token(user_id)
    set_auth_cookies(response, access, refresh)
    doc.pop("password_hash", None)
    return {"user": doc, "access_token": access}




@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    # Always succeed to avoid email enumeration
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "token": token,
            "used": False,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
        reset_url = f"{frontend_url}/reset-password?token={token}"
        import email_service
        try:
            await email_service.send_password_reset(email, reset_url, user.get("full_name", ""))
        except Exception as e:
            log.warning("Password-reset email failed for %s: %s", email, e)
        # Only echo the link to logs in dev (stub email) — never leak tokens in prod.
        if not email_service.is_live():
            log.info(f"[PASSWORD RESET] Link: {reset_url} (user={email})")
    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn):
    record = await db.password_reset_tokens.find_one({"token": payload.token, "used": False})
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    exp = record["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > exp:
        raise HTTPException(status_code=400, detail="Token expired")
    await db.users.update_one(
        {"id": record["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password)}},
    )
    await db.password_reset_tokens.update_one({"id": record["id"]}, {"$set": {"used": True}})
    return {"message": "Password reset successful"}


async def seed_admin_and_demo():
    """Seed admin/demo accounts. Set SEED_WIPE=true to WIPE all collections first.
    Defaults to false so a production restart never destroys data."""
    wipe = os.environ.get("SEED_WIPE", "false").lower() == "true"
    if wipe:
        for coll in [
            "users", "health_cases", "consultations", "messages", "prescriptions",
            "care_plans", "vitals", "payments", "feedback", "audit_logs",
            "appointments", "notifications", "otp_codes", "profile_events",
            "derived_signals", "password_reset_tokens", "login_attempts",
        ]:
            await db[coll].delete_many({})
        log.info("DB wiped for fresh seed")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@docnow.ng")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    now = datetime.now(timezone.utc).isoformat()

    # Admin (email/password)
    if not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "full_name": "DocNow.NG Admin",
            "phone": "+2348000000000",
            "role": "admin",
            "status": "approved",
            "auth_method": "password",
            "created_at": now,
            "updated_at": now,
        })
        log.info("Seeded admin user")

    # Demo doctor approved (email/password)
    if not await db.users.find_one({"email": "doctor@docnow.ng"}):
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": "doctor@docnow.ng",
            "password_hash": hash_password("Doctor@123"),
            "full_name": "Dr. Adaeze Okafor",
            "phone": "+2348011112222",
            "role": "doctor",
            "status": "approved",
            "auth_method": "password",
            "specialty": "General Practitioner",
            "license_number": "MDCN-2019-12345",
            "years_experience": 8,
            "consultation_fee": 5000.0,
            "bio": "General Practitioner with 8 years of experience.",
            "rating_avg": 4.8,
            "rating_count": 24,
            "earnings_total": 0.0,
            "created_at": now,
            "updated_at": now,
        })

    # Demo pending doctor
    if not await db.users.find_one({"email": "doctor.pending@docnow.ng"}):
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": "doctor.pending@docnow.ng",
            "password_hash": hash_password("Doctor@123"),
            "full_name": "Dr. Tunde Balogun",
            "phone": "+2348033334444",
            "role": "doctor",
            "status": "pending",
            "auth_method": "password",
            "specialty": "Cardiologist",
            "license_number": "MDCN-2021-67890",
            "years_experience": 5,
            "consultation_fee": 8000.0,
            "bio": "Cardiologist specializing in hypertension.",
            "rating_avg": 0.0,
            "rating_count": 0,
            "earnings_total": 0.0,
            "created_at": now,
            "updated_at": now,
        })

    # Demo patient — phone-OTP based, Gate-1 complete, Gate-2 INCOMPLETE (to demo the trigger)
    demo_phone = "+2348012345678"
    if not await db.users.find_one({"phone": demo_phone, "role": "patient"}):
        pid = str(uuid.uuid4())
        await db.users.insert_one({
            "id": pid,
            "phone": demo_phone,
            "full_name": "Chioma Eze",
            "dob": "1996-06-15",
            "gender": "Female",
            "country": "Nigeria",
            "state": "Lagos",
            "language": "English",
            "role": "patient",
            "status": "approved",
            "auth_method": "otp",
            "consents": {"care_delivery": True, "analytics": True, "model_training": False, "research": False},
            "allergies": [],
            "chronic_conditions": [],
            "current_medications": [],
            "active_red_flags": [],
            "emergency_contact": None,
            "created_at": now,
            "updated_at": now,
        })
        # Recompute initial signals
        from profile_service import recompute_signals
        await recompute_signals(pid)
        log.info(f"Seeded demo patient {demo_phone}")
