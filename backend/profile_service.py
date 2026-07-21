"""Versioned patient profile + event log + derived signals.

Three layers:
  1. users (current snapshot, mutable) — contains profile fields
  2. profile_events (append-only history) — each change is an event
  3. derived_signals (computed view, recomputed on every profile change)
"""
import uuid
from datetime import datetime, timezone
from db import db

# Required fields for each "gate" — used to compute completeness
GATE_1_FIELDS = {"full_name", "phone", "dob", "gender", "state", "language"}
GATE_2_FIELDS = {
    "genotype", "blood_group", "height_cm", "weight_kg",
    "red_flags_screened_at", "emergency_contact",
}
# Note: chronic_conditions/current_medications/allergies are NOT in this set —
# they are acknowledged via the red_flags_screened_at timestamp (set when patient
# completes the Gate-2 wizard, regardless of whether any conditions exist).
GATE_3_FIELDS = set()  # contextual, optional

SECTION_14_RED_FLAGS = [
    {"key": "chest_pain", "label": "Severe chest pain or pressure", "severity": "Emergency"},
    {"key": "breathing", "label": "Difficulty breathing or shortness of breath at rest", "severity": "Emergency"},
    {"key": "stroke", "label": "Sudden weakness/numbness on one side, slurred speech", "severity": "Emergency"},
    {"key": "head_injury", "label": "Severe head injury with confusion or vomiting", "severity": "Emergency"},
    {"key": "bleeding", "label": "Heavy uncontrolled bleeding", "severity": "Emergency"},
    {"key": "pregnancy_bleed", "label": "Pregnancy with bleeding or severe abdominal pain", "severity": "Emergency"},
    {"key": "suicidal", "label": "Thoughts of harming self or others", "severity": "Emergency"},
    {"key": "anaphylaxis", "label": "Severe allergic reaction (swelling, hives + breathing trouble)", "severity": "Emergency"},
    {"key": "high_fever", "label": "Fever above 39.5°C (103°F) lasting more than 2 days", "severity": "High"},
    {"key": "dehydration", "label": "Unable to keep fluids down for 24+ hours", "severity": "High"},
]


def red_flag_questions() -> list[dict]:
    return SECTION_14_RED_FLAGS


async def log_profile_event(user_id: str, field: str, old_value, new_value, source: str = "user"):
    """Append-only change history. Powers trend analysis."""
    await db.profile_events.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "source": source,  # 'user' | 'doctor' | 'system' | 'derived'
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def apply_profile_update(user_id: str, updates: dict, source: str = "user"):
    """Patch user fields AND emit a profile_event for each change."""
    current = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not current:
        return None
    changed = {}
    for field, new_val in updates.items():
        if new_val is None:
            continue
        old_val = current.get(field)
        if old_val != new_val:
            changed[field] = new_val
            await log_profile_event(user_id, field, old_val, new_val, source)
    if changed:
        changed["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": user_id}, {"$set": changed})
    # Recompute derived signals
    await recompute_signals(user_id)
    return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})


def _gate_completion(user: dict) -> dict:
    def filled(fields: set) -> tuple[int, int]:
        present = sum(1 for f in fields if user.get(f) not in (None, "", [], {}))
        return present, len(fields)

    g1_filled, g1_total = filled(GATE_1_FIELDS)
    g2_filled, g2_total = filled(GATE_2_FIELDS)
    total_filled = g1_filled + g2_filled
    total_total = g1_total + g2_total
    return {
        "gate_1_done": g1_filled == g1_total,
        "gate_1_progress": round(100 * g1_filled / max(1, g1_total)),
        "gate_2_done": g2_filled == g2_total,
        "gate_2_progress": round(100 * g2_filled / max(1, g2_total)),
        "overall_percent": round(100 * total_filled / max(1, total_total)),
    }


async def recompute_signals(user_id: str):
    """Compute risk_score, triage_priority, care_segment, next_best_action."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user or user.get("role") != "patient":
        return

    risk = 0
    chronic = user.get("chronic_conditions") or []
    # Each chronic condition adds risk
    risk += min(len(chronic), 5) * 10
    # Age component (uses dob)
    dob = user.get("dob")
    age = None
    if dob:
        try:
            born = datetime.fromisoformat(dob.split("T")[0])
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - born).days // 365
            if age >= 60:
                risk += 20
            elif age >= 40:
                risk += 10
        except Exception:
            pass
    # Pregnancy flag boosts risk
    if user.get("is_pregnant"):
        risk += 15
    # Active red flags
    rf = user.get("active_red_flags") or []
    if rf:
        risk += 30

    triage_priority = (
        "Emergency" if risk >= 60 or rf else
        "High" if risk >= 40 else
        "Moderate" if risk >= 20 else
        "Low"
    )

    segments = []
    if "Diabetes" in chronic:
        segments.append("diabetic")
    if "Hypertension" in chronic:
        segments.append("hypertensive")
    if "Sickle Cell" in chronic:
        segments.append("sickle_cell")
    if user.get("is_pregnant"):
        segments.append("maternal")
    if age is not None and age >= 60:
        segments.append("senior")
    care_segment = ",".join(segments) or "general"

    next_actions = []
    completion = _gate_completion(user)
    if not completion["gate_2_done"]:
        next_actions.append({"key": "complete_profile", "title": "Complete your medical essentials", "priority": "high"})
    if "Hypertension" in chronic and not _has_recent_vital(user_id):
        next_actions.append({"key": "log_bp", "title": "Log a blood-pressure reading today", "priority": "medium"})
    if user.get("is_pregnant"):
        next_actions.append({"key": "antenatal", "title": "Book your next antenatal check", "priority": "high"})

    signals = {
        "user_id": user_id,
        "risk_score": min(risk, 100),
        "triage_priority": triage_priority,
        "care_segment": care_segment,
        "next_best_actions": next_actions,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.derived_signals.update_one(
        {"user_id": user_id},
        {"$set": signals},
        upsert=True,
    )


def _has_recent_vital(user_id: str) -> bool:
    return False  # simplified


async def get_signals(user_id: str) -> dict | None:
    return await db.derived_signals.find_one({"user_id": user_id}, {"_id": 0})


async def profile_completeness(user: dict) -> dict:
    return _gate_completion(user)
