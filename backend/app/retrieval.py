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


_vector_store = None
_vector_store_failed = False


def _get_vector_store():
    """Lazily build a LangChain QdrantVectorStore over the scheme collection.

    Uses FastEmbedEmbeddings (same BAAI/bge-small-en-v1.5 model as embed_text)
    so query vectors are compatible with the indexed points. Returns None when
    langchain-qdrant / langchain-community or Qdrant is unavailable.
    """
    global _vector_store, _vector_store_failed
    if _vector_store is not None or _vector_store_failed:
        return _vector_store
    settings = get_settings()
    if get_qdrant_client() is None:
        _vector_store_failed = True
        return None
    try:
        from langchain_community.embeddings import FastEmbedEmbeddings
        from langchain_qdrant import QdrantVectorStore

        embeddings = FastEmbedEmbeddings(model_name=EMBED_MODEL)
        _vector_store = QdrantVectorStore.from_existing_collection(
            collection_name=settings.qdrant_collection,
            embedding=embeddings,
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            content_payload_key="page_content",
        )
    except Exception as exc:
        logger.warning(
            "LangChain vector store unavailable (%s); using direct Qdrant path",
            type(exc).__name__,
        )
        _vector_store_failed = True
    return _vector_store


def _retrieve_snippets_lc(query: str, filters: dict | None, limit: int) -> list[dict] | None:
    """LangChain retriever path. Returns None when the store is unavailable."""
    store = _get_vector_store()
    if store is None:
        return None
    docs = store.similarity_search_with_score(
        query,
        k=limit,
        filter=_build_filter(filters or {}),
    )
    snippets = []
    for doc, score in docs:
        meta = doc.metadata or {}
        snippets.append(
            {
                "slug": meta.get("slug"),
                "name": meta.get("name"),
                "chunk_type": meta.get("chunk_type"),
                "text": doc.page_content,
                "score": score,
                "official_url": meta.get("official_url"),
                "last_verified_date": meta.get("last_verified_date"),
            }
        )
    return snippets


def _retrieve_snippets_direct(query: str, filters: dict | None, limit: int) -> list[dict]:
    """Direct qdrant-client search (fallback / pre-LangChain payload shape)."""
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


def retrieve_snippets(query: str, filters: dict | None = None, limit: int = 5) -> list[dict]:
    """Return the top matching scheme chunks for query. Returns [] when Qdrant is unavailable.

    Primary path is the LangChain QdrantVectorStore retriever; falls back to a
    direct qdrant-client query on any failure.
    """
    try:
        snippets = _retrieve_snippets_lc(query, filters, limit)
        if snippets is not None:
            return snippets
    except Exception as exc:
        logger.warning("LangChain retrieval failed (%s); falling back", type(exc).__name__)
    return _retrieve_snippets_direct(query, filters, limit)
