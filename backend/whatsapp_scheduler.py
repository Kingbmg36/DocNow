"""Weekly WhatsApp health-tip broadcast for DocNow.NG.

A patient is eligible for tips when:
  - role == "patient"
  - status != "deleted"
  - phone is set (E.164)
  - whatsapp_marketing_opt_in is True (set during Gate-1 / patient_intake `wants_health_tips`)
  - has not already received a tip in the past 6 days (rolling, to ride out scheduler drift)

Tips come from `ai_service.generate_health_tips()` (already used by the in-app TipsView).
We pick one tip at random per patient so the cohort doesn't all get the same message.
"""
import os
import random
import secrets
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from db import db
from ai_service import generate_health_tips
from whatsapp_service import send_health_tip

log = logging.getLogger(__name__)

TIP_COOLDOWN_DAYS = 6


async def _eligible_patients() -> list[dict]:
    """Patients who opted in and haven't received a tip recently."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TIP_COOLDOWN_DAYS)).isoformat()
    recent_recipients = await db.whatsapp_messages.distinct(
        "patient_id",
        {"template_name": "docnow_health_tip_weekly", "created_at": {"$gte": cutoff}},
    )
    return await db.users.find({
        "role": "patient",
        "status": {"$ne": "deleted"},
        "phone": {"$exists": True, "$ne": None, "$ne": ""},
        "whatsapp_marketing_opt_in": True,
        "id": {"$nin": list(recent_recipients)},
    }, {"id": 1, "full_name": 1, "phone": 1}).to_list(5000)


async def send_weekly_tips(custom_tip: Optional[str] = None) -> dict:
    """Send one weekly health tip to every eligible patient.

    Args:
        custom_tip: If provided, send this exact text. Otherwise generate via AI.
    Returns counts: { eligible, sent, failed, tip_id }
    """
    patients = await _eligible_patients()
    log.info("Health-tip broadcast: %d eligible patients", len(patients))
    if not patients:
        return {"eligible": 0, "sent": 0, "failed": 0, "tip_id": None}

    # Generate a fresh tip pool (5 tips). One picked at random per patient.
    if custom_tip:
        tip_pool = [custom_tip.strip()]
    else:
        try:
            tip_pool = await generate_health_tips() or []
        except Exception as e:
            log.warning("Health-tip AI gen failed, using fallback: %s", e)
            tip_pool = [
                "Drink 6–8 glasses of water spaced through the day. Skip the sugar.",
                "Walk briskly for 20 minutes today — even pacing the room counts.",
                "Sleep is medicine. Aim for a consistent bedtime, +/- 30 min.",
            ]

    # Random-ish but deterministic seed per broadcast so it's reproducible in tests
    rng = random.Random(secrets.randbits(64))
    tip_id = uuid.uuid4().hex[:12]
    sent = failed = 0
    for p in patients:
        tip = rng.choice(tip_pool)
        try:
            await send_health_tip(
                p["phone"],
                patient_name=(p.get("full_name") or "there").split()[0],
                tip_body=tip,
                patient_id=p["id"],
                tip_id=tip_id,
            )
            sent += 1
        except Exception as e:
            log.exception("Health-tip send failed for %s: %s", p["id"], e)
            failed += 1

    # Audit row so admins can see broadcast history
    await db.whatsapp_broadcasts.insert_one({
        "id": tip_id,
        "kind": "health_tip_weekly",
        "eligible": len(patients),
        "sent": sent,
        "failed": failed,
        "tip_pool_size": len(tip_pool),
        "custom_tip": bool(custom_tip),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"eligible": len(patients), "sent": sent, "failed": failed, "tip_id": tip_id}


# ---------- Scheduler ----------
_scheduler = None


def start_scheduler() -> None:
    """Start the in-process scheduler. Idempotent (safe under uvicorn reload)."""
    global _scheduler
    if _scheduler is not None:
        return

    # Skip scheduler in dev unless explicitly enabled — avoids surprise sends from devs.
    if os.environ.get("WHATSAPP_SCHEDULER_ENABLED", "false").lower() != "true":
        log.info("WhatsApp scheduler disabled (WHATSAPP_SCHEDULER_ENABLED=false)")
        return

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = AsyncIOScheduler(timezone="Africa/Lagos")
    # Every Monday at 09:00 WAT (Lagos time)
    _scheduler.add_job(
        send_weekly_tips,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="whatsapp_weekly_health_tip",
        replace_existing=True,
        max_instances=1,
        coalesce=True,  # if missed, run once when service comes back
        misfire_grace_time=3600,
    )
    _scheduler.start()
    log.info("WhatsApp scheduler started (weekly health-tip job — Mon 09:00 Lagos)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
