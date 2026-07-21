"""MongoDB connection singleton."""
import os
from motor.motor_asyncio import AsyncIOMotorClient

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]


async def create_indexes():
    # email unique only when actually a string (OTP patients omit email entirely)
    try:
        await db.users.drop_index("email_1")
    except Exception:
        pass
    await db.users.create_index(
        "email",
        unique=True,
        partialFilterExpression={"email": {"$type": "string"}},
    )
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.health_cases.create_index([("patient_id", 1), ("created_at", -1)])
    await db.health_cases.create_index([("status", 1), ("urgency", 1)])
    await db.consultations.create_index([("case_id", 1)])
    await db.consultations.create_index([("doctor_id", 1), ("status", 1)])
    await db.prescriptions.create_index([("patient_id", 1), ("created_at", -1)])
    await db.care_plans.create_index([("patient_id", 1), ("created_at", -1)])
    await db.vitals.create_index([("patient_id", 1), ("recorded_at", -1)])
    await db.payments.create_index([("reference", 1)], unique=True)
    await db.emails.create_index([("created_at", -1)])
    await db.emails.create_index([("idempotency_key", 1)])
    await db.sms_messages.create_index([("created_at", -1)])
    await db.sms_messages.create_index([("idempotency_key", 1)])
    await db.audit_logs.create_index([("created_at", -1)])
    await db.messages.create_index([("consultation_id", 1), ("created_at", 1)])
    await db.appointments.create_index([("doctor_id", 1), ("scheduled_for", 1)])
    await db.appointments.create_index([("patient_id", 1), ("scheduled_for", 1)])
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.users.create_index("phone", sparse=True)
    await db.otp_codes.create_index([("phone", 1), ("created_at", -1)])
    await db.profile_events.create_index([("user_id", 1), ("created_at", -1)])
    await db.derived_signals.create_index("user_id", unique=True)
    await db.questionnaire_responses.create_index([("user_id", 1), ("code", 1), ("completed_at", -1)])
    await db.questionnaire_responses.create_index([("user_id", 1), ("code", 1), ("context_id", 1)])
