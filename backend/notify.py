"""In-app notification helper."""
import uuid
from datetime import datetime, timezone
from db import db


async def notify(user_id: str, type_: str, title: str, body: str = "", link: str = "", meta: dict | None = None):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": type_,  # appointment.booked | appointment.starting | consultation.completed | prescription.issued
        "title": title,
        "body": body,
        "link": link,
        "meta": meta or {},
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one(doc)
    doc.pop("_id", None)
    return doc
