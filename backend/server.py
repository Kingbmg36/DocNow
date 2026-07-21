"""DocNow.NG FastAPI server."""
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os
import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from db import db, create_indexes
from routes.auth import router as auth_router, seed_admin_and_demo
from routes.patients import router as patients_router
from routes.doctors import router as doctors_router
from routes.triage import router as triage_router
from routes.cases import router as cases_router
from routes.consultations import router as consultations_router
from routes.prescriptions import router as prescriptions_router
from routes.care_plans import router as care_plans_router
from routes.vitals import router as vitals_router
from routes.payments import router as payments_router
from routes.feedback import router as feedback_router
from routes.admin import router as admin_router
from routes.health_tips import router as tips_router
from routes.appointments import router as appointments_router
from routes.notifications import router as notifications_router
from routes.profile import router as profile_router
from routes.profile_sections import router as profile_sections_router
from routes.questionnaires import router as questionnaires_router
from routes.whatsapp import router as whatsapp_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="DocNow.NG API", version="1.0.0")

api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"name": "DocNow.NG", "status": "ok", "version": "1.0.0"}


@api.get("/health")
async def health():
    return {"status": "healthy"}


api.include_router(auth_router)
api.include_router(patients_router)
api.include_router(doctors_router)
api.include_router(triage_router)
api.include_router(cases_router)
api.include_router(consultations_router)
api.include_router(prescriptions_router)
api.include_router(care_plans_router)
api.include_router(vitals_router)
api.include_router(payments_router)
api.include_router(feedback_router)
api.include_router(admin_router)
api.include_router(tips_router)
api.include_router(appointments_router)
api.include_router(notifications_router)
api.include_router(profile_router)
api.include_router(profile_sections_router)
api.include_router(questionnaires_router)
api.include_router(whatsapp_router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Cookies still work cross-origin via samesite=lax
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await create_indexes()
    await seed_admin_and_demo()
    from whatsapp_scheduler import start_scheduler
    start_scheduler()
    logger.info("DocNow.NG startup complete")


@app.on_event("shutdown")
async def on_shutdown():
    from whatsapp_scheduler import stop_scheduler
    from whatsapp_service import shutdown_client
    from paystack_service import shutdown_client as shutdown_paystack
    from email_service import shutdown_client as shutdown_email
    from sms_service import shutdown_client as shutdown_sms
    stop_scheduler()
    await shutdown_client()
    await shutdown_paystack()
    await shutdown_email()
    await shutdown_sms()
    logger.info("DocNow.NG shutting down")
