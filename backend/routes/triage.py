"""AI Triage endpoint."""
from fastapi import APIRouter, Depends
from auth_utils import require_role
from models import TriageIn
from ai_service import run_triage
from unlock_service import maybe_unlock_from_triage

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("")
async def triage_endpoint(payload: TriageIn, user: dict = Depends(require_role("patient"))):
    result = await run_triage(payload.symptoms, payload.duration, payload.severity, payload.notes or "")
    # Gate 3 trigger: unlock contextual sections based on what was said
    await maybe_unlock_from_triage(user["id"], payload.symptoms, result)
    return result
