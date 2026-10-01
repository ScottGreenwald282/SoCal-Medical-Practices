"""Build observed events. Filing titles are not officer diffs."""

from __future__ import annotations

from datetime import date

from exit_factor_structural_pipeline.parse_sos import iso_or_blank, parse_agent_change, within_window
from exit_factor_structural_pipeline.schema import (
    EvidenceConfidence,
    FilingChange,
    FilingRecord,
    Interpretation,
    ObservedEvent,
)

WINDOW_START = date(2025, 10, 1)
WINDOW_END = date(2026, 10, 1)


def _agent_change(filing_type: str) -> bool:
    text = filing_type.upper()
    return "REGISTERED" in text and "AGENT" in text and "CHANGE" in text


def changes_from_index(
    entity_id: str,
    legal_name: str,
    filings: list[FilingRecord],
    snapshot_sha256: str,
) -> list[FilingChange]:
    """A filing-index row can support REGISTERED_AGENT_CHANGED only.

    Officer added/removed/role events need two comparable officer snapshots.
    A biennial-report row is not an officer diff.
    """
    changes: list[FilingChange] = []
    for filing in filings:
        if filing.filing_date is None or not _agent_change(filing.filing_type):
            continue
        changes.append(
            FilingChange(
                entity_id=entity_id,
                legal_name=legal_name,
                event=ObservedEvent.REGISTERED_AGENT_CHANGED,
                filing_id=filing.cert_no,
                filing_date=iso_or_blank(filing.filing_date),
                effective_date=iso_or_blank(filing.effective_date),
                before_value="unknown",
                after_value="unknown",
                within_last_12_months=within_window(filing.filing_date, WINDOW_START, WINDOW_END),
                evidence_confidence=EvidenceConfidence.OBSERVED_FILING_INDEX,
                evidence_note=(
                    "Filing index lists this registered-agent change. "
                    "Before and after names are unknown until the document is read. "
                    "This is not an ownership transfer."
                ),
                snapshot_sha256=snapshot_sha256,
                interpretation=Interpretation(),
            )
        )
    return changes


def apply_agent_document(change: FilingChange, document_text: str) -> FilingChange:
    before, after = parse_agent_change(document_text)
    if before == "unknown" and after == "unknown":
        return change
    if before != "unknown" and after != "unknown":
        note = (
            "Change of Registered Agent document states the agent on file and the new agent. "
            "The signer and the agent are not recorded as owners."
        )
    else:
        note = (
            "Change of Registered Agent document named only one side. "
            "The missing side stays unknown. The named person or company is not recorded as an owner."
        )
    return change.model_copy(
        update={
            "before_value": before,
            "after_value": after,
            "evidence_confidence": EvidenceConfidence.OBSERVED_DOCUMENT,
            "evidence_note": note,
        }
    )


def diff_officer_snapshots(
    entity_id: str,
    legal_name: str,
    before: list[dict[str, str]],
    after: list[dict[str, str]],
    before_filing_id: str,
    after_filing_id: str,
    as_of: date,
    snapshot_sha256: str,
) -> list[FilingChange]:
    """Diff two explicit snapshots. A single current list returns nothing."""
    if not before_filing_id or not after_filing_id:
        return []
    before_map = {_key(row["name"]): row for row in before if row.get("name")}
    after_map = {_key(row["name"]): row for row in after if row.get("name")}
    changes: list[FilingChange] = []
    for key, row in after_map.items():
        if key not in before_map:
            changes.append(
                _officer_event(
                    entity_id,
                    legal_name,
                    ObservedEvent.OFFICER_ADDED,
                    after_filing_id,
                    as_of,
                    "unknown",
                    f"{row['name']} | {row.get('role') or 'unknown'}",
                    snapshot_sha256,
                )
            )
            continue
        old_role = (before_map[key].get("role") or "").strip().upper()
        new_role = (row.get("role") or "").strip().upper()
        if old_role and new_role and old_role != new_role:
            changes.append(
                _officer_event(
                    entity_id,
                    legal_name,
                    ObservedEvent.OFFICER_ROLE_CHANGED,
                    after_filing_id,
                    as_of,
                    f"{before_map[key]['name']} | {before_map[key].get('role')}",
                    f"{row['name']} | {row.get('role')}",
                    snapshot_sha256,
                )
            )
    for key, row in before_map.items():
        if key not in after_map:
            changes.append(
                _officer_event(
                    entity_id,
                    legal_name,
                    ObservedEvent.OFFICER_REMOVED,
                    after_filing_id,
                    as_of,
                    f"{row['name']} | {row.get('role') or 'unknown'}",
                    "unknown",
                    snapshot_sha256,
                )
            )
    return changes


def _key(name: str) -> str:
    return " ".join(name.upper().split())


def _officer_event(
    entity_id: str,
    legal_name: str,
    event: ObservedEvent,
    filing_id: str,
    as_of: date,
    before: str,
    after: str,
    snapshot_sha256: str,
) -> FilingChange:
    return FilingChange(
        entity_id=entity_id,
        legal_name=legal_name,
        event=event,
        filing_id=filing_id,
        filing_date=as_of.isoformat(),
        before_value=before,
        after_value=after,
        within_last_12_months=within_window(as_of, WINDOW_START, WINDOW_END),
        evidence_confidence=EvidenceConfidence.OBSERVED_DOCUMENT,
        evidence_note=(
            f"Compared officer snapshot {filing_id} with the prior snapshot. "
            "Same surname is not a family relationship. This is not an ownership transfer."
        ),
        snapshot_sha256=snapshot_sha256,
        interpretation=Interpretation(),
    )
