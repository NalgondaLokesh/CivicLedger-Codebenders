"""Pydantic models for CivicLedger.

Privacy guardrail: this schema intentionally has NO fields for Aadhaar
numbers, voter IDs, PATDAAR passbook numbers, PANs, or bank account numbers.
Eligibility is always indicative ("Likely Eligible"), never guaranteed.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Persona(str, Enum):
    TELANGANA_STUDENTS = "telangana_students"
    TELANGANA_FARMERS = "telangana_farmers"
    TELANGANA_WOMEN_ENTREPRENEURS = "telangana_women_entrepreneurs"


class EducationLevel(str, Enum):
    POST_MATRIC = "post_matric"
    PROFESSIONAL = "professional"
    OVERSEAS = "overseas"


class Category(str, Enum):
    SC = "sc"
    ST = "st"
    BC = "bc"
    EBC = "ebc"
    MINORITY = "minority"
    GENERAL = "general"
    ALL = "all"


class SchemeLevel(str, Enum):
    STATE = "state"
    CENTRAL = "central"


class RuleType(str, Enum):
    INCOME_LIMIT = "income_limit"
    INSTITUTION_TYPE = "institution_type"
    ATTENDANCE = "attendance"
    MERIT = "merit"
    RESIDENCY = "residency"
    OTHER = "other"


class SchemeRule(BaseModel):
    type: RuleType
    label: str
    value: str


class SchemeCreate(BaseModel):
    """Payload used by the seed script (and future admin tooling).

    `rules` is the human-readable display list; the typed match fields below
    (education_level, category/categories, income caps, age, gender, SHG,
    land) drive indicative eligibility evaluation. All are optional so each
    persona can carry only the attributes that apply.
    """

    slug: str
    name: str
    summary: str
    # "state" = Telangana state scheme, "central" = Government of India scheme.
    scheme_level: SchemeLevel = SchemeLevel.STATE
    persona: Persona = Persona.TELANGANA_STUDENTS
    target_group: str = "telangana_students"
    education_level: Optional[EducationLevel] = None
    # Schemes spanning multiple stages (e.g. fee reimbursement for both
    # post-matric and professional courses) list them here.
    education_levels: list[EducationLevel] = Field(default_factory=list)
    category: Category = Category.ALL
    # Multi-category schemes (e.g. Kalyana Lakshmi) list eligible categories here.
    categories: list[str] = Field(default_factory=list)
    rules: list[SchemeRule] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    application_steps: list[str] = Field(default_factory=list)
    rejection_pitfalls: list[str] = Field(default_factory=list)
    official_url: str
    last_verified_date: date
    max_income_limit: Optional[int] = None
    max_annual_income_inr: Optional[int] = None
    amount_or_benefit: Optional[str] = None
    # Persona-specific match attributes
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    gender: Optional[str] = None
    requires_shg_membership: bool = False
    requires_cultivable_land: bool = False
    active: bool = True


class Scheme(SchemeCreate):
    """Stored scheme document (adds server-side metadata)."""

    id: str = Field(alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "from_attributes": True}


class SchemeListResponse(BaseModel):
    items: list[Scheme]
    total: int
