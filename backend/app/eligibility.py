"""Conversational eligibility check: PII masking, attribute extraction, rule matching.

Indicative only. Never stores or logs the raw user message, and never collects
identity numbers. Responses use "likely_eligible" / "needs_clarification" /
"not_likely" statuses only.
"""

import asyncio
import inspect
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import require_user, resolve_user_id
from .config import get_settings
from .db import get_db
from .llm import get_chat_model, groq_chat
from .retrieval import retrieve_snippets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eligibility", tags=["eligibility"])

MAX_TURNS = 2
MAX_MATCHES = 5
DISCLAIMER = "Indicative only, not a guarantee of eligibility. Confirm with the official portal."
MAX_STORED_MESSAGES = 40
REQUIRED_FIELDS = ("education_level", "category", "annual_income", "state")
PROFILE_KEYS = (
    "education_level", "category", "annual_income", "state", "needs_overseas",
    "age", "gender", "has_cultivable_land", "shg_member", "persona",
)
PERSONAS = {"telangana_students", "telangana_farmers", "telangana_women_entrepreneurs"}
EDUCATION_LEVELS = {"post_matric", "professional", "overseas"}
CATEGORIES = {"sc", "st", "bc", "ebc", "minority", "general"}
GENDERS = {"female", "male", "other"}
STATUS_ORDER = {"likely_eligible": 0, "needs_clarification": 1, "not_likely": 2}

TYPE_LABELS = {
    "income_limit": "Annual family income limit",
    "institution_type": "Institution type",
    "attendance": "Attendance requirement",
    "merit": "Merit criteria",
    "residency": "State residency",
    "other": "Other condition",
}

QUESTIONS = {
    "education_level": "Are you in intermediate or post-matric studies, a professional course, or planning to study abroad?",
    "category": "Which social category do you belong to: SC, ST, BC, EBC, minority, or general?",
    "annual_income": "What is your approximate annual family income in rupees?",
    "state": "Which state do you live in?",
    "age": "How old are you?",
}

PERSONA_REQUIRED = {
    "telangana_farmers": ("state", "age"),
    "telangana_women_entrepreneurs": ("state",),
}


def _required_fields(profile: dict[str, Any]) -> tuple[str, ...]:
    return PERSONA_REQUIRED.get(profile.get("persona"), REQUIRED_FIELDS)

GROQ_SYSTEM_PROMPT = (
    "You extract eligibility details for Telangana citizen schemes from a user's message. "
    "The platform covers three personas: telangana_students (scholarships), "
    "telangana_farmers (small/marginal farmers), telangana_women_entrepreneurs "
    "(women entrepreneurs and SHG members). "
    "Reply with a JSON object with exactly these keys: "
    "persona (one of telangana_students, telangana_farmers, telangana_women_entrepreneurs, or null), "
    "education_level (one of post_matric, professional, overseas, or null), "
    "category (one of sc, st, bc, ebc, minority, general, or null), "
    "annual_income (integer rupees per year, converting lakh to rupees where 1 lakh = 100000, or null), "
    "state (string or null), "
    "needs_overseas (true, false, or null), "
    "age (integer years old, or null), "
    "gender (one of female, male, other, or null), "
    "has_cultivable_land (true if the user owns/rents cultivable farmland, false if they say they do not, null if unstated), "
    "shg_member (true if the user belongs to a self-help group / SHG / SERP / MEPMA group, false if they say they do not, null if unstated). "
    "Use null when the message does not state a value. Do not guess. "
    "Never ask for or repeat identity numbers, passbook numbers, or account numbers."
)

AADHAAR_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
PAN_RE = re.compile(r"[A-Z]{5}\d{4}[A-Z]")
CATEGORY_RE = re.compile(r"\b(sc|st|bc|ebc|minority)\b", re.IGNORECASE)


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(max_length=1000)
    history: list[HistoryItem] = Field(default_factory=list, max_length=40)
    profile: dict[str, Any] = Field(default_factory=dict)
    turn_count: int = Field(default=0, ge=0)
    show_matches_now: bool = False


# ---------------------------------------------------------------- helpers

def _mask_pii(text: str) -> tuple[str, bool]:
    masked, n1 = AADHAAR_RE.subn("[masked]", text)
    masked, n2 = PAN_RE.subn("[masked]", masked)
    return masked, (n1 + n2) > 0


def _coerce_income(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    if isinstance(value, str):
        digits = re.sub(r"[,\s]", "", value)
        if digits.isdigit():
            return int(digits)
    return None


def _coerce_age(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        age = int(value)
        return age if 1 <= age <= 120 else None
    if isinstance(value, str):
        m = re.search(r"\d{1,3}", value)
        if m:
            age = int(m.group(0))
            return age if 1 <= age <= 120 else None
    return None


def _sanitize(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only well-typed, allowed values for the profile keys."""
    edu = raw.get("education_level")
    cat = raw.get("category")
    state = raw.get("state")
    needs = raw.get("needs_overseas")
    gender = raw.get("gender")
    persona = raw.get("persona")
    cat_norm = cat.strip().lower() if isinstance(cat, str) else None
    state_norm = state.strip() if isinstance(state, str) else None
    gender_norm = gender.strip().lower() if isinstance(gender, str) else None
    persona_norm = persona.strip().lower() if isinstance(persona, str) else None
    return {
        "education_level": edu if isinstance(edu, str) and edu in EDUCATION_LEVELS else None,
        "category": cat_norm if cat_norm in CATEGORIES else None,
        "annual_income": _coerce_income(raw.get("annual_income")),
        "state": state_norm or None,
        "needs_overseas": needs if isinstance(needs, bool) else None,
        "age": _coerce_age(raw.get("age")),
        "gender": gender_norm if gender_norm in GENDERS else None,
        "has_cultivable_land": raw.get("has_cultivable_land") if isinstance(raw.get("has_cultivable_land"), bool) else None,
        "shg_member": raw.get("shg_member") if isinstance(raw.get("shg_member"), bool) else None,
        "persona": persona_norm if persona_norm in PERSONAS else None,
    }


def _merge(profile: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile)
    for key in PROFILE_KEYS:
        if new.get(key) is not None:
            merged[key] = new[key]
    return merged


def _keyword_extract(text: str) -> dict[str, Any]:
    low = text.lower()
    found: dict[str, Any] = {}

    cat = CATEGORY_RE.search(text)
    if cat:
        found["category"] = cat.group(1).lower()
    if re.search(r"intermediate|post[\s-]?matric", low):
        found["education_level"] = "post_matric"
    if re.search(r"engineering|college|degree|professional", low):
        found["education_level"] = "professional"
    if re.search(r"abroad|overseas|master", low):
        found["education_level"] = "overseas"
        found["needs_overseas"] = True
    if re.search(r"hyderabad|warangal|karimnagar|telangana", low):
        found["state"] = "Telangana"

    lakh = re.search(r"(\d+(?:\.\d+)?)\s*lakhs?", low)
    if lakh:
        found["annual_income"] = int(float(lakh.group(1)) * 100000)
    else:
        income = re.search(r"income\D{0,30}?(\d[\d,]*)", low)
        if income:
            found["annual_income"] = int(income.group(1).replace(",", ""))

    # Persona hints
    if re.search(r"farmer|farming|agricultur|cultivat|\bacres?\b|\bpatta|kisan|rythu", low):
        found["persona"] = "telangana_farmers"
        found["has_cultivable_land"] = True
    elif re.search(r"\bshg\b|self[\s-]?help|serp|mepma|entrepreneur|business|mahila|women'?s|startup|enterprise", low):
        found["persona"] = "telangana_women_entrepreneurs"
        if re.search(r"\bshg\b|self[\s-]?help|serp|mepma", low):
            found["shg_member"] = True
    elif re.search(r"student|intermediate|post[\s-]?matric|engineering|college|degree|scholarship|abroad|overseas|course", low):
        found["persona"] = "telangana_students"

    # Demographics
    age = re.search(r"(?:age|aged)\D{0,10}?(\d{1,3})\b|\b(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|y/?o)\b", low)
    if age:
        found["age"] = int(age.group(1) or age.group(2))
    if re.search(r"\b(female|woman|women|girl)\b", low):
        found["gender"] = "female"
    elif re.search(r"\b(male|man|men|boy)\b", low):
        found["gender"] = "male"
    return found


async def _groq_extract(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Profile extraction via LangChain ChatGroq (JSON mode)."""
    content = await groq_chat(messages, temperature=0, json_mode=True)
    if not content:
        raise RuntimeError("LLM extraction unavailable")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("unexpected extraction output")
    return data


def _pretty(value: Any) -> str:
    return value.replace("_", " ") if isinstance(value, str) else str(value)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _evaluate(scheme: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    rules = [r for r in (scheme.get("rules") or []) if isinstance(r, dict)]

    def label_for(rule_type: str | None, fallback: str) -> str:
        if rule_type:
            for rule in rules:
                if rule.get("type") == rule_type and rule.get("label"):
                    return str(rule["label"])
        return fallback

    # Each check: (status, rule_type, label, reason)
    checks: list[tuple[str, str, str, str]] = []
    persona = scheme.get("persona") or "telangana_students"

    if persona == "telangana_students":
        # Education stage (a scheme may cover several levels via education_levels)
        scheme_levels = [str(x) for x in (scheme.get("education_levels") or [])]
        if not scheme_levels and scheme.get("education_level"):
            scheme_levels = [str(scheme["education_level"])]
        p_level = profile.get("education_level")
        edu_label = "Education stage"
        level_text = " or ".join(_pretty(x) for x in scheme_levels) if scheme_levels else "any"
        if p_level is None:
            checks.append(("unknown", "other", edu_label, "Tell us your education stage to check this."))
        elif p_level in scheme_levels:
            checks.append(("matched", "other", edu_label,
                           f"Your education stage ({_pretty(p_level)}) matches this scheme."))
        else:
            checks.append(("failed", "other", edu_label,
                           f"This scheme is for {level_text} students, not {_pretty(p_level)}."))

        # Social category (multi-category schemes use `categories`)
        scheme_cat = scheme.get("category")
        cats = [str(c).lower() for c in (scheme.get("categories") or [])]
        p_cat = profile.get("category")
        cat_label = "Social category"
        if cats:
            if p_cat is not None and p_cat in cats:
                checks.append(("matched", "other", cat_label,
                               f"Your category ({str(p_cat).upper()}) is covered by this scheme."))
            elif p_cat is None:
                checks.append(("unknown", "other", cat_label, "Tell us your social category to check this."))
            else:
                checks.append(("failed", "other", cat_label,
                               f"This scheme covers {'/'.join(c.upper() for c in cats)} applicants, not {str(p_cat).upper()}."))
        elif scheme_cat == "all" or (p_cat is not None and scheme_cat == p_cat):
            reason = ("This scheme is open to all categories."
                      if scheme_cat == "all" else f"Your category ({str(p_cat).upper()}) is covered by this scheme.")
            checks.append(("matched", "other", cat_label, reason))
        elif p_cat is None:
            checks.append(("unknown", "other", cat_label, "Tell us your social category to check this."))
        else:
            checks.append(("failed", "other", cat_label,
                           f"This scheme is for {str(scheme_cat).upper()} applicants, not {str(p_cat).upper()}."))

        # Gender requirement (e.g. girls-only scholarships like Pragati)
        scheme_gender = scheme.get("gender")
        if scheme_gender in ("female", "male", "other"):
            p_gender = profile.get("gender")
            if p_gender == scheme_gender:
                checks.append(("matched", "other", "Gender",
                               f"This scheme is for {scheme_gender} applicants."))
            elif p_gender in ("female", "male", "other"):
                checks.append(("failed", "other", "Gender",
                               f"This scheme is for {scheme_gender} applicants, not {p_gender}."))
            else:
                checks.append(("unknown", "other", "Gender",
                               "Tell us your gender to check this scheme."))

        income_limit = scheme.get("max_income_limit")
    else:
        # ---- Farmers & Women Entrepreneurs persona checks ----

        # Gender requirement (e.g. women-only schemes). An explicit male/other
        # answer fails even when the women-entrepreneurs persona was selected.
        if scheme.get("gender") == "female":
            p_gender = profile.get("gender")
            self_selected = profile.get("persona") == "telangana_women_entrepreneurs"
            if p_gender in ("male", "other"):
                checks.append(("failed", "other", "Gender",
                               "This scheme is for women applicants."))
            elif p_gender == "female" or self_selected:
                checks.append(("matched", "other", "Gender",
                               "You meet the women's eligibility for this scheme."))
            else:
                checks.append(("unknown", "other", "Gender",
                               "Tell us your gender to check this scheme."))

        # Age range
        min_age = scheme.get("min_age")
        max_age = scheme.get("max_age")
        if min_age is not None or max_age is not None:
            age = profile.get("age")
            lo = f"{min_age}+" if min_age is not None else "any age"
            hi = f"up to {max_age}" if max_age is not None else "any age"
            if age is None:
                checks.append(("unknown", "other", "Age",
                               f"Share your age to check the {lo} / {hi} requirement."))
            elif (min_age is None or age >= min_age) and (max_age is None or age <= max_age):
                checks.append(("matched", "other", "Age",
                               f"Your age ({age}) is within the required range."))
            else:
                checks.append(("failed", "other", "Age",
                               f"This scheme requires age {lo} / {hi}; you mentioned {age}."))

        # SHG membership
        if scheme.get("requires_shg_membership"):
            member = profile.get("shg_member")
            if member is True:
                checks.append(("matched", "other", "SHG membership",
                               "You are an SHG member, as this scheme requires."))
            elif member is False:
                checks.append(("failed", "other", "SHG membership",
                               "This scheme requires active SHG membership."))
            else:
                checks.append(("unknown", "other", "SHG membership",
                               "Tell us whether you belong to a self-help group (SHG)."))

        # Cultivable land
        if scheme.get("requires_cultivable_land"):
            land = profile.get("has_cultivable_land")
            if land is True:
                checks.append(("matched", "other", "Cultivable land",
                               "You have cultivable land, as this scheme requires."))
            elif land is False:
                checks.append(("failed", "other", "Cultivable land",
                               "This scheme requires cultivable land records."))
            else:
                checks.append(("unknown", "other", "Cultivable land",
                               "Tell us whether you own cultivable farmland."))

        # Eligible categories list (e.g. Kalyana Lakshmi)
        cats = [str(c).lower() for c in (scheme.get("categories") or [])]
        if cats:
            p_cat = profile.get("category")
            if p_cat is not None and p_cat in cats:
                checks.append(("matched", "other", "Social category",
                               f"Your category ({str(p_cat).upper()}) is covered by this scheme."))
            elif p_cat is None:
                checks.append(("unknown", "other", "Social category",
                               "Tell us your social category to check this."))
            else:
                checks.append(("failed", "other", "Social category",
                               f"This scheme covers {'/'.join(c.upper() for c in cats)} applicants, not {str(p_cat).upper()}."))

        income_limit = scheme.get("max_income_limit") or scheme.get("max_annual_income_inr")

    # Income (shared across personas)
    income = profile.get("annual_income")
    inc_label = label_for("income_limit", TYPE_LABELS["income_limit"])
    if income_limit is None:
        checks.append(("matched", "income_limit", inc_label, "This scheme has no income cap."))
    elif income is None:
        checks.append(("unknown", "income_limit", inc_label,
                       f"Share your annual family income to check the limit of INR {income_limit}."))
    elif income <= income_limit:
        checks.append(("matched", "income_limit", inc_label,
                       f"Your income (INR {income} a year) is within the limit of INR {income_limit}."))
    else:
        checks.append(("failed", "income_limit", inc_label,
                       f"Your income (INR {income} a year) is above the limit of INR {income_limit}."))

    # State (shared). Central schemes are open across India; state schemes
    # require Telangana residency.
    p_state = profile.get("state")
    state_label = label_for("residency", TYPE_LABELS["residency"])
    is_central = str(scheme.get("scheme_level") or "state") == "central"
    if is_central:
        if p_state:
            checks.append(("matched", "residency", state_label,
                           "Central scheme — open to residents across India."))
        else:
            checks.append(("unknown", "residency", state_label,
                           "Tell us your state to confirm residency."))
    elif p_state == "Telangana":
        checks.append(("matched", "residency", state_label, "You are in Telangana, as this scheme requires."))
    elif p_state is None:
        checks.append(("unknown", "residency", state_label, "Tell us your state to check residency."))
    else:
        checks.append(("failed", "residency", state_label, "This scheme is for Telangana residents."))

    # Overseas study (students only)
    if persona == "telangana_students":
        scheme_level = scheme.get("education_level")
        if scheme_level == "overseas":
            needs = profile.get("needs_overseas")
            ov_label = "Study abroad"
            if needs is True:
                checks.append(("matched", "other", ov_label, "You plan to study abroad, as this scheme requires."))
            elif needs is None:
                checks.append(("unknown", "other", ov_label, "Tell us whether you plan to study abroad."))
            else:
                checks.append(("failed", "other", ov_label, "This scheme is for students studying abroad."))

    statuses = [c[0] for c in checks]
    if "failed" in statuses:
        status = "not_likely"
    elif "unknown" in statuses:
        status = "needs_clarification"
    else:
        status = "likely_eligible"

    def entries(wanted: str) -> list[dict[str, str]]:
        return [{"label": c[2], "type": c[1], "reason": c[3]} for c in checks if c[0] == wanted]

    return {
        "slug": scheme.get("slug"),
        "name": scheme.get("name"),
        "status": status,
        "matched_rules": entries("matched"),
        "unknown_rules": entries("unknown"),
        "failed_rules": entries("failed"),
        "required_documents": list(scheme.get("required_documents") or []),
        "application_steps": list(scheme.get("application_steps") or []),
        "official_url": scheme.get("official_url"),
        "last_verified_date": _iso(scheme.get("last_verified_date")),
        "amount_or_benefit": scheme.get("amount_or_benefit"),
        "rejection_pitfalls": list(scheme.get("rejection_pitfalls") or []),
        "persona": persona,
    }


async def _load_active_schemes() -> list[dict[str, Any]]:
    try:
        db = get_db()
        return await db["schemes"].find({"active": True}).to_list(length=None)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Scheme data is temporarily unavailable") from exc


async def _retrieve_context(profile: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[str] = ["Telangana citizen scheme eligibility"]
    filters: dict[str, Any] = {}
    if profile.get("persona"):
        parts.append(_pretty(profile["persona"]))
        filters["target_group"] = profile["persona"]
    if profile.get("education_level"):
        parts.append(_pretty(profile["education_level"]))
        filters["education_level"] = profile["education_level"]
    if profile.get("category"):
        parts.append(f"{profile['category']} category")
        filters["category"] = profile["category"]
    if profile.get("annual_income") is not None:
        parts.append(f"income {profile['annual_income']}")
        filters["max_income_limit"] = profile["annual_income"]
    if profile.get("state"):
        parts.append(profile["state"])
    query = " ".join(parts)

    try:
        fn = retrieve_snippets
        if inspect.iscoroutinefunction(fn):
            snippets = await fn(query, filters=filters or None, limit=5)
        else:
            snippets = await asyncio.to_thread(fn, query, filters=filters or None, limit=5)
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for s in snippets or []:
        if not isinstance(s, dict):
            continue
        out.append({
            "slug": s.get("slug"),
            "chunk_type": s.get("chunk_type"),
            "text": s.get("text"),
            "official_url": s.get("official_url"),
            "last_verified_date": _iso(s.get("last_verified_date")),
        })
    return out


# ---------------------------------------------------------------- chat history
# Per-user persisted chat state. Only PII-masked content is ever stored.


async def _chat_collection() -> Any:
    coll = get_db()["chat_sessions"]
    await coll.create_index("user_id", unique=True)
    return coll


async def _save_chat_turn(user_id: str, user_text: str, assistant_text: str,
                          profile: dict[str, Any], turn_count: int) -> None:
    try:
        coll = await _chat_collection()
        doc = await coll.find_one({"user_id": user_id})
        messages = list((doc or {}).get("messages") or [])
        messages.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
        messages = messages[-MAX_STORED_MESSAGES:]
        await coll.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "messages": messages,
                    "profile": profile,
                    "turn_count": turn_count,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Chat history save failed: %s", type(exc).__name__)


@router.get("/history")
async def get_chat_history(user_id: str = Depends(require_user)) -> dict[str, Any]:
    doc = await (await _chat_collection()).find_one({"user_id": user_id})
    if doc is None:
        return {"messages": [], "profile": {}, "turn_count": 0}
    return {
        "messages": doc.get("messages") or [],
        "profile": doc.get("profile") or {},
        "turn_count": doc.get("turn_count") or 0,
    }


@router.delete("/history")
async def clear_chat_history(user_id: str = Depends(require_user)) -> dict[str, bool]:
    await (await _chat_collection()).delete_one({"user_id": user_id})
    return {"cleared": True}


# ---------------------------------------------------------------- Q&A mode
# Question-like messages are answered by Groq grounded in Qdrant-retrieved
# scheme chunks, instead of running the structured eligibility flow.

QUESTION_RE = re.compile(
    r"^(what|how|when|where|who|whom|whose|which|can|could|is|are|was|were|"
    r"does|do|did|should|shall|tell me|explain|show me|list|give me|any|"
    r"compare|comparison|difference|vs|versus|summari[sz]e|eligib|document|"
    r"fee|last date|deadline|benefit|amount|income limit|documents?)\b",
    re.IGNORECASE,
)

QA_SYSTEM_PROMPT = (
    "You are CivicLedger, an assistant for Telangana citizen schemes covering "
    "students, small farmers, and women entrepreneurs. Answer the user's "
    "question using ONLY the scheme context provided. Be concise and factual. "
    "Mention the scheme name and official portal when relevant. Results are "
    "indicative only — always suggest confirming on the official portal. "
    "If the context does not cover the question, say so honestly and suggest "
    "browsing the Scheme Explorer or the official portal. "
    "You may use simple markdown: **bold** for key terms, '- ' bullet lists, "
    "and pipe tables (| col | col |) when comparing options side by side. "
    "Use plain line breaks instead of HTML tags like <br>. "
    "Never ask for, repeat, or store Aadhaar, PAN, passbook, or account numbers."
)


def _looks_like_question(text: str) -> bool:
    t = text.strip()
    return t.endswith("?") or bool(QUESTION_RE.match(t))


# Pure greetings / meta questions — the whole message must match so that
# "hi, I'm a BC student…" still goes through eligibility extraction.
CHITCHAT_RE = re.compile(
    r"^\s*(hi+|hii+|hello+|hey+|yo|namaste|good\s+(morning|afternoon|evening|day)|"
    r"whats?\s*up|how\s+are\s+you|how'?s\s+it\s+going|thank(s|\s+you)(\s+so\s+much)?|"
    r"bye+|goodbye|see\s+you|what\s+is\s+(this|civicledger)|"
    r"what'?s\s+(this|the\s+site|the\s+app|civicledger)|"
    r"whats\s+(this|the\s+site|the\s+app)|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"how\s+does\s+(this|it|civicledger)\s+work|help|"
    # greeting followed by a meta question: "hello, what is this site?"
    r"(?:hi|hello|hey|yo|namaste|good\s+(?:morning|afternoon|evening|day))[\s,.!]+"
    r"(?:what\s+is\s+(?:this|civicledger)|what'?s\s+(?:this|the\s+site|the\s+app|civicledger)|"
    r"whats\s+(?:this|the\s+site|the\s+app)|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"how\s+does\s+(?:this|it|civicledger)\s+work|help))[\s!.?,]*$",
    re.IGNORECASE,
)

# Looser combo: a greeting followed anywhere by a meta question in a short
# message ("hello, what is this site about?"). Eligibility details in the
# same breath still go through extraction — there's no meta keyword then.
GREETING_PREFIX_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|namaste|good\s+(morning|afternoon|evening|day))\b",
    re.IGNORECASE,
)
META_QUESTION_RE = re.compile(
    r"(what\s+is|what'?s|whats|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"how\s+does\s+(this|it|civicledger)\s+work|about\s+(this|the\s+site|civicledger)|help)\b",
    re.IGNORECASE,
)


def _is_chitchat(text: str) -> bool:
    if CHITCHAT_RE.match(text):
        return True
    return (
        len(text) <= 120
        and bool(GREETING_PREFIX_RE.match(text))
        and bool(META_QUESTION_RE.search(text))
    )

CONVO_SYSTEM_PROMPT = (
    "You are CivicLedger, a friendly assistant that helps Telangana residents "
    "discover central and state government schemes for students, small farmers, "
    "and women entrepreneurs. Answer greetings and questions about what "
    "CivicLedger does in 1-3 short, warm sentences. Then invite the user to "
    "share their situation — education level, social category, family income, "
    "and state — for an indicative eligibility check. Eligibility results are "
    "indicative only, never guaranteed; suggest confirming on the official "
    "portal. Never ask for, repeat, or store Aadhaar, PAN, passbook, or "
    "account numbers."
)

CONVO_FALLBACK = (
    "Hi! I'm CivicLedger — I help Telangana students, farmers, and women "
    "entrepreneurs find government schemes they may qualify for. Tell me about "
    "your education, category, income and state, and I'll check which schemes "
    "you are likely eligible for (indicative only)."
)


async def _converse(message: str, history: list[dict[str, str]]) -> str:
    """Conversational reply for greetings/meta questions via ChatGroq."""
    messages = [{"role": "system", "content": CONVO_SYSTEM_PROMPT}]
    messages.extend(history[-4:])
    messages.append({"role": "user", "content": message})
    text = await groq_chat(messages, temperature=0.7)
    if text:
        return text
    logger.warning("ChatGroq chit-chat unavailable; using fallback")
    return CONVO_FALLBACK


def _qa_retrieval_query(question: str, history: list[dict[str, str]]) -> str:
    """Build a retrieval query that carries conversation context.

    Follow-ups like "what documents does it need?" are meaningless on their
    own — prepend the last couple of user turns so Qdrant fetches chunks for
    the scheme actually being discussed.
    """
    recent_user = [
        h.get("content", "")
        for h in history[-6:]
        if h.get("role") == "user" and h.get("content")
    ][-2:]
    parts = [question]
    for prev in recent_user:
        # Skip near-duplicates of the current question.
        if prev.strip().lower() != question.strip().lower():
            parts.insert(0, prev.strip()[:200])
    return " ".join(parts)[:800]


async def _retrieve_qa_context(
    question: str,
    profile: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve scheme chunks relevant to a free-form question."""
    filters: dict[str, Any] = {}
    if profile.get("persona"):
        filters["target_group"] = profile["persona"]
    query = _qa_retrieval_query(question, history or [])
    try:
        fn = retrieve_snippets
        if inspect.iscoroutinefunction(fn):
            snippets = await fn(query, filters=filters or None, limit=6)
        else:
            snippets = await asyncio.to_thread(fn, query, filters=filters or None, limit=6)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for s in snippets or []:
        if isinstance(s, dict):
            out.append({
                "slug": s.get("slug"),
                "name": s.get("name"),
                "chunk_type": s.get("chunk_type"),
                "text": s.get("text"),
                "official_url": s.get("official_url"),
                "last_verified_date": _iso(s.get("last_verified_date")),
            })
    return out


async def _answer_question(
    question: str,
    snippets: list[dict[str, Any]],
    history: list[dict[str, str]],
) -> tuple[str, str]:
    """Return (reply_text, mode). mode is 'groq' or 'fallback'."""
    context_parts = []
    for s in snippets:
        label = s.get("name") or s.get("slug") or "scheme"
        context_parts.append(f"- {label} [{s.get('chunk_type','')}]: {s.get('text','')}")
    context = "\n".join(context_parts) or "(no scheme context available)"

    messages = [{"role": "system", "content": QA_SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": f"Scheme context:\n{context}"})
    messages.extend(history[-4:])
    messages.append({"role": "user", "content": question})
    text = await groq_chat(messages, temperature=0.3)
    if text:
        return text, "groq"
    logger.warning("ChatGroq Q&A unavailable; using fallback")

    # Fallback: summarize retrieved chunks directly.
    if snippets:
        lines = ["Here's what the scheme documents say:"]
        seen = set()
        for s in snippets[:3]:
            name = s.get("name") or s.get("slug")
            if name in seen:
                continue
            seen.add(name)
            lines.append(f"• {name}: {str(s.get('text',''))[:220]}")
        lines.append("For full details, check the official portal link on each scheme card.")
        return "\n".join(lines), "fallback"
    return ("I couldn't find scheme documents covering that question. "
            "Try the Scheme Explorer, or rephrase using scheme names like "
            "Rythu Bharosa, ePASS, or Kalyana Lakshmi."), "fallback"


# ---------------------------------------------------------------- endpoint

@router.post("/chat")
async def eligibility_chat(
    req: ChatRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    # 1. PII masking first. The raw message is never stored or logged.
    masked_message, pii_msg = _mask_pii(req.message)
    masked_history: list[dict[str, str]] = []
    pii_warning = pii_msg
    for item in req.history:
        masked_content, found = _mask_pii(item.content)
        pii_warning = pii_warning or found
        masked_history.append({"role": item.role, "content": masked_content})

    # 1b. Conversational & Q&A modes: greetings/meta questions get a friendly
    # reply; questions are answered from retrieved scheme context — neither
    # touches the eligibility extraction/matching flow.
    is_chitchat = _is_chitchat(masked_message)
    if not req.show_matches_now and (is_chitchat or _looks_like_question(masked_message)):
        profile = _sanitize(req.profile)
        if is_chitchat:
            snippets = []
            reply = await _converse(masked_message, masked_history)
            mode = "chitchat"
        else:
            snippets = await _retrieve_qa_context(masked_message, profile, masked_history)
            reply, qmode = await _answer_question(masked_message, snippets, masked_history)
            mode = f"qa_{qmode}"

        uid = await resolve_user_id(authorization)
        if uid is not None:
            await _save_chat_turn(uid, masked_message, reply, profile, req.turn_count)

        return {
            "reply": reply,
            "is_answer": True,
            "extracted_traits": {},
            "missing_fields": [],
            "follow_up_questions": [],
            "needs_more_info": False,
            "turn_count": req.turn_count,
            "max_turns": MAX_TURNS,
            "pii_warning": pii_warning,
            "profile": profile,
            "matches": [],
            "context_snippets": snippets,
            "extraction_mode": mode,
            "disclaimer": DISCLAIMER,
        }

    # 2. Extraction: ChatGroq (JSON mode) when configured, keyword fallback otherwise.
    extraction_mode = "keyword"
    extracted: dict[str, Any] | None = None
    if get_chat_model() is not None:
        messages = [{"role": "system", "content": GROQ_SYSTEM_PROMPT}]
        messages.extend(masked_history[-6:])
        messages.append({"role": "user", "content": masked_message})
        try:
            extracted = _sanitize(await _groq_extract(messages))
            extraction_mode = "groq"
        except Exception as exc:
            logger.warning("LLM extraction unavailable (%s); using keyword fallback", type(exc).__name__)
            extracted = None
    if extracted is None:
        extracted = _sanitize(_keyword_extract(masked_message))

    # 3. Merge into profile: new non-null values override stored ones.
    profile = _merge(_sanitize(req.profile), extracted)

    # 4. Missing attributes and turn logic (persona-aware).
    required = _required_fields(profile)
    missing = [f for f in required if profile.get(f) is None]
    needs_more = bool(missing) and req.turn_count < MAX_TURNS and not req.show_matches_now
    follow_ups = [QUESTIONS[f] for f in missing[:2]] if needs_more else []
    do_match = not needs_more

    # 5. Matching and RAG context, only when matching is performed.
    matches: list[dict[str, Any]] = []
    snippets: list[dict[str, Any]] = []
    if do_match:
        schemes = await _load_active_schemes()
        # When the persona is known, only evaluate that persona's schemes —
        # cross-persona results would just be noise.
        p_persona = profile.get("persona")
        if p_persona:
            schemes = [
                s for s in schemes
                if (s.get("persona") or "telangana_students") == p_persona
            ]
        evaluated = [_evaluate(s, profile) for s in schemes if isinstance(s, dict)]
        evaluated.sort(key=lambda m: (STATUS_ORDER[m["status"]], m["name"] or ""))
        matches = evaluated[:MAX_MATCHES]
        snippets = await _retrieve_context(profile)

    # 6. Reply text.
    if needs_more:
        reply = "Thanks. To check your eligibility I need a few details. " + " ".join(follow_ups)
    elif matches:
        reply = (f"Based on what you shared, {len(matches)} scheme(s) may fit. "
                 "This is indicative only; confirm on the official portal.")
        if missing:
            reply += " Some details are still missing, so some results need clarification."
    else:
        reply = "I could not find schemes matching these details yet. Try adding your course, category, or income."

    # Persist the masked exchange for signed-in users (cross-device history).
    uid = await resolve_user_id(authorization)
    if uid is not None:
        await _save_chat_turn(uid, masked_message, reply, profile, req.turn_count + 1)

    return {
        "reply": reply,
        "is_answer": False,
        "extracted_traits": {k: extracted.get(k) for k in PROFILE_KEYS},
        "missing_fields": missing,
        "follow_up_questions": follow_ups,
        "needs_more_info": needs_more,
        "turn_count": req.turn_count + 1,
        "max_turns": MAX_TURNS,
        "pii_warning": pii_warning,
        "profile": profile,
        "matches": matches,
        "context_snippets": snippets,
        "extraction_mode": extraction_mode,
        "disclaimer": DISCLAIMER,
    }
