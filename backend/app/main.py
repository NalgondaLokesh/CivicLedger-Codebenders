import asyncio

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import get_db, ping_db
from .admin import router as admin_router
from .auth import router as auth_router
from .eligibility import router as eligibility_router
from .groq_client import groq_status
from .models import Category, EducationLevel, Persona, SchemeLevel, SchemeListResponse
from .qdrant_client import qdrant_status
from .tracker import router as tracker_router

app = FastAPI(title="CivicLedger API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(eligibility_router)
app.include_router(tracker_router)


@app.get("/api/health")
async def health() -> dict:
    db_ok = await ping_db()
    qdrant = await asyncio.to_thread(qdrant_status)
    groq = groq_status()
    ok = db_ok and qdrant in ("up", "not_configured")
    return {
        "status": "ok" if ok else "degraded",
        "mongodb": "up" if db_ok else "down",
        "qdrant": qdrant,
        "groq": groq,
    }


@app.get("/api/schemes", response_model=SchemeListResponse)
async def list_schemes(
    education_level: EducationLevel | None = None,
    category: Category | None = None,
    persona: Persona | None = None,
    scheme_level: SchemeLevel | None = None,
    max_income: int | None = Query(default=None, ge=0, description="Max annual family income (INR)"),
) -> SchemeListResponse:
    query: dict = {"active": True}
    groups = []
    if persona is not None:
        # Match docs seeded with `persona`; fall back to legacy target_group.
        groups.append({"$or": [
            {"persona": persona.value},
            {"persona": {"$exists": False}, "target_group": persona.value},
        ]})
    if scheme_level is not None:
        if scheme_level == SchemeLevel.STATE:
            # Legacy docs predate scheme_level; treat missing as "state".
            groups.append({"$or": [
                {"scheme_level": SchemeLevel.STATE.value},
                {"scheme_level": {"$exists": False}},
            ]})
        else:
            query["scheme_level"] = scheme_level.value
    if education_level:
        # Schemes may cover several stages via `education_levels`.
        groups.append({"$or": [
            {"education_level": education_level.value},
            {"education_levels": education_level.value},
        ]})
    if category:
        groups.append({"$or": [{"category": category.value}, {"category": Category.ALL.value}]})
    if max_income is not None:
        # Schemes with no income cap always qualify; either cap field counts.
        groups.append({"$or": [
            {"max_income_limit": {"$gte": max_income}},
            {"max_annual_income_inr": {"$gte": max_income}},
            {"max_income_limit": None, "max_annual_income_inr": None},
        ]})
    if groups:
        query["$and"] = groups

    coll = get_db()["schemes"]
    cursor = coll.find(query).sort("name", 1)
    docs = await cursor.to_list(length=None)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return SchemeListResponse(items=docs, total=len(docs))
