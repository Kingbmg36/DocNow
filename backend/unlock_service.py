"""Gate 3 — contextual section unlocks.

Sections are unlocked by natural product events. Each unlock is idempotent and
creates an in-app notification. The frontend renders unlocked sections on the
patient Overview with a 'Complete' CTA that opens a generic schema-driven modal.
"""
import uuid
from datetime import datetime, timezone
from db import db
from notify import notify

# ---- Field types: text | textarea | number | select | multiselect | scale | date | bool ----
SECTIONS: dict = {
    "lifestyle": {
        "title": "Lifestyle",
        "subtitle": "Help us personalise your health tips",
        "section_number": 7,
        "fields": [
            {"key": "smoking", "label": "Smoking", "type": "select", "options": ["Never", "Former", "Current — occasional", "Current — daily"]},
            {"key": "alcohol", "label": "Alcohol", "type": "select", "options": ["Never", "Occasionally", "Weekly", "Daily"]},
            {"key": "exercise_days_per_week", "label": "Exercise days / week", "type": "number", "min": 0, "max": 7},
            {"key": "diet_style", "label": "Diet style", "type": "select", "options": ["Omnivore", "Pescatarian", "Vegetarian", "Vegan", "Other"]},
            {"key": "sleep_hours_avg", "label": "Average sleep (hours / night)", "type": "number", "min": 0, "max": 14},
            {"key": "stress_level", "label": "Typical stress level (1 low – 5 high)", "type": "scale", "min": 1, "max": 5},
        ],
    },
    "womens_health": {
        "title": "Women's Health",
        "subtitle": "For safer, more relevant care",
        "section_number": 8,
        "fields": [
            {"key": "is_pregnant", "label": "Currently pregnant?", "type": "bool"},
            {"key": "weeks_pregnant", "label": "Weeks pregnant (if applicable)", "type": "number", "min": 0, "max": 45},
            {"key": "last_menstrual_period", "label": "Last menstrual period", "type": "date"},
            {"key": "gravidity", "label": "Gravidity (total pregnancies)", "type": "number", "min": 0},
            {"key": "parity", "label": "Parity (live births)", "type": "number", "min": 0},
            {"key": "contraception", "label": "Current contraception", "type": "select", "options": ["None", "Oral pill", "IUD", "Injectable", "Implant", "Condom", "Natural", "Other"]},
            {"key": "prior_complications", "label": "Prior pregnancy complications", "type": "textarea"},
            {"key": "breastfeeding", "label": "Currently breastfeeding?", "type": "bool"},
        ],
    },
    "mental_wellness": {
        "title": "Mental Wellness",
        "subtitle": "Confidential — used only to match you with the right support",
        "section_number": 9,
        "fields": [
            {"key": "phq2_mood", "label": "Past 2 weeks, how often have you felt down or hopeless? (0–3)", "type": "scale", "min": 0, "max": 3},
            {"key": "phq2_interest", "label": "Past 2 weeks, how often have you had little interest in things you usually enjoy? (0–3)", "type": "scale", "min": 0, "max": 3},
            {"key": "gad2_anxious", "label": "Past 2 weeks, how often have you felt nervous or anxious? (0–3)", "type": "scale", "min": 0, "max": 3},
            {"key": "gad2_worry", "label": "Past 2 weeks, how often have you been unable to stop worrying? (0–3)", "type": "scale", "min": 0, "max": 3},
            {"key": "sleep_quality", "label": "Sleep quality (1 poor – 5 excellent)", "type": "scale", "min": 1, "max": 5},
            {"key": "prior_diagnoses", "label": "Prior mental health diagnoses (optional)", "type": "textarea"},
            {"key": "current_therapy", "label": "Currently in therapy or on psychiatric medication?", "type": "bool"},
        ],
    },
    "healthcare_access": {
        "title": "Healthcare Access",
        "subtitle": "So we recommend care you can actually reach",
        "section_number": 10,
        "fields": [
            {"key": "has_insurance", "label": "Do you have health insurance / HMO?", "type": "bool"},
            {"key": "hmo_name", "label": "HMO / Insurance provider", "type": "text"},
            {"key": "preferred_hospital", "label": "Preferred hospital (if any)", "type": "text"},
            {"key": "transport_access", "label": "Transport to a clinic", "type": "select", "options": ["Easy", "Sometimes difficult", "Often difficult"]},
            {"key": "cost_barrier", "label": "Cost barrier to care (1 not at all – 5 major)", "type": "scale", "min": 1, "max": 5},
        ],
    },
    "pharmacy_prefs": {
        "title": "Pharmacy Preferences",
        "subtitle": "Pick how you want to receive your medicines",
        "section_number": 11,
        "fields": [
            {"key": "delivery_mode", "label": "Preferred delivery", "type": "select", "options": ["Home delivery", "Pickup at pharmacy", "Either"]},
            {"key": "preferred_pharmacy", "label": "Preferred pharmacy chain (optional)", "type": "text"},
            {"key": "delivery_address", "label": "Delivery address (if home delivery)", "type": "textarea"},
            {"key": "generic_ok", "label": "OK to substitute generic medicines (usually cheaper)?", "type": "bool"},
        ],
    },
    "family_health": {
        "title": "Family Health",
        "subtitle": "Helps flag hereditary risks",
        "section_number": 15,
        "fields": [
            {"key": "family_conditions", "label": "Conditions known in close family", "type": "multiselect",
             "options": ["Hypertension", "Diabetes", "Stroke", "Heart disease", "Sickle Cell", "Cancer", "Mental illness", "Asthma", "Tuberculosis"]},
            {"key": "family_notes", "label": "Notes (e.g. mother — diabetes at 45)", "type": "textarea"},
        ],
    },
}


def section_catalog() -> list[dict]:
    """Public schema list for the frontend."""
    return [{"key": k, **{kk: vv for kk, vv in v.items()}} for k, v in SECTIONS.items()]


async def unlock(user_id: str, section_key: str, reason: str = "") -> bool:
    """Idempotent unlock + notification."""
    if section_key not in SECTIONS:
        return False
    existing = await db.profile_unlocks.find_one({"user_id": user_id, "section_key": section_key})
    if existing:
        return False
    now = datetime.now(timezone.utc).isoformat()
    await db.profile_unlocks.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "section_key": section_key,
        "section_number": SECTIONS[section_key]["section_number"],
        "reason": reason,
        "unlocked_at": now,
        "completed_at": None,
    })
    sec = SECTIONS[section_key]
    await notify(
        user_id,
        "section.unlocked",
        f"Unlocked: {sec['title']}",
        f"{sec['subtitle']} — takes about 90 seconds.",
        "",
        {"section_key": section_key},
    )
    return True


async def mark_completed(user_id: str, section_key: str):
    await db.profile_unlocks.update_one(
        {"user_id": user_id, "section_key": section_key},
        {"$set": {"completed_at": datetime.now(timezone.utc).isoformat()}},
    )


async def get_unlocks(user_id: str) -> list[dict]:
    items = await db.profile_unlocks.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    return items


# ============ Trigger helpers ============
PREGNANCY_KEYWORDS = ("pregnan", "ante", "obstet", "gyn", "maternal", "miscarr", "labour", "labor")
MENTAL_KEYWORDS = ("psych", "mental", "depress", "anxiet", "anxious", "counsel", "suicid", "panic", "mood")


async def maybe_unlock_from_triage(user_id: str, symptoms: str, triage: dict):
    haystack = (
        (symptoms or "") + " " +
        (triage.get("recommended_specialty", "") or "") + " " +
        (triage.get("summary", "") or "")
    ).lower()
    if any(k in haystack for k in PREGNANCY_KEYWORDS):
        await unlock(user_id, "womens_health", "triage_signal")
    if any(k in haystack for k in MENTAL_KEYWORDS):
        await unlock(user_id, "mental_wellness", "triage_signal")


async def maybe_unlock_post_consultation(user_id: str):
    count = await db.consultations.count_documents({"patient_id": user_id, "status": "completed"})
    if count == 1:
        await unlock(user_id, "lifestyle", "first_consult")
        await unlock(user_id, "healthcare_access", "first_consult")


async def maybe_unlock_post_prescription(user_id: str):
    await unlock(user_id, "pharmacy_prefs", "first_prescription")


async def maybe_unlock_30_days(user: dict):
    created = user.get("created_at")
    if not created:
        return
    try:
        born = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except Exception:
        return
    if born.tzinfo is None:
        born = born.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - born).days >= 30:
        await unlock(user["id"], "family_health", "30_days_in")
