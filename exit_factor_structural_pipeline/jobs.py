"""Management-job lane. An opening is not a hire and not a first role by default."""

from __future__ import annotations

from exit_factor_structural_pipeline.match import is_explicit_first_role, is_management_title, names_match
from exit_factor_structural_pipeline.schema import EvidenceConfidence, ManagementJob, ObservedEvent


def job_from_posting(
    entity_id: str,
    legal_name: str,
    dbas: list[str],
    *,
    title: str,
    url: str,
    company: str,
    posting_date: str = "",
    location: str = "",
    status: str = "",
    job_id: str = "",
    page_text: str = "",
) -> ManagementJob | None:
    if not is_management_title(title):
        return None
    aliases = [legal_name, *dbas]
    if not any(names_match(company, alias) for alias in aliases if alias):
        return None
    if not url.startswith("http"):
        return None
    return ManagementJob(
        entity_id=entity_id,
        legal_name=legal_name,
        event=ObservedEvent.MANAGEMENT_JOB_POSTED,
        job_title=title.strip(),
        job_url=url,
        job_id=job_id,
        posting_date=posting_date,
        location=location,
        status=status or "unknown",
        company_on_posting=company,
        exact_company_match=True,
        is_first_management_role=is_explicit_first_role(f"{title}\n{page_text}"),
        evidence_confidence=EvidenceConfidence.OBSERVED_JOB_PAGE,
        evidence_note=(
            "Posting observed. An opening does not prove a hire. "
            "FIRST is set only when the page says newly created or first."
        ),
    )
