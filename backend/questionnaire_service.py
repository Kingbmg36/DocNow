"""Generic questionnaire engine.

A questionnaire = ordered list of sections; each section = ordered list of fields.
The same schema renderer (QuestionnaireRunner.jsx) handles every questionnaire.

Each response is stored in db.questionnaire_responses with shape:
  { id, user_id, code, version, responses:{<field_key>: value, ...},
    context_id (optional, e.g. consultation_id), started_at, completed_at }
"""
from datetime import datetime, timezone
import uuid
from db import db


QUESTIONNAIRES: dict = {
    # ---------- PATIENT INTAKE — Nigeria-focused, on first dashboard visit ----------
    "patient_intake": {
        "title": "Your health profile",
        "subtitle": "Six short sections — helps your doctor, sharpens AI triage, and unlocks personalised care.",
        "role": "patient",
        "trigger": "first_dashboard_visit",
        "version": 2,
        "sections": [
            {
                "key": "about_you",
                "title": "About you",
                "fields": [
                    {"key": "lga", "label": "Local Government Area (LGA)", "type": "text"},
                    {"key": "home_address", "label": "Home address (street, area)", "type": "textarea"},
                    {"key": "occupation", "label": "Occupation", "type": "text"},
                    {"key": "marital_status", "label": "Marital status", "type": "select",
                     "options": ["Single", "Married", "Divorced", "Widowed", "Prefer not to say"]},
                    {"key": "next_of_kin_name", "label": "Next of kin — full name", "type": "text"},
                    {"key": "next_of_kin_phone", "label": "Next of kin — phone number", "type": "text"},
                    {"key": "next_of_kin_relationship", "label": "Next of kin — relationship", "type": "select",
                     "options": ["Spouse", "Parent", "Sibling", "Child", "Friend", "Other"]},
                    {"key": "accessibility_needs", "label": "Any disability or condition that affects communication or movement?", "type": "multiselect",
                     "options": ["None", "Hearing impairment", "Visual impairment", "Mobility impairment", "Speech impairment", "Other"]},
                    {"key": "preferred_consult_mode", "label": "Preferred consultation mode", "type": "select",
                     "options": ["Video", "Voice call", "Text chat", "No preference"]},
                ],
            },
            {
                "key": "general_health",
                "title": "General health & medical history",
                "fields": [
                    {"key": "overall_health", "label": "How would you describe your overall health?", "type": "select",
                     "options": ["Excellent", "Good", "Fair", "Poor"]},
                    {"key": "bp_status", "label": "Do you know your blood pressure status?", "type": "select",
                     "options": ["Normal", "High blood pressure", "Low blood pressure", "I don't know"]},
                    {"key": "past_illnesses", "label": "Have you ever been diagnosed with any of these?", "type": "multiselect",
                     "options": ["Hypertension", "Diabetes", "Asthma", "Ulcer", "Sickle Cell Disease", "Tuberculosis",
                                 "Hepatitis", "HIV/AIDS", "Arthritis", "Heart Disease", "Kidney Disease",
                                 "Mental Health Condition", "Epilepsy", "Cancer", "None"]},
                    {"key": "past_illnesses_other", "label": "Other diagnoses (specify)", "type": "text"},
                    {"key": "past_surgeries", "label": "Past surgeries", "type": "multiselect",
                     "options": ["Appendectomy", "C-section", "Tonsillectomy", "Hernia repair", "Cataract",
                                 "Cholecystectomy", "Hysterectomy", "None", "Other"]},
                    {"key": "ever_hospitalized", "label": "Ever been hospitalized in the past 5 years?", "type": "bool"},
                    {"key": "hospitalization_notes", "label": "Most recent admission — reason / year (optional)", "type": "textarea"},
                    {"key": "malaria_last_12mo", "label": "Have you had malaria in the last 12 months?", "type": "select",
                     "options": ["No", "Once", "2–3 times", "More than 3 times"]},
                    {"key": "sickness_frequency", "label": "How often do you fall sick in a year?", "type": "select",
                     "options": ["Rarely (0–1)", "Sometimes (2–4)", "Often (5–8)", "Very often (more than 8)"]},
                    {"key": "currently_treating", "label": "Currently receiving treatment for any condition?", "type": "textarea"},
                    {"key": "bad_drug_reaction", "label": "Ever reacted badly to a medication?", "type": "bool"},
                ],
            },
            {
                "key": "immunizations",
                "title": "Immunizations",
                "fields": [
                    {"key": "childhood_immunizations_complete", "label": "Childhood immunizations complete?", "type": "bool"},
                    {"key": "yellow_fever", "label": "Yellow fever vaccinated?", "type": "bool"},
                    {"key": "hepatitis_b", "label": "Hepatitis B vaccinated?", "type": "bool"},
                    {"key": "covid_doses", "label": "COVID-19 vaccine doses", "type": "select",
                     "options": ["None", "1 dose", "2 doses", "Boosted"]},
                    {"key": "last_tetanus_date", "label": "Last tetanus booster (approx. date)", "type": "date"},
                ],
            },
            {
                "key": "lifestyle",
                "title": "Lifestyle & habits",
                "fields": [
                    {"key": "smoking", "label": "Do you smoke?", "type": "select",
                     "options": ["Never", "Occasionally", "Frequently", "Former smoker"]},
                    {"key": "alcohol", "label": "Do you drink alcohol?", "type": "select",
                     "options": ["Never", "Occasionally", "Weekly", "Daily"]},
                    {"key": "exercise_days_per_week", "label": "How many days a week do you exercise?", "type": "number", "min": 0, "max": 7},
                    {"key": "sleep_hours_avg", "label": "How many hours do you sleep daily?", "type": "number", "min": 0, "max": 14},
                    {"key": "stress_level_baseline", "label": "How would you rate your stress level? (1 low – 5 high)", "type": "scale", "min": 1, "max": 5},
                    {"key": "diet_style", "label": "What best describes your diet?", "type": "select",
                     "options": ["Balanced", "Mostly carbohydrates", "Fast food often", "Low food access",
                                 "High protein", "Vegetarian", "Other"]},
                ],
            },
            {
                "key": "mental_wellness",
                "title": "Mental & emotional wellbeing",
                "fields": [
                    {"key": "phq2_mood", "label": "Past 2 weeks — felt down or hopeless? (0 none – 3 nearly every day)", "type": "scale", "min": 0, "max": 3},
                    {"key": "phq2_interest", "label": "Past 2 weeks — little interest in things you usually enjoy? (0–3)", "type": "scale", "min": 0, "max": 3},
                    {"key": "gad2_anxious", "label": "Past 2 weeks — felt nervous or anxious? (0–3)", "type": "scale", "min": 0, "max": 3},
                    {"key": "gad2_worry", "label": "Past 2 weeks — unable to stop worrying? (0–3)", "type": "scale", "min": 0, "max": 3},
                    {"key": "sleep_quality_baseline", "label": "Sleep quality lately (1 poor – 5 excellent)", "type": "scale", "min": 1, "max": 5},
                    {"key": "wants_mental_support", "label": "Would you like access to mental health support?", "type": "bool"},
                ],
            },
            {
                "key": "access_and_goals",
                "title": "Healthcare access, goals & consent",
                "fields": [
                    {"key": "has_primary_doctor", "label": "Do you have a primary doctor?", "type": "bool"},
                    {"key": "nearest_hospital_km", "label": "Distance to nearest hospital (approx. km)", "type": "number", "min": 0, "max": 200},
                    {"key": "usual_hospital_type", "label": "What type of hospital do you usually use?", "type": "select",
                     "options": ["Government hospital", "Private hospital", "Pharmacy / Chemist",
                                 "Traditional medicine", "Faith-based center", "None"]},
                    {"key": "delayed_treatment_cost", "label": "Ever delayed treatment because of cost?", "type": "bool"},
                    {"key": "insurance", "label": "Do you have health insurance?", "type": "select",
                     "options": ["NHIA", "HMO", "Employer insurance", "None"]},
                    {"key": "goals", "label": "What would you like DocNow.NG to help you with?", "type": "multiselect",
                     "options": ["Quick doctor consultations", "Symptom checking", "Medication reminders",
                                 "Family healthcare", "Pregnancy support", "Chronic disease management",
                                 "Mental health support", "Fitness & wellness", "Affordable healthcare",
                                 "Emergency support"]},
                    {"key": "comms_channel", "label": "How would you like us to contact you?", "type": "multiselect",
                     "options": ["SMS", "WhatsApp", "Push Notification", "Email"]},
                    {"key": "wants_health_tips", "label": "Would you like daily health tips & reminders?", "type": "bool"},
                    {"key": "ai_triage_ok", "label": "Comfortable using AI symptom checks before a doctor?", "type": "bool"},
                    {"key": "photo_upload_ok", "label": "Willing to upload photos for skin / visible symptom analysis?", "type": "bool"},
                    {"key": "anonymous_data_ok", "label": "Allow anonymous health data to improve public-health insights in Nigeria?", "type": "bool"},
                ],
            },
            {
                "key": "family_health",
                "title": "Family health (optional)",
                "fields": [
                    {"key": "family_conditions", "label": "Conditions known in close family", "type": "multiselect",
                     "options": ["Hypertension", "Diabetes", "Sickle Cell", "Cancer", "Heart Disease",
                                 "Mental Health Conditions", "Stroke", "Asthma", "Tuberculosis", "None"]},
                    {"key": "family_notes", "label": "Notes (e.g. mother — diabetes at 45)", "type": "textarea"},
                    {"key": "wants_dependent_profiles", "label": "Want to create profiles for children or dependents?", "type": "bool"},
                ],
            },
        ],
    },

    # ---------- DOCTOR ONBOARDING — required before going live ----------
    "doctor_onboarding": {
        "title": "Doctor onboarding",
        "subtitle": "Required before your profile is reviewed for approval.",
        "role": "doctor",
        "trigger": "registration",
        "version": 1,
        "sections": [
            {
                "key": "identity",
                "title": "Identity & qualification",
                "fields": [
                    {"key": "mdcn_number", "label": "MDCN registration number", "type": "text"},
                    {"key": "mdcn_year", "label": "Year of MDCN registration", "type": "number", "min": 1970, "max": 2030},
                    {"key": "year_qualified", "label": "Year qualified (MBBS / MD)", "type": "number", "min": 1970, "max": 2030},
                    {"key": "medical_school", "label": "Medical school", "type": "text"},
                    {"key": "profile_photo_url", "label": "Profile photo URL (optional)", "type": "text"},
                ],
            },
            {
                "key": "practice",
                "title": "Practice details",
                "fields": [
                    {"key": "primary_specialty", "label": "Primary specialty", "type": "select",
                     "options": ["General Practitioner", "Pediatrician", "Cardiologist", "Dermatologist", "OB-GYN", "Psychiatrist", "Internal Medicine", "Endocrinologist", "Neurologist", "Other"]},
                    {"key": "sub_specialties", "label": "Sub-specialties", "type": "multiselect",
                     "options": ["Maternal medicine", "Sports medicine", "Geriatrics", "Adolescent medicine", "Sleep medicine", "Sexual health", "Tropical diseases"]},
                    {"key": "languages", "label": "Languages spoken", "type": "multiselect",
                     "options": ["English", "Yoruba", "Igbo", "Hausa", "Pidgin", "French"]},
                    {"key": "primary_affiliation", "label": "Current hospital / clinic", "type": "text"},
                    {"key": "other_affiliations", "label": "Other affiliations", "type": "textarea"},
                ],
            },
            {
                "key": "telemedicine",
                "title": "Telemedicine & availability",
                "fields": [
                    {"key": "modalities", "label": "Consultation modalities you offer", "type": "multiselect",
                     "options": ["Video", "Voice call", "Chat"]},
                    {"key": "days_available", "label": "Days available", "type": "multiselect",
                     "options": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                    {"key": "daily_start_hour", "label": "Daily start hour (0-23)", "type": "number", "min": 0, "max": 23},
                    {"key": "daily_end_hour", "label": "Daily end hour (0-23)", "type": "number", "min": 0, "max": 23},
                    {"key": "response_time_goal", "label": "Average response time goal", "type": "select",
                     "options": ["< 5 minutes", "< 15 minutes", "< 1 hour", "< 4 hours"]},
                ],
            },
            {
                "key": "attestations",
                "title": "Scope & attestations",
                "fields": [
                    {"key": "attest_scope", "label": "I attest I only practise within my scope of competence", "type": "bool"},
                    {"key": "attest_telemedicine", "label": "I have read and agree to Nigerian telemedicine guidelines", "type": "bool"},
                    {"key": "attest_conduct", "label": "I agree to the DocNow.NG code of conduct", "type": "bool"},
                    {"key": "attest_verification", "label": "I consent to background and license verification", "type": "bool"},
                ],
                "required_true": ["attest_scope", "attest_telemedicine", "attest_conduct", "attest_verification"],
            },
        ],
    },

    # ---------- DOCTOR POST-CONSULTATION — structured clinical summary ----------
    "doctor_post_consult": {
        "title": "Clinical summary",
        "subtitle": "Captured at consultation close — feeds the care plan and quality metrics.",
        "role": "doctor",
        "trigger": "consultation_complete",
        "version": 1,
        "sections": [
            {
                "key": "assessment",
                "title": "Assessment",
                "fields": [
                    {"key": "working_diagnosis", "label": "Working diagnosis", "type": "text"},
                    {"key": "icd10_codes", "label": "ICD-10 codes (comma-separated, optional)", "type": "text"},
                    {"key": "severity", "label": "Severity", "type": "select",
                     "options": ["Mild", "Moderate", "Severe"]},
                    {"key": "differential", "label": "Differential diagnoses", "type": "textarea"},
                ],
            },
            {
                "key": "plan",
                "title": "Plan",
                "fields": [
                    {"key": "referral_needed", "label": "Referral needed?", "type": "bool"},
                    {"key": "referral_specialty", "label": "Refer to (specialty)", "type": "select",
                     "options": ["Not required", "Cardiologist", "Pediatrician", "OB-GYN", "Psychiatrist", "Dermatologist", "Endocrinologist", "Neurologist", "General Surgery", "ENT", "Other"]},
                    {"key": "tests_ordered", "label": "Tests ordered", "type": "multiselect",
                     "options": ["FBC", "Malaria parasite", "Widal", "RBS / FBS", "Urinalysis", "Lipid profile", "Liver function", "Kidney function", "ECG", "Chest X-ray", "Ultrasound"]},
                    {"key": "follow_up_needed", "label": "Follow-up needed?", "type": "bool"},
                    {"key": "follow_up_days", "label": "Follow up in N days", "type": "number", "min": 0, "max": 365},
                    {"key": "patient_advice", "label": "Advice for the patient (will appear in care plan)", "type": "textarea"},
                ],
            },
            {
                "key": "quality",
                "title": "Quality signals",
                "fields": [
                    {"key": "triage_accuracy", "label": "How accurate was the AI triage? (1 poor – 5 excellent)", "type": "scale", "min": 1, "max": 5},
                    {"key": "diagnosis_confidence", "label": "Confidence in your working diagnosis (1–5)", "type": "scale", "min": 1, "max": 5},
                    {"key": "red_flags_during_consult", "label": "Red flags noticed during consult", "type": "multiselect",
                     "options": ["None", "Chest pain", "Breathing difficulty", "Sudden weakness", "Heavy bleeding", "Suicidal ideation", "Severe allergic reaction", "Other"]},
                ],
            },
        ],
    },

    # ---------- DOCTOR REFRESH — every 180 days ----------
    "doctor_refresh": {
        "title": "Doctor profile refresh",
        "subtitle": "Keeps your details current — 90 seconds.",
        "role": "doctor",
        "trigger": "every_180_days",
        "version": 1,
        "sections": [
            {
                "key": "practice_update",
                "title": "Practice update",
                "fields": [
                    {"key": "still_active", "label": "Still accepting consultations on DocNow.NG?", "type": "bool"},
                    {"key": "current_affiliation", "label": "Current hospital / clinic", "type": "text"},
                    {"key": "updated_fee", "label": "Updated consultation fee (NGN)", "type": "number", "min": 0},
                    {"key": "updated_days", "label": "Days available", "type": "multiselect",
                     "options": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                ],
            },
            {
                "key": "credentials_update",
                "title": "Credentials",
                "fields": [
                    {"key": "cme_credits_12mo", "label": "CME credits earned in last 12 months", "type": "number", "min": 0},
                    {"key": "new_certifications", "label": "New certifications / training", "type": "textarea"},
                    {"key": "scope_change", "label": "Any scope-of-practice change?", "type": "textarea"},
                ],
            },
        ],
    },
}


def list_for_role(role: str) -> list[str]:
    return [code for code, q in QUESTIONNAIRES.items() if q["role"] == role]


def get_schema(code: str) -> dict | None:
    return QUESTIONNAIRES.get(code)


async def get_last_response(user_id: str, code: str, context_id: str | None = None) -> dict | None:
    q = {"user_id": user_id, "code": code}
    if context_id:
        q["context_id"] = context_id
    return await db.questionnaire_responses.find_one(q, {"_id": 0}, sort=[("completed_at", -1)])


async def submit_response(user_id: str, code: str, responses: dict, context_id: str | None = None) -> dict:
    schema = QUESTIONNAIRES.get(code)
    if not schema:
        raise ValueError(f"Unknown questionnaire: {code}")
    # Flatten allowed keys
    allowed = set()
    required_true = []
    for sec in schema["sections"]:
        for f in sec["fields"]:
            allowed.add(f["key"])
        required_true.extend(sec.get("required_true", []))
    clean = {k: v for k, v in (responses or {}).items() if k in allowed}
    # Required attestations
    for k in required_true:
        if not clean.get(k):
            raise ValueError(f"Required attestation '{k}' was not accepted")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "code": code,
        "version": schema["version"],
        "context_id": context_id,
        "responses": clean,
        "started_at": now,
        "completed_at": now,
    }
    await db.questionnaire_responses.insert_one(doc)
    # Mirror selected fields onto the user document (for doctor onboarding & refresh that update profile)
    if code in ("doctor_onboarding", "doctor_refresh"):
        await db.users.update_one(
            {"id": user_id},
            {"$set": {**{f"qx_{code}.{k}": v for k, v in clean.items()},
                       f"qx_{code}_completed_at": now,
                       "updated_at": now}},
        )
    # Mirror selected fields onto patient profile + recompute derived signals
    if code == "patient_intake":
        from profile_service import apply_profile_update
        mirror_keys = {
            "lga", "home_address", "occupation", "marital_status",
            "next_of_kin_name", "next_of_kin_phone", "next_of_kin_relationship",
            "accessibility_needs", "preferred_consult_mode",
            "overall_health", "bp_status", "past_illnesses", "past_illnesses_other",
            "past_surgeries", "ever_hospitalized", "hospitalization_notes",
            "malaria_last_12mo", "sickness_frequency", "currently_treating",
            "bad_drug_reaction",
            "childhood_immunizations_complete", "yellow_fever", "hepatitis_b",
            "covid_doses", "last_tetanus_date",
            "smoking", "alcohol", "exercise_days_per_week", "sleep_hours_avg",
            "stress_level_baseline", "diet_style",
            "phq2_mood", "phq2_interest", "gad2_anxious", "gad2_worry",
            "sleep_quality_baseline", "wants_mental_support",
            "has_primary_doctor", "nearest_hospital_km", "usual_hospital_type",
            "delayed_treatment_cost", "insurance", "goals", "comms_channel",
            "wants_health_tips", "ai_triage_ok", "photo_upload_ok",
            "anonymous_data_ok",
            "family_conditions", "family_notes", "wants_dependent_profiles",
        }
        mirror = {k: v for k, v in clean.items() if k in mirror_keys}
        # Mirror health-tip opt-in to the canonical marketing flag used by the WA scheduler.
        if "wants_health_tips" in clean:
            mirror["whatsapp_marketing_opt_in"] = bool(clean["wants_health_tips"])
        # Merge past_illnesses into chronic_conditions (used by risk score & care segments)
        if isinstance(clean.get("past_illnesses"), list):
            cond_map = {
                "Hypertension": "Hypertension",
                "Diabetes": "Diabetes",
                "Asthma": "Asthma",
                "Sickle Cell Disease": "Sickle Cell",
                "HIV/AIDS": "HIV",
                "Tuberculosis": "Tuberculosis",
                "Heart Disease": "Heart Disease",
                "Kidney Disease": "Kidney Disease",
                "Epilepsy": "Epilepsy",
                "Cancer": "Cancer",
                "Mental Health Condition": "Mental Illness",
                "Hepatitis": "Hepatitis",
                "Ulcer": "Ulcer",
                "Arthritis": "Arthritis",
            }
            existing_user = await db.users.find_one({"id": user_id}, {"chronic_conditions": 1})
            existing = list((existing_user or {}).get("chronic_conditions") or [])
            for past in clean["past_illnesses"]:
                mapped = cond_map.get(past)
                if mapped and mapped not in existing:
                    existing.append(mapped)
            mirror["chronic_conditions"] = existing
        mirror[f"qx_{code}_completed_at"] = now
        await apply_profile_update(user_id, mirror, source="intake")
    doc.pop("_id", None)
    return doc


async def status_for_user(user: dict) -> list[dict]:
    """Return per-questionnaire status for the role: pending / completed."""
    role = user.get("role")
    out = []
    for code, schema in QUESTIONNAIRES.items():
        if schema["role"] != role:
            continue
        last = None
        if schema["trigger"] != "consultation_complete":
            # Non-context questionnaires: most recent submission
            last = await db.questionnaire_responses.find_one(
                {"user_id": user["id"], "code": code, "context_id": None},
                {"_id": 0},
                sort=[("completed_at", -1)],
            )
        # Refresh logic for periodic ones
        needs_refresh = False
        if schema["trigger"] == "every_180_days" and last:
            try:
                done = datetime.fromisoformat(last["completed_at"].replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - done).days >= 180:
                    needs_refresh = True
            except Exception:
                pass
        out.append({
            "code": code,
            "title": schema["title"],
            "subtitle": schema["subtitle"],
            "trigger": schema["trigger"],
            "version": schema["version"],
            "completed": bool(last) and not needs_refresh,
            "completed_at": last["completed_at"] if last else None,
            "needs_refresh": needs_refresh,
        })
    return out
