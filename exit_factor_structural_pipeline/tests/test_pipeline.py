from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from exit_factor_structural_pipeline.baseline import load_blocked_names
from exit_factor_structural_pipeline.counties import county_for_principal_city
from exit_factor_structural_pipeline.events import (
    apply_agent_document,
    changes_from_index,
    diff_officer_snapshots,
)
from exit_factor_structural_pipeline.jobs import job_from_posting
from exit_factor_structural_pipeline.match import in_name_set, names_match, normalize_name
from exit_factor_structural_pipeline.parse_sos import (
    biennial_has_officer_fields,
    formation_from_filings,
    parse_agent_change,
    parse_filings,
    parse_officers,
    parse_result_span,
    parse_search_results,
    parse_summary,
)
from exit_factor_structural_pipeline.schema import Interpretation, OwnerVerification

FIXTURES = Path(__file__).parent / "fixtures"


def test_search_parser_reads_live_result_shape_and_span():
    text = (FIXTURES / "search_king.md").read_text()
    rows = parse_search_results(text)
    assert [row["entity_id"] for row in rows] == ["753682", "279417", "43210"]
    assert rows[1]["name_type"] == "Fictitious name"
    assert parse_result_span(text)["reported_total"] == 16
    assert parse_result_span(text)["shown_to"] == 3
    capped = parse_result_span("Results\u00a01 - 25 of 1000")
    assert capped["shown_to"] == 25
    assert capped["reported_total"] == 1000


def test_summary_uses_principal_office_city_not_as_county():
    summary = parse_summary((FIXTURES / "summary_753682.txt").read_text())
    assert summary["entity_id"] == "753682"
    assert summary["legal_name"] == "KING CONSTRUCTION AND HOME REPAIR LLC"
    assert summary["status"] == "Active"
    assert "LIMITED LIABILITY COMPANY" in summary["chapter"]
    assert summary["registered_agent_name"] == "ERIC ORION KING"
    assert summary["principal_city"] == "Ottumwa"
    county, basis = county_for_principal_city(summary["principal_city"])
    assert county == ""
    assert basis == "outside_or_unlisted"
    live_cells = """
Searched: 753682
Business No. |
Legal Name |
Status |
753682 |
KING CONSTRUCTION AND HOME REPAIR LLC |
Active |
Type |
State of Inc. |
Modified |
Legal |
IA |
No |
Chapter |
CODE 489 DOMESTIC LIMITED LIABILITY COMPANY |
Names (Viewing 1 of 1)
Type |
Status |
Modified |
Name |
Legal |
Inactive |
No |
OLD NAME |
Registered Agent or Reserving Party
Full Name |
ERIC ORION KING |
Principal Office
City, State, Zip |
OTTUMWA, IA, 52501 |
"""
    live = parse_summary(live_cells)
    assert live["status"] == "Active"
    assert live["legal_name"] == "KING CONSTRUCTION AND HOME REPAIR LLC"
    assert live["name_type"] == "Legal"
    assert "LIMITED LIABILITY COMPANY" in live["chapter"]


def test_formation_comes_from_organization_filing_not_later_biennial():
    filings = parse_filings((FIXTURES / "filings_753682.txt").read_text())
    assert [item.cert_no for item in filings] == [
        "FT0273065",
        "WA0104694",
        "FT0501651",
        "A25753682",
        "FT0501653",
    ]
    formed, basis = formation_from_filings(filings)
    assert formed == date(2023, 6, 15)
    assert "FT0273065" in basis
    biennial_only = [item for item in filings if "BIENNIAL" in item.filing_type]
    assert formation_from_filings(biennial_only) == (None, "unknown")


def test_officers_tab_none_on_file_is_not_a_diff():
    assert parse_officers((FIXTURES / "officers_none.txt").read_text()) == []
    assert diff_officer_snapshots(
        "753682",
        "EXAMPLE LLC",
        before=[],
        after=[],
        before_filing_id="",
        after_filing_id="",
        as_of=date(2026, 1, 28),
        snapshot_sha256="abc",
    ) == []


def test_filing_index_emits_agent_change_only_and_document_fills_names():
    filings = parse_filings((FIXTURES / "filings_753682.txt").read_text())
    changes = changes_from_index("753682", "EXAMPLE LLC", filings, "abc")
    assert [change.event.value for change in changes] == ["REGISTERED_AGENT_CHANGED"]
    assert changes[0].filing_id == "FT0501653"
    assert changes[0].before_value == "unknown"
    assert changes[0].within_last_12_months is True
    updated = apply_agent_document(changes[0], (FIXTURES / "agent_change.txt").read_text())
    assert updated.before_value == "TONYA THOMAS"
    assert updated.after_value == "Eric orion king"
    hashed = """
## Change of Registered Agent
**The current registered agent/office as indicated on the Secretary of State's records is**
### MICHAEL S VERVAECKE
Full Name
#### The name, street address and email address of the new registered agent is
LAIRD LAW PLC
Full Name
"""
    assert parse_agent_change(hashed) == ("MICHAEL S VERVAECKE", "LAIRD LAW PLC")
    commercial = """
The current registered agent/office as indicated on the Secretary of State's records is
LEGALINC CORPORATE SERVICES INC.
Full Name
The name, street address and email address of the new registered agent is
REPUBLIC REGISTERED AGENT LLC
Full Name
"""
    assert parse_agent_change(commercial) == (
        "LEGALINC CORPORATE SERVICES INC.",
        "REPUBLIC REGISTERED AGENT LLC",
    )
    numbered = """
Statement to change the registered agent
4. The name of the CURRENT registered AGENT as indicated on the Secretary of State's records is:
NATIONAL CORPORATE RESEARCH, LTD.
5. The name and email address of the NEW registered AGENT is:
COGENCY GLOBAL INC.
"""
    assert parse_agent_change(numbered) == (
        "NATIONAL CORPORATE RESEARCH, LTD.",
        "COGENCY GLOBAL INC.",
    )
    assert updated.interpretation.ownership_transfer is False
    assert updated.interpretation.family_relationship == "unknown"
    assert updated.interpretation.owner_need.value == "not_confirmed"


def test_biennial_sample_has_no_officer_roster():
    text = (FIXTURES / "biennial.txt").read_text()
    assert "Biennial Report" in text
    assert biennial_has_officer_fields(text) is False
    before, after = parse_agent_change(text)
    assert before == "unknown"
    assert after == "unknown"


def test_officer_snapshot_diff_emits_add_remove_and_role():
    changes = diff_officer_snapshots(
        "1",
        "EXAMPLE LLC",
        before=[
            {"name": "Ada Lowe", "role": "Manager"},
            {"name": "Ben Lowe", "role": "Member"},
        ],
        after=[
            {"name": "Ada Lowe", "role": "President"},
            {"name": "Cara Nguyen", "role": "Manager"},
        ],
        before_filing_id="A1",
        after_filing_id="A2",
        as_of=date(2026, 3, 1),
        snapshot_sha256="def",
    )
    events = {change.event.value: change for change in changes}
    assert set(events) == {"OFFICER_ADDED", "OFFICER_REMOVED", "OFFICER_ROLE_CHANGED"}
    assert events["OFFICER_ADDED"].after_value.startswith("Cara Nguyen")
    assert events["OFFICER_REMOVED"].before_value.startswith("Ben Lowe")
    assert "President" in events["OFFICER_ROLE_CHANGED"].after_value
    assert events["OFFICER_ROLE_CHANGED"].interpretation.family_relationship == "unknown"


def test_name_match_is_exact_and_skips_prior_companies():
    assert names_match("King Construction", "KING CONSTRUCTION, L.L.C.")
    assert not names_match("King Construction", "KING CONSTRUCTION AND HOME REPAIR LLC")
    blocked = load_blocked_names()
    assert in_name_set("King Construction LLC", blocked)
    assert not in_name_set("KING CONSTRUCTION AND HOME REPAIR LLC", blocked)
    assert not in_name_set("ACME CONSTRUCTION LLC", {normalize_name("CTI Ready Mix")})
    assert "CTI READY MIX" in blocked


def test_county_map_keeps_split_cities_unresolved():
    assert county_for_principal_city("Ankeny") == ("Polk", "unique_city")
    assert county_for_principal_city("Waukee") == ("Dallas", "unique_city")
    assert county_for_principal_city("Indianola") == ("Warren", "unique_city")
    assert county_for_principal_city("West Des Moines")[1] == "split_city_unresolved"
    assert county_for_principal_city("") == ("", "unknown")
    assert county_for_principal_city("DESMOINES") == ("Polk", "city_spelling_desmoines")


def test_job_requires_exact_company_and_explicit_first_role():
    matched = job_from_posting(
        "1",
        "Example Plumbing LLC",
        [],
        title="Operations Manager",
        url="https://example.com/jobs/12",
        company="Example Plumbing LLC",
        posting_date="2026-09-01",
        location="Ankeny, IA",
        status="open",
        job_id="12",
        page_text="We are hiring an operations manager.",
    )
    assert matched is not None
    assert matched.is_first_management_role is False
    first = job_from_posting(
        "1",
        "Example Plumbing LLC",
        [],
        title="General Manager",
        url="https://example.com/jobs/13",
        company="Example Plumbing, LLC",
        page_text="This is a newly created general manager role.",
    )
    assert first is not None and first.is_first_management_role is True
    assert job_from_posting(
        "1",
        "Example Plumbing LLC",
        [],
        title="General Manager",
        url="https://example.com/jobs/14",
        company="Other Plumbing LLC",
    ) is None


def test_schema_blocks_intent_and_unverified_openers():
    with pytest.raises(ValidationError):
        Interpretation(ownership_transfer=True)
    with pytest.raises(ValidationError):
        OwnerVerification(
            entity_id="1",
            legal_name="Example LLC",
            owner_verified=False,
            opener="Pat Example is the owner.",
        )
