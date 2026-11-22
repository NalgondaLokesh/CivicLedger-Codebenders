from .config import get_settings

_client = None


def get_groq_client():
    """Lazily build a Groq client from settings. Returns None if GROQ_API_KEY is unset.

    The groq package is imported inside the function so the app still starts
    when the package is not installed.
    """
    global _client
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    if _client is None:
        try:
            from groq import Groq
        except ImportError:
            return None
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def groq_status() -> str:
    """Return "configured" or "not_configured". No network call."""
    return "configured" if get_settings().groq_api_key else "not_configured"
