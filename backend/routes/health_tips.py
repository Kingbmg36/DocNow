"""Health tips: AI-generated wellness suggestions."""
from fastapi import APIRouter, Depends
from auth_utils import get_current_user
from ai_service import generate_health_tips

router = APIRouter(prefix="/health-tips", tags=["health_tips"])


@router.get("")
async def get_tips(user: dict = Depends(get_current_user)):
    tips = await generate_health_tips()
    return {"tips": tips, "disclaimer": "These tips are general wellness suggestions and are not medical advice."}
