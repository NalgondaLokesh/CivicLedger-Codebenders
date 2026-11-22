"""Sync active schemes from MongoDB `schemes` into the Qdrant collection.

Run from backend/:  python -m app.sync_qdrant

Each active scheme is split into chunks (summary, rules, documents, steps,
eligibility). Embeddings are deterministic 384-dim hashing vectors, L2-normalized
(see app.retrieval.embed_text; no model or extra dependency). Points get a
deterministic uuid5 id per (slug, chunk_type), and are written with upsert, so
reruns are idempotent.

Exit codes: 0 on success, 1 when QDRANT_URL or MONGODB_URI is not configured.
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import date, datetime

from .config import get_settings
from .retrieval import EMBED_DIM, embed_text

logger = logging.getLogger(__name__)

UPSERT_BATCH = 128


def _iso(value) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value in (None, ""):
        return None
    return str(value)


def build_chunks(scheme: dict) -> list[dict]:
    """Return [{chunk_type, text}] for one scheme, skipping empty chunks."""
    rules = scheme.get("rules") or []
    rule_parts = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        parts = [str(x) for x in (rule.get("label"), rule.get("value")) if x not in (None, "")]
        if parts:
            rule_parts.append(": ".join(parts))

    steps = scheme.get("application_steps") or []
    documents = scheme.get("required_documents") or []

    eligibility_parts = []
    if scheme.get("persona"):
        eligibility_parts.append(f"Persona: {scheme['persona']}")
    if scheme.get("education_level"):
        eligibility_parts.append(f"Education level: {scheme['education_level']}")
    if scheme.get("education_levels"):
        eligibility_parts.append(f"Education levels: {', '.join(str(x) for x in scheme['education_levels'])}")
    if scheme.get("category") and scheme.get("category") != "all":
        eligibility_parts.append(f"Category: {scheme['category']}")
    if scheme.get("categories"):
        eligibility_parts.append(f"Eligible categories: {', '.join(scheme['categories'])}")
    if scheme.get("gender"):
        eligibility_parts.append(f"Gender: {scheme['gender']}")
    if scheme.get("min_age") is not None or scheme.get("max_age") is not None:
        eligibility_parts.append(f"Age: {scheme.get('min_age') or 'any'}-{scheme.get('max_age') or 'any'}")
    if scheme.get("requires_shg_membership"):
        eligibility_parts.append("Requires active SHG membership")
    if scheme.get("requires_cultivable_land"):
        eligibility_parts.append("Requires cultivable land record")
    income_cap = scheme.get("max_income_limit") or scheme.get("max_annual_income_inr")
    if income_cap is not None:
        eligibility_parts.append(f"Maximum income limit: {income_cap}")

    name = str(scheme.get("name") or "")
    candidates = [
        ("summary", scheme.get("summary") or ""),
        ("rules", "; ".join(rule_parts)),
        ("documents", ", ".join(str(d) for d in documents)),
        ("steps", "; ".join(f"Step {i}: {s}" for i, s in enumerate(steps, 1))),
        ("eligibility", "; ".join(eligibility_parts)),
    ]
    # Prefix each chunk with the scheme name so vectors match name-based queries.
    return [
        {"chunk_type": ctype, "text": f"{name}. {text}" if name else text}
        for ctype, text in candidates
        if text.strip()
    ]


def _point_id(slug: str, chunk_type: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{slug}:{chunk_type}"))


def _base_payload(scheme: dict, slug: str) -> dict:
    return {
        "slug": slug,
        "name": scheme.get("name"),
        "scheme_level": scheme.get("scheme_level") or "state",
        "persona": scheme.get("persona") or scheme.get("target_group"),
        "target_group": scheme.get("target_group") or scheme.get("persona"),
        "official_url": scheme.get("official_url"),
        "last_verified_date": _iso(scheme.get("last_verified_date")),
        "max_income_limit": scheme.get("max_income_limit"),
        "education_level": scheme.get("education_level"),
        "category": scheme.get("category"),
    }


def _chunk_payload(scheme: dict, slug: str, chunk: dict) -> dict:
    """Payload compatible with both the direct Qdrant filter path and
    LangChain's QdrantVectorStore (page_content + metadata keys)."""
    flat = {
        **_base_payload(scheme, slug),
        "chunk_type": chunk["chunk_type"],
        "text": chunk["text"],
    }
    metadata = {k: v for k, v in flat.items() if k != "text"}
    return {
        **flat,
        "page_content": chunk["text"],
        "metadata": metadata,
    }


def _delete_slug_points(client, collection: str, slug: str) -> int:
    """Delete all points for a slug (paginated scroll + delete by id)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = Filter(must=[FieldCondition(key="slug", match=MatchValue(value=slug))])
    ids = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=flt,
            limit=256,
            offset=offset,
            with_payload=False,
        )
        ids.extend(p.id for p in points)
        if offset is None:
            break
    if ids:
        client.delete(collection_name=collection, points_selector=ids, wait=True)
    return len(ids)


def sync_scheme_to_qdrant(scheme: dict) -> dict:
    """Idempotently upsert one scheme's chunks into Qdrant Cloud.

    Returns {"status": "synced" | "skipped_unconfigured" | "failed", ...}.
    Never raises — callers can report the status without failing the request.
    """
    settings = get_settings()
    if not settings.qdrant_url:
        return {"status": "skipped_unconfigured", "chunks": 0,
                "message": "QDRANT_URL is not configured"}

    slug = scheme.get("slug") or str(scheme.get("_id") or "")
    if not slug:
        return {"status": "failed", "chunks": 0, "message": "Scheme has no slug"}

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
    except ImportError as exc:
        return {"status": "failed", "chunks": 0,
                "message": f"qdrant_client package unavailable: {exc}"}

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )
    collection = settings.qdrant_collection
    try:
        if not client.collection_exists(collection_name=collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )

        # Qdrant Cloud requires a keyword index for the slug delete filter.
        try:
            from qdrant_client.models import KeywordIndexParams, KeywordIndexType

            client.create_payload_index(
                collection_name=collection,
                field_name="slug",
                field_schema=KeywordIndexParams(type=KeywordIndexType.KEYWORD),
            )
        except Exception:
            pass  # index already exists

        removed = _delete_slug_points(client, collection, slug)

        if scheme.get("active") is False:
            return {"status": "synced", "chunks": 0, "removed": removed,
                    "message": f"Scheme inactive; removed {removed} chunk(s) from the index"}

        points = []
        for chunk in build_chunks(scheme):
            points.append(
                PointStruct(
                    id=_point_id(slug, chunk["chunk_type"]),
                    vector=embed_text(chunk["text"]),
                    payload=_chunk_payload(scheme, slug, chunk),
                )
            )
        for start in range(0, len(points), UPSERT_BATCH):
            client.upsert(
                collection_name=collection,
                points=points[start : start + UPSERT_BATCH],
                wait=True,
            )
        return {"status": "synced", "chunks": len(points), "removed": removed,
                "message": f"Upserted {len(points)} chunk(s) for '{slug}'"}
    except Exception as exc:
        logger.warning("Qdrant sync failed for slug %s: %s", slug, exc)
        return {"status": "failed", "chunks": 0, "message": str(exc)}


def main() -> int:
    settings = get_settings()
    if not settings.qdrant_url:
        print("QDRANT_URL is not configured in backend/.env; nothing synced.")
        return 1
    if not settings.mongodb_uri:
        print("MONGODB_URI is not configured in backend/.env; nothing synced.")
        return 1

    from pymongo import MongoClient
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        IntegerIndexParams,
        IntegerIndexType,
        KeywordIndexParams,
        KeywordIndexType,
        PointStruct,
        VectorParams,
    )

    mongo = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
    try:
        schemes = list(mongo[settings.mongodb_db_name]["schemes"].find({"active": True}))
    finally:
        mongo.close()

    points = []
    for scheme in schemes:
        slug = scheme.get("slug") or str(scheme.get("_id"))
        for chunk in build_chunks(scheme):
            points.append(
                PointStruct(
                    id=_point_id(slug, chunk["chunk_type"]),
                    vector=embed_text(chunk["text"]),
                    payload=_chunk_payload(scheme, slug, chunk),
                )
            )

    qdrant = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )
    collection = settings.qdrant_collection
    if not qdrant.collection_exists(collection_name=collection):
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"Created Qdrant collection '{collection}'.")

    # Qdrant Cloud requires payload indexes for filtered keys. Keyword indexes
    # cover exact-match string filters; integer covers the income range filter.
    for key in ("slug", "target_group", "persona", "education_level", "category"):
        try:
            qdrant.create_payload_index(
                collection_name=collection,
                field_name=key,
                field_schema=KeywordIndexParams(type=KeywordIndexType.KEYWORD),
            )
        except Exception:
            pass  # index already exists
    try:
        qdrant.create_payload_index(
            collection_name=collection,
            field_name="max_income_limit",
            field_schema=IntegerIndexParams(type=IntegerIndexType.INTEGER, range=True),
        )
    except Exception:
        pass

    upserted = 0
    for start in range(0, len(points), UPSERT_BATCH):
        batch = points[start : start + UPSERT_BATCH]
        qdrant.upsert(collection_name=collection, points=batch, wait=True)
        upserted += len(batch)

    print(f"Schemes: {len(schemes)}")
    print(f"Chunks: {len(points)}")
    print(f"Upserted: {upserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
