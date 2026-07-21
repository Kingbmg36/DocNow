"""Generic questionnaire endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from auth_utils import get_current_user
from questionnaire_service import (
    QUESTIONNAIRES, get_schema, status_for_user, submit_response, get_last_response,
)

router = APIRouter(prefix="/questionnaires", tags=["questionnaires"])


class SubmitIn(BaseModel):
    responses: dict
    context_id: Optional[str] = None


@router.get("/catalog")
async def catalog():
    """Public schema list (no auth)."""
    return {
        "questionnaires": [
            {"code": c, "title": q["title"], "subtitle": q["subtitle"],
             "role": q["role"], "trigger": q["trigger"], "version": q["version"]}
            for c, q in QUESTIONNAIRES.items()
        ]
    }


@router.get("/mine")
async def my_questionnaires(user: dict = Depends(get_current_user)):
    return {"items": await status_for_user(user)}


@router.get("/{code}")
async def get_questionnaire(code: str):
    schema = get_schema(code)
    if not schema:
        raise HTTPException(404, "Unknown questionnaire")
    return schema


@router.get("/{code}/response/me")
async def my_response(
    code: str,
    context_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    schema = get_schema(code)
    if not schema:
        raise HTTPException(404, "Unknown questionnaire")
    if schema["role"] != user["role"]:
        raise HTTPException(403, f"This questionnaire is for {schema['role']} only")
    resp = await get_last_response(user["id"], code, context_id)
    return resp or {}


@router.post("/{code}/submit")
async def submit(code: str, payload: SubmitIn, user: dict = Depends(get_current_user)):
    schema = get_schema(code)
    if not schema:
        raise HTTPException(404, "Unknown questionnaire")
    if schema["role"] != user["role"]:
        raise HTTPException(403, f"This questionnaire is for {schema['role']} only")
    try:
        doc = await submit_response(user["id"], code, payload.responses, payload.context_id)
        return doc
    except ValueError as e:
        raise HTTPException(400, str(e))
