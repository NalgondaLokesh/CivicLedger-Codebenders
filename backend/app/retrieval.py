"""Qdrant retrieval helpers for scheme snippets.

Embeddings come from fastembed's BAAI/bge-small-en-v1.5 model (384-dim,
local ONNX — no API key). When fastembed is unavailable, a deterministic
hashing embedding is used as fallback so indexing/retrieval still agree.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re

from .config import get_settings
from .qdrant_client import get_qdrant_client

EMBED_DIM = 384
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
logger = logging.getLogger(__name__)

_embedder = None
_embedder_failed = False


def _get_embedder():
    """Lazily load the fastembed model. Returns None when unavailable."""
    global _embedder, _embedder_failed
    if _embedder is None and not _embedder_failed:
        try:
            from fastembed import TextEmbedding

            _embedder = TextEmbedding(model_name=EMBED_MODEL)
        except Exception as exc:
            logger.warning("fastembed unavailable (%s); using hashing fallback", type(exc).__name__)
            _embedder_failed = True
    return _embedder


def embed_text(text: str) -> list[float]:
    """Embedding vector for text. Real model when available, else hashing."""
    model = _get_embedder()
    if model is not None:
        try:
            vec = next(iter(model.embed([text or ""])))
            return [float(v) for v in vec]
        except Exception as exc:
            logger.warning("fastembed inference failed (%s); using hashing fallback", type(exc).__name__)
    return _hash_embed(text)


def _hash_embed(text: str) -> list[float]:
    """Deterministic, L2-normalized hashing embedding of fixed size EMBED_DIM."""
    vec = [0.0] * EMBED_DIM
    for token in _TOKEN_RE.findall((text or "").lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBED_DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        # Empty text: return a fixed unit vector so Qdrant never sees a zero vector.
        vec[0] = 1.0
        return vec
    return [v / norm for v in vec]


def _build_filter(filters: dict):
    """Build a qdrant Filter from optional keys. Returns None when no conditions apply."""
    from qdrant_client import models

    must = []
    for key in ("target_group", "education_level", "category"):
        value = filters.get(key)
        if value:
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))

    income = filters.get("max_income_limit")
    if income is not None:
        # Keep schemes with no income cap, or whose cap is >= the given value.
        must.append(
            models.Filter(
                should=[
                    models.IsEmptyCondition(is_empty=models.PayloadField(key="max_income_limit")),
                    models.FieldCondition(key="max_income_limit", range=models.Range(gte=income)),
                ]
            )
        )
    return models.Filter(must=must) if must else None


def retrieve_snippets(query: str, filters: dict | None = None, limit: int = 5) -> list[dict]:
    """Return the top matching scheme chunks for query. Returns [] when Qdrant is unavailable."""
    client = get_qdrant_client()
    if client is None:
        return []
    try:
        settings = get_settings()
        result = client.query_points(
            collection_name=settings.qdrant_collection,
            query=embed_text(query),
            query_filter=_build_filter(filters or {}),
            limit=limit,
            with_payload=True,
        )
        points = getattr(result, "points", result)
        snippets = []
        for point in points:
            payload = point.payload or {}
            snippets.append(
                {
                    "slug": payload.get("slug"),
                    "name": payload.get("name"),
                    "chunk_type": payload.get("chunk_type"),
                    "text": payload.get("text"),
                    "score": point.score,
                    "official_url": payload.get("official_url"),
                    "last_verified_date": payload.get("last_verified_date"),
                }
            )
        return snippets
    except Exception as exc:
        logger.warning("Qdrant retrieval failed: %s", exc)
        return []
