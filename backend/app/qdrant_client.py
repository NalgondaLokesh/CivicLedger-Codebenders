from .config import get_settings

_client = None


def get_qdrant_client():
    """Lazily build a QdrantClient from settings. Returns None if QDRANT_URL is unset.

    The qdrant_client package is imported inside the function so the app still
    starts when the package is not installed.
    """
    global _client
    settings = get_settings()
    if not settings.qdrant_url:
        return None
    if _client is None:
        try:
            from qdrant_client import QdrantClient
        except ImportError:
            return None

        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=5,
        )
    return _client


def qdrant_status() -> str:
    """Return "up", "down", or "not_configured". Never raises."""
    try:
        client = get_qdrant_client()
        if client is None:
            return "not_configured"
        client.get_collections()
        return "up"
    except Exception:
        return "down"
