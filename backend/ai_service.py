"""AI Triage, Care Plans & Health Tips via the Anthropic Claude API.

Swapped off the Emergent Universal LLM key onto the official `anthropic` SDK so the
app runs on any host (Railway, etc.). Model is env-configurable (default
`claude-opus-4-8`); set ANTHROPIC_MODEL to trade cost/speed (e.g. `claude-sonnet-5`).

Only the LLM call in `_chat_json` changed — the three public functions
(`run_triage`, `generate_health_tips`, `generate_care_plan`) keep the same shape and
their deterministic fallbacks, so nothing downstream needs to change.
"""
import os
import json
import logging
from typing import Optional

from anthropic import AsyncAnthropic

log = logging.getLogger(__name__)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "2000"))

TRIAGE_SYSTEM_PROMPT = """You are an AI healthcare triage assistant for DocNow.NG, serving patients across Africa (starting with Nigeria).

Your job:
- Summarize symptoms in plain language
- Identify urgency level (one of: Emergency, High, Moderate, Low)
- Identify red flags (warning signs requiring urgent care)
- Suggest appropriate medical specialty
- Suggest next steps the patient can take while awaiting consultation
- Suggest 3-5 questions the doctor should ask the patient
- Always include a medical disclaimer

You MUST NOT:
- Provide definitive diagnosis
- Guarantee outcomes
- Replace a qualified doctor

Always include emergency guidance if Emergency or High urgency.
Focus especially on conditions common in Africa: malaria, typhoid, respiratory illnesses, hypertension, diabetes, gastroenteritis, sickle cell crises.

Respond ONLY in valid JSON with this exact schema:
{
  "summary": "<2-3 sentence plain-language symptom summary>",
  "urgency": "Emergency" | "High" | "Moderate" | "Low",
  "urgency_reasoning": "<1 sentence on why this urgency level>",
  "red_flags": ["<warning sign 1>", "<warning sign 2>"],
  "recommended_specialty": "<e.g. General Practitioner, Pediatrician, Cardiologist>",
  "next_steps": ["<step 1>", "<step 2>", "<step 3>"],
  "doctor_questions": ["<q1>", "<q2>", "<q3>"],
  "disclaimer": "This is not a medical diagnosis. Please consult a qualified healthcare professional. If this is an emergency, visit the nearest hospital immediately."
}
"""


TIPS_SYSTEM_PROMPT = """You are a wellness coach for DocNow.NG in Africa. Generate 5 short, practical health tips covering hydration, sleep, exercise, nutrition, and stress management. These are NOT medical advice.

Respond ONLY in valid JSON:
{
  "tips": [
    {"category": "Hydration|Sleep|Exercise|Nutrition|Stress", "title": "<short>", "body": "<1-2 sentences>"}
  ]
}
"""


CARE_PLAN_SYSTEM_PROMPT = """You are an AI assistant compiling a structured Care Plan for a DocNow.NG consultation. Given the doctor notes, prescription, and triage, produce a clear, patient-friendly Care Plan.

Respond ONLY in valid JSON:
{
  "consultation_summary": "<2-3 sentences>",
  "doctor_advice": "<plain language advice paragraph>",
  "warning_signs": ["<sign1>", "<sign2>", "<sign3>"],
  "recommended_tests": ["<test1>", "<test2>"],
  "follow_up": "<follow-up instructions, e.g. return in 7 days if no improvement>",
  "health_tips": ["<tip1>", "<tip2>", "<tip3>"]
}
"""


# Lazy client so the module imports even when ANTHROPIC_API_KEY isn't set —
# a missing key then surfaces via each function's try/except → deterministic fallback.
_client: Optional[AsyncAnthropic] = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


async def _chat_json(system: str, user_text: str) -> dict:
    """Call Claude and parse a JSON object out of the response.

    Thinking is left off (fast, patient-facing path); the prompts are explicit and
    these are structured-extraction tasks. Keeps the robust brace/fence extraction
    from the original so a stray preamble doesn't break parsing.
    """
    client = _get_client()
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    raw = next((b.text for b in resp.content if b.type == "text"), "")
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    txt = txt.strip()
    start = txt.find("{")
    end = txt.rfind("}")
    if start != -1 and end != -1:
        txt = txt[start:end + 1]
    return json.loads(txt)


async def run_triage(symptoms: str, duration: str, severity: str, notes: str = "") -> dict:
    prompt = f"""Patient information:
- Symptoms: {symptoms}
- Duration: {duration}
- Self-reported severity: {severity}
- Additional notes: {notes or 'none'}

Provide the triage JSON now."""
    try:
        result = await _chat_json(TRIAGE_SYSTEM_PROMPT, prompt)
        # Sanity defaults
        result.setdefault("disclaimer", "This is not a medical diagnosis. Please consult a qualified healthcare professional.")
        urgency = result.get("urgency", "Moderate")
        if urgency not in ("Emergency", "High", "Moderate", "Low"):
            result["urgency"] = "Moderate"
        return result
    except Exception as e:
        log.exception("Triage AI failed: %s", e)
        # Safe fallback
        return {
            "summary": f"Patient reports: {symptoms}. Duration: {duration}. Severity: {severity}.",
            "urgency": "Moderate",
            "urgency_reasoning": "Automated fallback — manual doctor review required.",
            "red_flags": ["Unable to auto-detect — defer to clinician"],
            "recommended_specialty": "General Practitioner",
            "next_steps": ["Stay hydrated", "Rest", "Avoid self-medication"],
            "doctor_questions": [
                "When did the symptoms start?",
                "Have you taken any medication?",
                "Any chronic conditions?",
            ],
            "disclaimer": "This is not a medical diagnosis. Please consult a qualified healthcare professional. If this is an emergency, visit the nearest hospital immediately.",
            "ai_unavailable": True,
        }


async def generate_health_tips() -> list[dict]:
    try:
        result = await _chat_json(TIPS_SYSTEM_PROMPT, "Generate today's tips.")
        return result.get("tips", [])
    except Exception as e:
        log.exception("Tips AI failed: %s", e)
        return [
            {"category": "Hydration", "title": "Drink water regularly", "body": "Aim for 8 cups of clean water daily, more in hot weather."},
            {"category": "Sleep", "title": "Prioritize 7-8 hours", "body": "Consistent sleep strengthens immunity and mood."},
            {"category": "Exercise", "title": "Move 30 minutes", "body": "A brisk walk daily improves cardiovascular health."},
            {"category": "Nutrition", "title": "Eat the rainbow", "body": "Include fresh fruits and vegetables at every meal."},
            {"category": "Stress", "title": "Breathe deeply", "body": "Try 5 minutes of slow breathing when overwhelmed."},
        ]


async def generate_care_plan(triage: dict, notes: str, prescription_items: list[dict]) -> dict:
    prompt = f"""Triage JSON: {json.dumps(triage)}
Doctor notes: {notes}
Prescription items: {json.dumps(prescription_items)}

Produce the Care Plan JSON now."""
    try:
        return await _chat_json(CARE_PLAN_SYSTEM_PROMPT, prompt)
    except Exception as e:
        log.exception("Care plan AI failed: %s", e)
        return {
            "consultation_summary": triage.get("summary", "Consultation completed."),
            "doctor_advice": notes or "Follow the prescription and rest well.",
            "warning_signs": triage.get("red_flags") or ["Worsening symptoms", "High fever", "Difficulty breathing"],
            "recommended_tests": [],
            "follow_up": "Return for a follow-up consultation in 7 days if symptoms persist or worsen.",
            "health_tips": ["Stay hydrated", "Get adequate rest", "Take medication as prescribed"],
        }
