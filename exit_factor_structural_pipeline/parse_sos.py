"""Parsers for Iowa SOS HTML/markdown that this pilot actually observed."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from exit_factor_structural_pipeline.schema import FilingRecord

_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_RESULTS = re.compile(r"Results\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)", re.I)
_CERT_ROW = re.compile(
    r"\|\s*([A-Z]{1,3}\d{5,})\s*\|\s*(\d+)\s*\|\s*(\d{1,2}/\d{1,2}/\d{4})\s*\|\s*(\d{1,2}/\d{1,2}/\d{4})\s*\|\s*([^|\n]+)"
)
_MD_RESULT = re.compile(
    r"\|\s*\[(\d+)\]\([^)]*\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)
_CITY = re.compile(r"([A-Z][A-Z .'-]*?),\s*([A-Z]{2}),\s*(\d{5})")
_ORG_TYPES = (
    "CERTIFICATE OF ORGANIZATION",
    "ARTICLES OF ORGANIZATION",
    "ARTICLES OF INCORPORATION",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = _DATE.search(value)
    if not match:
        return None
    month, day, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def iso_or_blank(value: date | None) -> str:
    return value.isoformat() if value else ""


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</tr>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    text = re.sub(r"(?i)</(p|div|h\d|li)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def parse_result_span(text: str) -> dict[str, int | None]:
    match = _RESULTS.search(text)
    if not match:
        return {"shown_from": None, "shown_to": None, "reported_total": None}
    start, end, total = (int(part) for part in match.groups())
    return {"shown_from": start, "shown_to": end, "reported_total": total}


def parse_search_results(text: str) -> list[dict[str, str]]:
    rows = []
    seen: set[str] = set()
    for match in _MD_RESULT.finditer(text):
        entity_id, name, status, name_type, legal = (part.strip() for part in match.groups())
        if entity_id in seen:
            continue
        seen.add(entity_id)
        rows.append(
            {
                "entity_id": entity_id,
                "name": name,
                "status": status,
                "name_type": name_type,
                "legal_name": legal,
            }
        )
    if rows:
        return rows
    # HTML path: a business-number anchor followed by nearby cell text is handled
    # by the markdown converter in the client. Keep a plain pipe fallback.
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) >= 5 and cells[0].isdigit() and len(cells[0]) >= 3:
            entity_id = cells[0]
            if entity_id in seen:
                continue
            seen.add(entity_id)
            rows.append(
                {
                    "entity_id": entity_id,
                    "name": cells[1],
                    "status": cells[2],
                    "name_type": cells[3],
                    "legal_name": cells[4],
                }
            )
    return rows


def parse_filings(text: str) -> list[FilingRecord]:
    filings: list[FilingRecord] = []
    seen: set[str] = set()
    for match in _CERT_ROW.finditer(text):
        cert, pages, filed, effective, filing_type = (part.strip() for part in match.groups())
        if cert in seen:
            continue
        seen.add(cert)
        filings.append(
            FilingRecord(
                cert_no=cert,
                pages=pages,
                filing_date=parse_date(filed),
                effective_date=parse_date(effective),
                filing_type=re.sub(r"\s+", " ", filing_type),
            )
        )
    return filings


def _section(text: str, start: str, end: str | None) -> str:
    begin = text.upper().find(start.upper())
    if begin < 0:
        return ""
    if not end:
        return text[begin:]
    stop = text.upper().find(end.upper(), begin + len(start))
    if stop < 0:
        return text[begin:]
    return text[begin:stop]


def _city_line(section: str) -> tuple[str, str, str]:
    match = _CITY.search(section.upper())
    if not match:
        return "", "", ""
    city, state, zip_code = match.groups()
    return " ".join(city.split()).title(), state, zip_code


def _labeled_name(section: str) -> str:
    lines = [line.strip(" |") for line in section.splitlines()]
    lines = [line for line in lines if line]
    for idx, line in enumerate(lines):
        if line.upper() == "FULL NAME" and idx + 1 < len(lines):
            candidate = lines[idx + 1].strip(" |")
            if candidate and "ADDRESS" not in candidate.upper():
                return candidate
    return ""


def _flat_cells(text: str) -> list[str]:
    cells: list[str] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        cells.extend(part for part in parts if part)
    return cells


def _values_after(cells: list[str], labels: tuple[str, ...]) -> list[str]:
    lowered = [cell.lower().rstrip(".") for cell in cells]
    targets = [label.lower().rstrip(".") for label in labels]
    width = len(targets)
    for idx in range(len(cells) - width):
        if lowered[idx : idx + width] == targets:
            return cells[idx + width : idx + (width * 2)]
    return []


def parse_summary(text: str) -> dict[str, str]:
    """Parse the summary layout observed for a business-number search.

    The live HTML puts each table cell on its own line. The saved fixture puts
    a header triple on one line. Flattening on the pipe character covers both.
    """
    out = {
        "entity_id": "",
        "legal_name": "",
        "status": "",
        "name_type": "",
        "state_of_inc": "",
        "modified": "",
        "expiration": "",
        "effective_date": "",
        "filing_date": "",
        "chapter": "",
        "registered_agent_name": "",
        "principal_city": "",
        "principal_state": "",
        "principal_zip": "",
        "agent_city": "",
    }
    cells = _flat_cells(text.split("Names (")[0])
    identity = _values_after(cells, ("Business No.", "Legal Name", "Status"))
    if len(identity) >= 3 and identity[0].isdigit():
        out["entity_id"], out["legal_name"], out["status"] = identity[:3]
    kind = _values_after(cells, ("Type", "State of Inc.", "Modified"))
    if len(kind) >= 3:
        out["name_type"], out["state_of_inc"], out["modified"] = kind[:3]
    dates = _values_after(cells, ("Expiration Date", "Effective Date", "Filing Date"))
    if len(dates) >= 3:
        out["expiration"], out["effective_date"], out["filing_date"] = dates[:3]
    for idx, cell in enumerate(cells):
        if cell.lower() == "chapter" and idx + 1 < len(cells):
            out["chapter"] = cells[idx + 1]
            break
    agent = _section(text, "Registered Agent", "Principal Office")
    office = _section(text, "Principal Office", "Back to Top")
    out["registered_agent_name"] = _labeled_name(agent)
    city, state, zip_code = _city_line(office)
    out["principal_city"], out["principal_state"], out["principal_zip"] = city, state, zip_code
    agent_city, _, _ = _city_line(agent)
    out["agent_city"] = agent_city
    if not out["entity_id"]:
        match = re.search(r"Searched:\s*\**\s*(\d+)", text)
        if match:
            out["entity_id"] = match.group(1)
    return out


def formation_from_filings(filings: list[FilingRecord]) -> tuple[date | None, str]:
    """Organization/articles dates are the formation basis. Summary filing date is not."""
    chosen: date | None = None
    basis = "unknown"
    for filing in filings:
        ftype = filing.filing_type.upper()
        if not any(token in ftype for token in _ORG_TYPES):
            continue
        if filing.filing_date is None:
            continue
        if chosen is None or filing.filing_date < chosen:
            chosen = filing.filing_date
            basis = f"{filing.cert_no} {filing.filing_type}"
    return chosen, basis


def parse_officers(text: str) -> list[dict[str, str]]:
    if re.search(r"none on file", text, re.I):
        return []
    officers = []
    header_idx = None
    rows = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if cells:
            rows.append(cells)
    for idx, cells in enumerate(rows):
        lowered = [cell.lower() for cell in cells]
        if "name" in lowered and "type" in lowered:
            header_idx = idx
            break
    if header_idx is None:
        return []
    header = [cell.lower() for cell in rows[header_idx]]
    for cells in rows[header_idx + 1 :]:
        if len(cells) < 2:
            continue
        joined = " ".join(cells).lower()
        if "secretary of state" in joined or "none on file" in joined:
            break
        record = {header[i]: cells[i] for i in range(min(len(header), len(cells)))}
        name = record.get("name", "")
        role = record.get("type", "")
        if name:
            officers.append({"name": name, "role": role})
    return officers


def biennial_has_officer_fields(text: str) -> bool:
    """The sampled LLC biennial named an agent and a signer, not members or officers."""
    if not re.search(r"biennial report", text, re.I):
        return False
    return bool(
        re.search(r"\b(member|manager|officer|director)\b", text, re.I)
        and re.search(r"\b(name of|names of)\b", text, re.I)
    )


_LABEL_SKIP = (
    "full name",
    "address",
    "city",
    "state",
    "zip",
    "country",
    "the name of the business",
    "mailing address",
    "street address",
    "email address",
    "signature",
    "authorized",
    "new agent",
    "date",
)


def _clean_doc_line(line: str) -> str:
    text = re.sub(r"[#*]+", " ", line)
    text = text.replace("|", " ")
    return re.sub(r"\s+", " ", text).strip()


def _name_after(lines: list[str], index: int) -> str:
    for line in lines[index + 1 : index + 8]:
        low = line.lower()
        if not line or low.startswith("(") or re.fullmatch(r"[-:]+", line):
            continue
        if any(low.startswith(prefix) for prefix in _LABEL_SKIP):
            continue
        if "secretary of state" in low:
            continue
        if "registered agent" in low and any(token in low for token in ("current", "new ", "must", "sign")):
            continue
        if re.match(r"\d", line):
            continue
        return line
    return "unknown"


def parse_agent_change(text: str) -> tuple[str, str]:
    """Return (before, after) names from a registered-agent change document.

    Missing sides stay unknown. Names are not treated as owners.
    Street addresses are not returned.
    """
    if not re.search(r"registered agent", text, re.I):
        return "unknown", "unknown"
    lines = [_clean_doc_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    before = "unknown"
    after = "unknown"
    for idx, line in enumerate(lines):
        low = line.lower()
        if "must sign" in low or "consent" in low:
            continue
        if before == "unknown" and "current registered agent" in low and "office is" not in low:
            before = _name_after(lines, idx)
        elif after == "unknown" and "new registered agent" in low:
            after = _name_after(lines, idx)
    return before, after


def within_window(value: date | None, start: date, end: date) -> bool:
    if value is None:
        return False
    return start <= value <= end


def parse_timestamp(value: str) -> datetime | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day)
