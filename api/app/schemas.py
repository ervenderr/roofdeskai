import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMPTY_VALUES = {"", "null", "none", "unknown", "n/a"}


class ServiceType(str, Enum):
    repair = "repair"
    replacement = "replacement"
    inspection = "inspection"
    other = "other"


class LeadFields(BaseModel):
    """Fields the model may extract; also the update_lead schema (unknown fields rejected)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=30)
    email: str | None = Field(None, max_length=120)
    address: str | None = Field(None, max_length=200)
    service_type: ServiceType | None = None
    property_type: str | None = Field(None, max_length=50)
    is_owner: bool | None = None
    timeline_months: int | None = Field(None, ge=0, le=120)
    budget_range: str | None = Field(None, max_length=50)

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return None if isinstance(v, str) and v.strip().lower() in EMPTY_VALUES else v

    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        return v if v is not None and EMAIL_RE.match(v) else None  # invalid -> treated as not given

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v):
        return v if v is not None and 7 <= len(re.sub(r"\D", "", v)) <= 15 else None


class Turn(BaseModel):
    """What the LLM proposes each turn. The code decides what to do with it."""

    reply: str = Field("", max_length=1200)  # empty -> code asks for the next missing field
    extracted: LeadFields = Field(default_factory=LeadFields)
    is_question: bool = False
    not_ready: bool = False
    escalate_reason: Literal["angry", "legal", "safety", "human_request"] | None = None
