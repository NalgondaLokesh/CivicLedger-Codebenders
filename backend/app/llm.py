"""LangChain-powered Groq chat model wrapper.

All LLM calls in the eligibility flow go through ChatGroq (LangChain) so
prompts, retries, and provider swaps stay in one place. Falls back to None
when langchain-groq or GROQ_API_KEY is unavailable — callers keep their own
keyword/deterministic fallbacks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import get_settings
from .groq_client import groq_status

logger = logging.getLogger(__name__)

_model = None
_model_failed = False


def get_chat_model() -> Any | None:
    """Lazily build a LangChain ChatGroq model. None when unconfigured."""
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    settings = get_settings()
    if not settings.groq_api_key:
        _model_failed = True
        return None
    try:
        from langchain_groq import ChatGroq

        _model = ChatGroq(
            model=settings.groq_model,
            groq_api_key=settings.groq_api_key,
            temperature=0.4,
        )
    except Exception as exc:
        logger.warning("ChatGroq unavailable (%s)", type(exc).__name__)
        _model_failed = True
    return _model


def llm_status() -> str:
    """Return 'configured' / 'not_configured' / 'unavailable'."""
    if groq_status() != "configured":
        return "not_configured"
    return "configured" if get_chat_model() is not None else "unavailable"


async def groq_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    json_mode: bool = False,
) -> str | None:
    """Invoke ChatGroq with a role/content message list. Returns text or None.

    Never raises — callers decide their own fallback behaviour.
    """
    model = get_chat_model()
    if model is None:
        return None
    try:
        runnable = model
        if temperature is not None or json_mode:
            kwargs: dict[str, Any] = {}
            if temperature is not None:
                kwargs["temperature"] = temperature
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            runnable = model.bind(**kwargs)
        # invoke() is sync — run it off the event loop.
        resp = await asyncio.to_thread(runnable.invoke, messages)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):  # multi-modal content blocks
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        text = str(content or "").strip()
        return text or None
    except Exception as exc:
        logger.warning("ChatGroq invoke failed (%s)", type(exc).__name__)
        return None
