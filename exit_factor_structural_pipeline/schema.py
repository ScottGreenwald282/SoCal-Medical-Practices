"""Observed-event schema. Validation checks shape, not source truth."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ObservedEvent(str, Enum):
    OFFICER_ADDED = "OFFICER_ADDED"
    OFFICER_REMOVED = "OFFICER_REMOVED"
    OFFICER_ROLE_CHANGED = "OFFICER_ROLE_CHANGED"
    REGISTERED_AGENT_CHANGED = "REGISTERED_AGENT_CHANGED"
    MANAGEMENT_JOB_POSTED = "MANAGEMENT_JOB_POSTED"
    MANAGEMENT_APPOINTED = "MANAGEMENT_APPOINTED"


class EvidenceConfidence(str, Enum):
    OBSERVED_FILING_INDEX = "observed_filing_index"
    OBSERVED_DOCUMENT = "observed_document"
    OBSERVED_JOB_PAGE = "observed_job_page"
    UNKNOWN = "unknown"


class OwnerNeed(str, Enum):
    NOT_CONFIRMED = "not_confirmed"


class Interpretation(BaseModel):
    """Review triggers stay separate from verified intent."""

    ownership_transfer: bool = False
    family_relationship: str = "unknown"
    founder_age: str = "unknown"
    sale_readiness: str = "unknown"
    distress: str = "unknown"
    retirement: str = "unknown"
    owner_need: OwnerNeed = OwnerNeed.NOT_CONFIRMED
    is_first_management_role: bool = False
    business_relevance: str = "not_inferred"

    @field_validator("family_relationship", "founder_age", "sale_readiness", "distress", "retirement")
    @classmethod
    def unknown_only(cls, value: str) -> str:
        if value != "unknown":
            raise ValueError("intent and relationship fields stay unknown unless a source states them")
        return value

    @field_validator("ownership_transfer")
    @classmethod
    def no_ownership_inference(cls, value: bool) -> bool:
        if value:
            raise ValueError("officer or agent changes do not prove an ownership transfer")
        return value


class EntityRecord(BaseModel):
    entity_id: str
    legal_name: str
    dbas: str = ""
    status: str
    chapter: str = ""
    formation_date: str = ""
    formation_date_basis: str = "unknown"
    principal_city: str = ""
    principal_state: str = ""
    principal_zip: str = ""
    operating_county: str = ""
    county_basis: str = "unknown"
    registered_agent_name: str = ""
    trade_hint: str = ""
    trade_confirmed: str = "no"
    trade_source: str = ""
    domain: str = ""
    in_baseline: str = "no"
    cohort_pass: str = "no"
    cohort_fail_reasons: str = ""
    snapshot_sha256: str = ""
    source_url: str = "https://sos.iowa.gov/search/business/Search.aspx"

    @field_validator("entity_id")
    @classmethod
    def digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Iowa business number must be digits")
        return value


class FilingRecord(BaseModel):
    cert_no: str
    pages: str = ""
    filing_date: date | None = None
    effective_date: date | None = None
    filing_type: str

    @field_validator("cert_no")
    @classmethod
    def cert(cls, value: str) -> str:
        if not value or value.lower() == "unknown":
            raise ValueError("filing id is required")
        return value


class FilingChange(BaseModel):
    entity_id: str
    legal_name: str
    event: ObservedEvent
    filing_id: str
    filing_date: str
    effective_date: str = ""
    before_value: str = "unknown"
    after_value: str = "unknown"
    within_last_12_months: bool
    evidence_confidence: EvidenceConfidence
    evidence_note: str
    snapshot_sha256: str = ""
    interpretation: Interpretation = Field(default_factory=Interpretation)

    @field_validator("filing_date")
    @classmethod
    def date_required(cls, value: str) -> str:
        if not value or value == "unknown":
            raise ValueError("filing date is required")
        date.fromisoformat(value)
        return value

    @field_validator("event")
    @classmethod
    def observed(cls, value: ObservedEvent) -> ObservedEvent:
        if value not in ObservedEvent:
            raise ValueError("event must be an enumerated OBSERVED event")
        return value


class ManagementJob(BaseModel):
    entity_id: str
    legal_name: str
    event: ObservedEvent = ObservedEvent.MANAGEMENT_JOB_POSTED
    job_title: str
    job_url: str
    job_id: str = ""
    posting_date: str = ""
    location: str = ""
    status: str = ""
    company_on_posting: str
    exact_company_match: bool
    is_first_management_role: bool = False
    evidence_confidence: EvidenceConfidence = EvidenceConfidence.OBSERVED_JOB_PAGE
    evidence_note: str = ""

    @field_validator("job_url")
    @classmethod
    def url_required(cls, value: str) -> str:
        if not value.startswith("http"):
            raise ValueError("job URL is required")
        return value

    @field_validator("exact_company_match")
    @classmethod
    def must_match(cls, value: bool) -> bool:
        if not value:
            raise ValueError("management jobs require an exact company match")
        return value


class OwnerVerification(BaseModel):
    entity_id: str
    legal_name: str
    owner_name: str = ""
    owner_title: str = ""
    ownership_source_url: str = ""
    owner_verified: bool = False
    opener: str = ""
    claude_summarizer: str = "unavailable"

    @field_validator("opener")
    @classmethod
    def opener_only_when_verified(cls, value: str, info) -> str:
        verified = info.data.get("owner_verified")
        if value and not verified:
            raise ValueError("openers are drafted only after a current full-name owner is verified")
        if value and "sell" in value.lower():
            raise ValueError("opener must not infer a sale")
        return value
