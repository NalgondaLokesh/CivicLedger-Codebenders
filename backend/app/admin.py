"""Admin endpoints for scheme management: upsert + Qdrant Cloud sync.

Guarded by ADMIN_API_KEY via the X-Admin-Key header:
  - 503 when ADMIN_API_KEY is not configured
  - 401 when the header is missing or wrong

Scheme payloads reuse SchemeCreate — no sensitive-ID fields, and every
scheme keeps official_url + last_verified_date. Eligibility stays indicative.
"""

import asyncio
import hmac
import logging
from datetime import date, datetime, time, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException

from .config import get_settings
from .db import get_db
from .models import SchemeCreate
from .sync_qdrant import sync_scheme_to_qdrant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_indexes_ready = False


def require_admin(
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API key is not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin key")


async def _ensure_slug_index() -> None:
    global _indexes_ready
    if not _indexes_ready:
        await get_db()["schemes"].create_index("slug", unique=True)
        _indexes_ready = True


def _scheme_doc(payload: SchemeCreate) -> dict[str, Any]:
    """JSON-safe scheme doc for Mongo. BSON has no date type, so
    last_verified_date is stored as midnight UTC (same as seed_schemes.py)."""
    doc = payload.model_dump(mode="json")
    # Preserve an existing education_levels list when the admin payload
    # doesn't carry one (the admin form doesn't edit it).
    if not payload.education_levels:
        doc.pop("education_levels", None)
    lv = doc.get("last_verified_date")
    if isinstance(lv, str):
        doc["last_verified_date"] = datetime.combine(date.fromisoformat(lv), time.min)
    doc["updated_at"] = datetime.now(timezone.utc)
    return doc


@router.get("/schemes", dependencies=[Depends(require_admin)])
async def list_all_schemes() -> dict[str, Any]:
    """All schemes including inactive ones (admin picker)."""
    docs = await get_db()["schemes"].find().sort("name", 1).to_list(length=None)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return {"items": docs, "total": len(docs)}


@router.post("/schemes", dependencies=[Depends(require_admin)])
async def upsert_scheme(payload: SchemeCreate) -> dict[str, Any]:
    """Upsert a scheme by slug, then sync its Qdrant chunks.

    The MongoDB write is authoritative: a Qdrant failure is reported in the
    response (`qdrant.status == "failed"`) but does not fail the request.
    """
    await _ensure_slug_index()
    coll = get_db()["schemes"]
    doc = _scheme_doc(payload)
    now = doc["updated_at"]

    await coll.update_one(
        {"slug": payload.slug},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    saved = await coll.find_one({"slug": payload.slug})
    if saved is None:
        raise HTTPException(status_code=500, detail="Scheme save failed")
    saved["_id"] = str(saved["_id"])

    try:
        qdrant = await asyncio.to_thread(sync_scheme_to_qdrant, saved)
    except Exception as exc:  # defensive: sync helper already never raises
        logger.warning("Qdrant sync raised for slug %s: %s", payload.slug, exc)
        qdrant = {"status": "failed", "chunks": 0, "message": str(exc)}

    return {"scheme": saved, "qdrant": qdrant}
