"""Bounded live pilot. Coverage is the pages actually opened, not all Iowa entities."""

from __future__ import annotations

import csv
import json
import time
from datetime import date
from pathlib import Path

from exit_factor_structural_pipeline.baseline import load_blocked_names
from exit_factor_structural_pipeline.counties import county_for_principal_city
from exit_factor_structural_pipeline.events import apply_agent_document, changes_from_index
from exit_factor_structural_pipeline.feasibility import write_feasibility
from exit_factor_structural_pipeline.firecrawl_client import (
    SEARCH_URL,
    BudgetExhausted,
    FirecrawlClient,
    document_actions,
    entity_actions,
    markdown_of,
    name_search_actions,
)
from exit_factor_structural_pipeline.match import in_name_set
from exit_factor_structural_pipeline.opener import CLAUDE_STATUS
from exit_factor_structural_pipeline.parse_sos import (
    biennial_has_officer_fields,
    formation_from_filings,
    html_to_text,
    iso_or_blank,
    parse_filings,
    parse_officers,
    parse_result_span,
    parse_search_results,
    parse_summary,
    sha256_text,
)
from exit_factor_structural_pipeline.schema import EntityRecord, FilingChange

ROOT = Path(__file__).resolve().parent
RESEARCH_DATE = "2026-10-01"
PREFIXES = (
    "PLUMBING",
    "ROOFING",
    "CONCRETE",
    "EXCAVAT",
    "HEATING",
    "WELDING",
    "PAVING",
    "MECHANICAL",
    "ELECTRIC",
    "INSULATION",
    "DRYWALL",
    "MASONRY",
)
FORMATION_MIN = 1985
FORMATION_MAX = 2005
BIENNIAL_SAMPLE_CAP = 2
AGENT_DOCUMENT_CAP = 8

ENTITY_FIELDS = list(EntityRecord.model_fields)
CHANGE_FIELDS = [
    "entity_id",
    "legal_name",
    "event",
    "filing_id",
    "filing_date",
    "effective_date",
    "before_value",
    "after_value",
    "within_last_12_months",
    "evidence_confidence",
    "evidence_note",
    "snapshot_sha256",
    "ownership_transfer",
    "family_relationship",
    "founder_age",
    "sale_readiness",
    "owner_need",
    "is_first_management_role",
]
JOB_FIELDS = [
    "entity_id",
    "legal_name",
    "event",
    "job_title",
    "job_url",
    "job_id",
    "posting_date",
    "location",
    "status",
    "company_on_posting",
    "exact_company_match",
    "is_first_management_role",
    "evidence_confidence",
    "evidence_note",
]
INTERSECTION_FIELDS = CHANGE_FIELDS + [
    "job_url",
    "job_title",
    "owner_name",
    "owner_verified",
    "opener",
    "claude_summarizer",
    "accepted_new_company",
]
REVIEW_FIELDS = [
    "entity_id",
    "legal_name",
    "lane",
    "event",
    "filing_id",
    "filing_date",
    "within_last_12_months",
    "job_url",
    "cohort_pass",
    "note",
]
REJECT_FIELDS = ["entity_id", "legal_name", "stage", "reasons", "detail"]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _tabs(result: dict) -> dict[str, str]:
    data = (result.get("body") or {}).get("data") or {}
    scrapes = (data.get("actions") or {}).get("scrapes") or []
    found: dict[str, str] = {}
    for scrape in scrapes:
        url = scrape.get("url") or ""
        html = scrape.get("html") or ""
        text = html_to_text(html) if html else (scrape.get("markdown") or "")
        if "filings.aspx" in url:
            found["filings"] = text
        elif "officers.aspx" in url:
            found["officers"] = text
        elif "summary.aspx" in url:
            found["summary"] = text
    if "summary" not in found:
        found["summary"] = markdown_of(result)
    return found


def _candidate(row: dict) -> bool:
    if row.get("status", "").lower() != "active":
        return False
    if row.get("name_type", "").lower() != "legal":
        return False
    legal = (row.get("legal_name") or "").upper()
    return "LLC" in legal or "L.L.C" in legal


def _structural_reasons(record: dict) -> list[str]:
    reasons: list[str] = []
    if record["status"].lower() != "active":
        reasons.append("status_not_active")
    chapter = record["chapter"].upper()
    if "LIMITED LIABILITY COMPANY" not in chapter:
        reasons.append("chapter_not_confirmed_llc")
    if not record["formation_date"]:
        reasons.append("formation_date_unknown")
    else:
        year = int(record["formation_date"][:4])
        if year < FORMATION_MIN or year > FORMATION_MAX:
            reasons.append(f"formation_year_{year}_outside_1985_2005")
    if record["operating_county"] not in {"Polk", "Dallas", "Warren"}:
        reasons.append("operating_county_" + (record["county_basis"] or "unknown"))
    if record["in_baseline"] == "yes":
        reasons.append("previously_delivered")
    return reasons


def _flatten_change(change: FilingChange) -> dict:
    data = change.model_dump()
    interp = data.pop("interpretation")
    data["event"] = data["event"].value if hasattr(data["event"], "value") else data["event"]
    data["evidence_confidence"] = (
        data["evidence_confidence"].value
        if hasattr(data["evidence_confidence"], "value")
        else data["evidence_confidence"]
    )
    data["within_last_12_months"] = "yes" if data["within_last_12_months"] else "no"
    data.update(interp)
    data["ownership_transfer"] = "no"
    data["owner_need"] = "not_confirmed"
    data["is_first_management_role"] = "no"
    return data


class Pilot:
    def __init__(self, out_dir: Path | None = None, max_details: int = 50) -> None:
        self.out = out_dir or ROOT
        self.cache = self.out / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.max_details = max_details
        self.client = FirecrawlClient(self.cache / "snapshots")
        self.blocked = load_blocked_names()
        self.checkpoint_path = self.cache / "checkpoint.json"
        self.state_path = self.cache / "state.json"
        self.checkpoint = {"detailed": [], "prefixes_done": []}
        if self.checkpoint_path.exists():
            self.checkpoint = json.loads(self.checkpoint_path.read_text())
        self.entities: list[dict] = []
        self.changes: list[FilingChange] = []
        self.rejected: list[dict] = []
        self.stats = {
            "sos_prefix_search": self._blank_stats(),
            "sos_entity": self._blank_stats(),
            "sos_document": self._blank_stats(),
            "management_jobs": self._blank_stats(),
            "owner_verification": self._blank_stats(),
        }
        self.notes: list[str] = []
        self.biennial_samples = 0
        self.biennial_with_officers = 0
        self.agent_docs = 0
        self.coverage_pages: list[dict] = []
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text())
        self.entities = payload.get("entities") or []
        self.changes = [FilingChange.model_validate(row) for row in payload.get("changes") or []]
        self.rejected = payload.get("rejected") or []
        self.notes = payload.get("notes") or []
        self.coverage_pages = payload.get("coverage_pages") or []
        self.biennial_samples = payload.get("biennial_samples") or 0
        self.biennial_with_officers = payload.get("biennial_with_officers") or 0
        self.agent_docs = payload.get("agent_docs") or 0
        saved_stats = payload.get("stats") or {}
        for key, value in saved_stats.items():
            if key in self.stats:
                self.stats[key].update(value)

    def _save_state(self) -> None:
        payload = {
            "entities": self.entities,
            "changes": [change.model_dump(mode="json") for change in self.changes],
            "rejected": self.rejected,
            "notes": self.notes,
            "coverage_pages": self.coverage_pages,
            "biennial_samples": self.biennial_samples,
            "biennial_with_officers": self.biennial_with_officers,
            "agent_docs": self.agent_docs,
            "stats": self.stats,
        }
        self.state_path.write_text(json.dumps(payload))
        self._save_checkpoint()

    @staticmethod
    def _blank_stats() -> dict:
        return {
            "attempted": 0,
            "fetched": 0,
            "parsed": 0,
            "matched": 0,
            "event_positive": 0,
            "owner_verified": 0,
            "intersected": 0,
            "seconds": 0.0,
        }

    def _save_checkpoint(self) -> None:
        self.checkpoint_path.write_text(json.dumps(self.checkpoint))

    def _call(self, actions: list[dict], stat_key: str) -> dict | None:
        started = time.time()
        self.stats[stat_key]["attempted"] += 1
        last: dict | None = None
        for _ in range(2):
            try:
                last = self.client.scrape(SEARCH_URL, actions=actions)
            except BudgetExhausted as exc:
                self.notes.append(str(exc))
                self.stats[stat_key]["seconds"] += time.time() - started
                return None
            if last.get("ok"):
                self.stats[stat_key]["fetched"] += 1
                break
            time.sleep(1.5)
        self.stats[stat_key]["seconds"] += time.time() - started
        return last

    def _repair_saved_entities(self) -> None:
        """Re-read cached summary text so a parser fix does not require a refetch."""
        changed = False
        for record in self.entities:
            path = self.cache / "snapshots" / f"entity_{record['entity_id']}.txt"
            if not path.exists():
                continue
            summary = parse_summary(path.read_text(encoding="utf-8", errors="replace"))
            if summary.get("status"):
                record["status"] = summary["status"]
                changed = True
            if summary.get("legal_name"):
                record["legal_name"] = summary["legal_name"]
            if summary.get("chapter"):
                record["chapter"] = summary["chapter"]
            if summary.get("principal_city"):
                record["principal_city"] = summary["principal_city"]
                record["principal_state"] = summary.get("principal_state") or ""
                record["principal_zip"] = summary.get("principal_zip") or ""
                county, basis = county_for_principal_city(record["principal_city"])
                record["operating_county"] = county
                record["county_basis"] = basis
            if summary.get("registered_agent_name"):
                record["registered_agent_name"] = summary["registered_agent_name"]
            record["in_baseline"] = "yes" if in_name_set(record["legal_name"], self.blocked) else "no"
            reasons = _structural_reasons(record)
            reasons.append("trade_not_confirmed_from_non_sos_source")
            record["cohort_fail_reasons"] = ";".join(reasons)
            record["cohort_pass"] = "no"
            EntityRecord.model_validate(record)
            for rejected in self.rejected:
                if rejected.get("entity_id") == record["entity_id"] and rejected.get("stage") == "cohort":
                    rejected["legal_name"] = record["legal_name"]
                    rejected["reasons"] = record["cohort_fail_reasons"]
                    old_detail = rejected.get("detail") or ""
                    extra = ""
                    if "officers_current=" in old_detail:
                        extra = "; " + old_detail[old_detail.find("officers_current=") :]
                    rejected["detail"] = (
                        f"city={record['principal_city']}; county_basis={record['county_basis']}; "
                        f"formation={record['formation_date'] or 'unknown'}{extra}"
                    )
        if changed:
            self._save_state()

    def _repair_agent_docs(self) -> None:
        repaired: list[FilingChange] = []
        for change in self.changes:
            path = self.cache / "snapshots" / f"doc_{change.entity_id}_{change.filing_id}.txt"
            if path.exists():
                repaired.append(
                    apply_agent_document(change, path.read_text(encoding="utf-8", errors="replace"))
                )
            else:
                repaired.append(change)
        self.changes = repaired

    def search_prefix(self, prefix: str) -> list[dict]:
        if prefix in self.checkpoint["prefixes_done"]:
            cached = self.cache / f"prefix_{prefix}.json"
            spans = self.checkpoint.get("prefix_spans") or {}
            if prefix in spans and not any(page.get("prefix") == prefix for page in self.coverage_pages):
                self.coverage_pages.append({"prefix": prefix, **spans[prefix]})
            if cached.exists():
                return json.loads(cached.read_text())
        result = self._call(name_search_actions(prefix), "sos_prefix_search")
        text = markdown_of(result or {})
        if "Results" not in text and "Business No" not in text:
            self.notes.append(f"prefix {prefix} did not return a results table")
            self.rejected.append(
                {
                    "entity_id": "",
                    "legal_name": prefix,
                    "stage": "prefix_search",
                    "reasons": "no_results_table",
                    "detail": "The name-prefix search did not render a results table.",
                }
            )
            return []
        rows = parse_search_results(text)
        span = parse_result_span(text)
        self.coverage_pages.append({"prefix": prefix, **span, "parsed_rows": len(rows)})
        self.stats["sos_prefix_search"]["parsed"] += len(rows)
        if span.get("reported_total") and span.get("shown_to") and span["reported_total"] > span["shown_to"]:
            self.notes.append(
                f"prefix {prefix} showed {span['shown_from']}-{span['shown_to']} of {span['reported_total']}. "
                "Later pages were not opened. This is not all matching entities."
            )
        (self.cache / f"prefix_{prefix}.json").write_text(json.dumps(rows))
        self.checkpoint["prefixes_done"].append(prefix)
        self.checkpoint.setdefault("prefix_spans", {})[prefix] = {
            "shown_from": span.get("shown_from"),
            "shown_to": span.get("shown_to"),
            "reported_total": span.get("reported_total"),
            "parsed_rows": len(rows),
        }
        self._save_state()
        for row in rows:
            if not _candidate(row):
                self.rejected.append(
                    {
                        "entity_id": row["entity_id"],
                        "legal_name": row["legal_name"],
                        "stage": "search_result",
                        "reasons": "not_active_legal_llc_on_search_row",
                        "detail": f"status={row['status']}; type={row['name_type']}; prefix={prefix}",
                    }
                )
        return rows

    def detail(self, business_no: str, legal_hint: str) -> None:
        if business_no in self.checkpoint["detailed"]:
            return
        result = self._call(entity_actions(business_no), "sos_entity")
        if not result or not result.get("ok"):
            self.rejected.append(
                {
                    "entity_id": business_no,
                    "legal_name": legal_hint,
                    "stage": "entity_fetch",
                    "reasons": "fetch_failed",
                    "detail": (result or {}).get("error") or (result or {}).get("detail") or "no response",
                }
            )
            return
        tabs = _tabs(result)
        summary_text = tabs.get("summary") or ""
        filings_text = tabs.get("filings") or ""
        officers_text = tabs.get("officers") or ""
        blob = summary_text + "\n" + filings_text + "\n" + officers_text
        digest = sha256_text(blob)
        (self.cache / "snapshots" / f"entity_{business_no}.txt").write_text(blob)
        summary = parse_summary(summary_text)
        filings = parse_filings(filings_text)
        officers = parse_officers(officers_text)
        if not summary.get("entity_id"):
            summary["entity_id"] = business_no
        self.stats["sos_entity"]["parsed"] += 1
        formed, basis = formation_from_filings(filings)
        county, county_basis = county_for_principal_city(summary.get("principal_city") or "")
        legal_name = summary.get("legal_name") or legal_hint
        record = {
            "entity_id": summary["entity_id"],
            "legal_name": legal_name,
            "dbas": "",
            "status": summary.get("status") or "",
            "chapter": summary.get("chapter") or "",
            "formation_date": iso_or_blank(formed),
            "formation_date_basis": basis,
            "principal_city": summary.get("principal_city") or "",
            "principal_state": summary.get("principal_state") or "",
            "principal_zip": summary.get("principal_zip") or "",
            "operating_county": county,
            "county_basis": county_basis,
            "registered_agent_name": summary.get("registered_agent_name") or "",
            "trade_hint": "",
            "trade_confirmed": "no",
            "trade_source": "",
            "domain": "",
            "in_baseline": "yes" if in_name_set(legal_name, self.blocked) else "no",
            "cohort_pass": "no",
            "cohort_fail_reasons": "",
            "snapshot_sha256": digest,
            "source_url": SEARCH_URL,
        }
        reasons = _structural_reasons(record)
        if not filings_text:
            reasons.append("filings_tab_not_parsed")
        if "officers" not in tabs:
            reasons.append("officers_tab_not_parsed")
        reasons.append("trade_not_confirmed_from_non_sos_source")
        record["cohort_fail_reasons"] = ";".join(reasons)
        record["cohort_pass"] = "no"
        validated = EntityRecord.model_validate(record)
        self.entities.append(validated.model_dump())
        self.stats["sos_entity"]["matched"] += 1
        changes = changes_from_index(record["entity_id"], legal_name, filings, digest)
        if changes:
            self.stats["sos_entity"]["event_positive"] += 1
        self.changes.extend(changes)
        self.rejected.append(
            {
                "entity_id": record["entity_id"],
                "legal_name": legal_name,
                "stage": "cohort",
                "reasons": record["cohort_fail_reasons"],
                "detail": (
                    f"city={record['principal_city']}; county_basis={county_basis}; "
                    f"formation={record['formation_date'] or 'unknown'}; "
                    f"officers_current={len(officers)}; filings={len(filings)}; "
                    f"agent_city_not_used={summary.get('agent_city') or ''}"
                ),
            }
        )
        self._maybe_documents(record, filings, filings_text)
        self.checkpoint["detailed"].append(business_no)
        self._save_state()

    def _maybe_documents(self, record: dict, filings, filings_text: str) -> None:
        biennials = [item for item in filings if "BIENNIAL REPORT" in item.filing_type.upper() and item.filing_date]
        biennials.sort(key=lambda item: item.filing_date, reverse=True)
        if self.biennial_samples < BIENNIAL_SAMPLE_CAP and biennials:
            self._read_document(record, biennials[0].cert_no, "biennial")
        if self.biennial_samples >= BIENNIAL_SAMPLE_CAP and self.biennial_with_officers == 0:
            note = (
                "Stopped further biennial document downloads. "
                f"{self.biennial_samples} sampled LLC biennial reports had no officer, manager, or member roster."
            )
            if note not in self.notes:
                self.notes.append(note)
        agent_filings = [
            item
            for item in filings
            if "REGISTERED" in item.filing_type.upper() and "AGENT" in item.filing_type.upper()
        ]
        for filing in agent_filings:
            if self.agent_docs >= AGENT_DOCUMENT_CAP:
                break
            if filing.filing_date is None:
                continue
            self._read_document(record, filing.cert_no, "agent")

    def _read_document(self, record: dict, cert_no: str, kind: str) -> None:
        result = self._call(document_actions(record["entity_id"], cert_no), "sos_document")
        text = markdown_of(result or {})
        if not text:
            self.notes.append(f"document {cert_no} for {record['entity_id']} returned no text")
            return
        self.stats["sos_document"]["parsed"] += 1
        (self.cache / "snapshots" / f"doc_{record['entity_id']}_{cert_no}.txt").write_text(text)
        if kind == "biennial":
            self.biennial_samples += 1
            if biennial_has_officer_fields(text):
                self.biennial_with_officers += 1
            else:
                self.notes.append(
                    f"Biennial {cert_no} for {record['entity_id']} has no officer, manager, or member roster."
                )
            return
        self.agent_docs += 1
        updated: list[FilingChange] = []
        for change in self.changes:
            if change.entity_id == record["entity_id"] and change.filing_id == cert_no:
                updated.append(apply_agent_document(change, text))
            else:
                updated.append(change)
        self.changes = updated

    def run(self) -> dict:
        started = time.time()
        credit_state = {}
        try:
            credit_state = self.client.reconcile(96639, 690)
        except Exception as exc:
            self.notes.append(f"credit reconcile failed: {type(exc).__name__}")
        write_feasibility(self.out / "source_feasibility.csv")
        self._repair_saved_entities()
        self._repair_agent_docs()
        # One known live entity first, so the filings parser is exercised on a number search.
        self.detail("753682", "KING CONSTRUCTION AND HOME REPAIR LLC")
        for prefix in PREFIXES:
            if len(self.checkpoint["detailed"]) >= self.max_details:
                self.notes.append(
                    f"Stopped prefix searches at the {self.max_details}-entity detail cap."
                )
                break
            rows = self.search_prefix(prefix)
            for row in rows:
                if len(self.checkpoint["detailed"]) >= self.max_details:
                    if _candidate(row):
                        self.rejected.append(
                            {
                                "entity_id": row["entity_id"],
                                "legal_name": row["legal_name"],
                                "stage": "detail_cap",
                                "reasons": "not_opened_after_50_entity_cap",
                                "detail": f"prefix={prefix}",
                            }
                        )
                    continue
                if not _candidate(row):
                    continue
                self.detail(row["entity_id"], row["legal_name"])
        self.stats["management_jobs"]["attempted"] = 0
        self.notes.append(
            "Apify job actors were not run. APIFY_TOKEN is unset and the store actors found earlier are pay-per-result."
        )
        self.notes.append(
            "Owner verification was not started. Openers are drafted only after a current full-name owner is verified, "
            "and only for the filing-change AND management-job intersection. Claude did not run."
        )
        structural_passes = [
            row
            for row in self.entities
            if "operating_county_outside" not in row["cohort_fail_reasons"]
            and "operating_county_unknown" not in row["cohort_fail_reasons"]
            and "operating_county_split" not in row["cohort_fail_reasons"]
            and "formation_date_unknown" not in row["cohort_fail_reasons"]
            and "formation_year_" not in row["cohort_fail_reasons"]
            and "chapter_not_confirmed_llc" not in row["cohort_fail_reasons"]
            and "previously_delivered" not in row["cohort_fail_reasons"]
            and row["status"].lower() == "active"
        ]
        if structural_passes:
            self.notes.append(
                f"{len(structural_passes)} entities cleared county, year, LLC, and baseline screens "
                "but trade was not confirmed from a non-SOS source, so they were not accepted "
                "and company career pages were not searched."
            )
        else:
            years = sorted(
                {"unknown" if not row["formation_date"] else row["formation_date"][:4] for row in self.entities}
            )
            self.notes = [note for note in self.notes if not note.startswith("No parsed entity cleared")]
            self.notes.append(
                "No parsed entity cleared the active LLC, 1985-2005 formation, and Polk, Dallas, or Warren "
                "principal-office screens. Company career pages were not searched. "
                "Formation years present in this first-page sample: " + ", ".join(years) + ". "
                "The opened page was the first 25 rows of a larger result, and searches stop at 1,000 matches. "
                "That page is not a formation-year or county filter."
            )
        change_rows = [_flatten_change(change) for change in self.changes]
        in_window = [row for row in change_rows if row["within_last_12_months"] == "yes"]
        review = []
        for row in change_rows:
            review.append(
                {
                    "entity_id": row["entity_id"],
                    "legal_name": row["legal_name"],
                    "lane": "filing_change_only",
                    "event": row["event"],
                    "filing_id": row["filing_id"],
                    "filing_date": row["filing_date"],
                    "within_last_12_months": row["within_last_12_months"],
                    "job_url": "",
                    "cohort_pass": "no",
                    "note": "No verified current management job was matched. Intersection is empty.",
                }
            )
        self.stats["sos_entity"]["intersected"] = 0
        _write_csv(self.out / "entities.csv", ENTITY_FIELDS, self.entities)
        _write_csv(self.out / "filing_changes.csv", CHANGE_FIELDS, change_rows)
        _write_csv(self.out / "management_jobs.csv", JOB_FIELDS, [])
        _write_csv(self.out / "qualified_intersection.csv", INTERSECTION_FIELDS, [])
        _write_csv(self.out / "single_signal_review.csv", REVIEW_FIELDS, review)
        _write_csv(self.out / "rejected.csv", REJECT_FIELDS, self.rejected)
        elapsed = time.time() - started
        seen_notes: list[str] = []
        for note in self.notes:
            if note not in seen_notes:
                seen_notes.append(note)
        self.notes = seen_notes
        live_source_seconds = round(sum(item["seconds"] for item in self.stats.values()), 1)
        report = {
            "research_date": RESEARCH_DATE,
            "coverage": "partial_name_prefix_and_one_number_lookup_not_all_active_entities",
            "claude_summarizer": CLAUDE_STATUS,
            "accepted_new_owner_verified": 0,
            "target": 50,
            "shortfall_versus_50": 50,
            "counts": {
                "entities_parsed": len(self.entities),
                "filing_changes": len(change_rows),
                "filing_changes_last_12_months": len(in_window),
                "management_jobs": 0,
                "qualified_intersection": 0,
                "single_signal_review": len(review),
                "rejected_rows": len(self.rejected),
                "owner_verified": 0,
                "structural_screen_passes": len(structural_passes),
                "biennial_documents_sampled": self.biennial_samples,
                "biennial_documents_with_officer_roster": self.biennial_with_officers,
                "agent_change_documents_read": self.agent_docs,
            },
            "prefix_pages": self.coverage_pages,
            "sources": self.stats,
            "credits": {
                **credit_state,
                "local_spent_after": self.client.spent(),
                "local_cap": 4000,
                "credits_added_by_pilot_counter": self.client.credits_observed,
                "elapsed_seconds_this_process": round(elapsed, 1),
                "live_source_seconds": live_source_seconds,
            },
            "notes": self.notes,
            "interpretation": {
                "registered_agent_change_is_ownership_transfer": False,
                "same_surname_is_family": False,
                "formation_year_is_founder_age": False,
                "job_opening_is_a_hire": False,
                "job_opening_is_first_role_without_explicit_text": False,
            },
        }
        (self.out / "yield_report.json").write_text(json.dumps(report, indent=2))
        _write_readme(self.out / "README.md", report)
        return report


def _write_readme(path: Path, report: dict) -> None:
    counts = report["counts"]
    lines = [
        "# Structural ingestion pilot",
        "",
        f"Research date: {report['research_date']}. Claude summarizer: {report['claude_summarizer']}.",
        "",
        "This run is a partial Iowa Secretary of State name-prefix sample plus one business-number lookup. It is not a list of all active construction, specialty-trade, or manufacturing LLCs in Polk, Dallas, and Warren counties.",
        "",
        "## Live counts",
        "",
        f"- Entities parsed: {counts['entities_parsed']}",
        f"- Filing-index or document changes: {counts['filing_changes']}",
        f"- Those changes with a filing date in the last 12 months: {counts['filing_changes_last_12_months']}",
        f"- Management jobs with an exact company match: {counts['management_jobs']}",
        f"- Filing-change AND management-job intersection: {counts['qualified_intersection']}",
        f"- Single-lane rows: {counts['single_signal_review']}",
        f"- Rejected or not-accepted rows: {counts['rejected_rows']}",
        f"- Owner-verified new companies: {counts['owner_verified']}",
        f"- Shortfall versus 50 accepted companies: {report['shortfall_versus_50']}",
        f"- Biennial documents sampled: {counts['biennial_documents_sampled']}",
        f"- Sampled biennials with an officer, manager, or member roster: {counts['biennial_documents_with_officer_roster']}",
        f"- Registered-agent change documents read: {counts['agent_change_documents_read']}",
        f"- Live source time recorded on the fetch counters: {report['credits'].get('live_source_seconds')} seconds",
        f"- Firecrawl local spend after the run: {report['credits'].get('local_spent_after')} of {report['credits'].get('local_cap')}",
        "",
        "Search pages opened:",
        "",
    ]
    for page in report.get("prefix_pages") or []:
        lines.append(
            f"- {page.get('prefix')}: showed {page.get('shown_from')}-{page.get('shown_to')} "
            f"of {page.get('reported_total')}; parser kept {page.get('parsed_rows')} rows"
        )
    lines.extend([
        "",
        "## What the sources actually returned",
        "",
        "The HTML search has no county, industry, or formation-year filter. The public JSON schema also has no NAICS or county field. Entity JSON calls returned HTTP 401 without a subscription, and the subscription was not purchased.",
        "",
        "The officers tab on the sampled entity was a current list and said none were on file. Two fields are required before OFFICER_ADDED, OFFICER_REMOVED, or OFFICER_ROLE_CHANGED can be emitted: a prior snapshot and a later snapshot with filing ids. Those snapshots were not on the officers tab.",
        "",
        "The sampled LLC biennial report listed the registered agent, principal office, and an authorized signer. It did not list members, managers, or officers. Further biennial downloads stopped after that representative sample.",
        "",
        "A Change of Registered Agent document can supply the previous agent name and the new agent name. That comparison is REGISTERED_AGENT_CHANGED. It is not an ownership transfer, and the agent is not recorded as the owner.",
        "",
        "County is taken from the principal-office city when that city sits in only one of Polk, Dallas, or Warren. Registered-agent cities are not used. Split cities stay unresolved. Formation year comes from a certificate of organization or articles filing, not from the summary filing date alone.",
        "",
        "Apify and Bright Data tokens were unset. Indeed actors in the Apify store are pay-per-result and were not run. No management-job row was created. The intersection is empty, so owner verification and openers were not started.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "pip install -r exit_factor_structural_pipeline/requirements.txt",
        "PYTHONPATH=. python -m exit_factor_structural_pipeline pilot --max-details 50",
        "PYTHONPATH=. python -m pytest exit_factor_structural_pipeline/tests",
        "```",
        "",
        "The Firecrawl key is read from the existing secret file outside the repository. Snapshots and checkpoint state stay in `exit_factor_structural_pipeline/cache/`, which is gitignored.",
        "",
        "## Notes from this run",
        "",
    ])
    for note in report["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    path.write_text("\n".join(lines))
