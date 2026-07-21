"""Pydantic schemas for request/response."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ---------- Auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: str  # 'patient' | 'doctor'
    phone: Optional[str] = None
    # Patient extras
    age: Optional[int] = None
    gender: Optional[str] = None
    country: Optional[str] = "Nigeria"
    state: Optional[str] = None
    # Doctor extras
    specialty: Optional[str] = None
    license_number: Optional[str] = None
    years_experience: Optional[int] = None
    consultation_fee: Optional[float] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


# ---------- Patient ----------
class PatientProfileIn(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    allergies: Optional[List[str]] = None
    existing_conditions: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None
    emergency_contact: Optional[str] = None


# ---------- Doctor ----------
class DoctorProfileIn(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    license_number: Optional[str] = None
    years_experience: Optional[int] = None
    consultation_fee: Optional[float] = None
    bio: Optional[str] = None


class DoctorApprovalIn(BaseModel):
    action: str  # 'approve' | 'reject' | 'suspend'
    reason: Optional[str] = None


# ---------- Triage / Cases ----------
class TriageIn(BaseModel):
    symptoms: str
    duration: str
    severity: str  # mild | moderate | severe
    notes: Optional[str] = ""


class CaseCreateIn(BaseModel):
    symptoms: str
    duration: str
    severity: str
    notes: Optional[str] = ""
    triage: Optional[dict] = None


# ---------- Consultation ----------
class MessageIn(BaseModel):
    text: str


class ConsultationNotesIn(BaseModel):
    notes: str


class PrescriptionItemIn(BaseModel):
    medication: str
    dosage: str
    frequency: str
    duration: str
    instructions: Optional[str] = ""


class PrescriptionIn(BaseModel):
    items: List[PrescriptionItemIn]
    recommended_tests: Optional[List[str]] = []


class CompleteConsultationIn(BaseModel):
    final_notes: Optional[str] = ""


# ---------- Vitals ----------
class VitalIn(BaseModel):
    type: str  # weight | bp_systolic | bp_diastolic | heart_rate | blood_sugar | temperature
    value: float
    unit: str
    note: Optional[str] = ""


# ---------- Payments ----------
class InitPaymentIn(BaseModel):
    case_id: str
    amount: float
    currency: str = "NGN"


class VerifyPaymentIn(BaseModel):
    reference: str


# ---------- Feedback ----------
class FeedbackIn(BaseModel):
    consultation_id: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = ""
