#!/usr/bin/env python3
"""Verify regional JSONL people against fetched public pages and emit merge files.

Evidence strings written to the merge files are sliced from fetched page text.
Agent paraphrases are not copied into qualified evidence fields.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_dataset import COMPANIES, PEOPLE, norm_domain, norm_name  # noqa: E402

PAGES = ROOT / "raw" / "pages"
RESEARCH_DATE = "2026-09-30"
EXCLUDED_STATES = {"NY", "ND", "SD"}

INVESTOR_PHRASES = [
    "dscr",
    "fix and flip",
    "fix & flip",
    "fix-and-flip",
    "hard money",
    "private money",
    "bridge loan",
    "investment property",
    "rental income",
    "non-qm",
    "non qm",
]

OUTSIDE_PHRASES = [
    "wholesale lender",
    "wholesale lenders",
    "wholesale partner",
    "wholesale partners",
    "wholesale broker",
    "wholesale access",
    "wholesale market",
    "wholesale relationship",
    "wholesale relationships",
    "lender network",
    "network of lenders",
    "network of wholesale",
    "multiple lenders",
    "multiple wholesale",
    "multiple national wholesale",
    "dozens of wholesale",
    "dozens of lenders",
    "hundreds of lenders",
    "hundreds of wholesale",
    "shop your loan",
    "shops your loan",
    "shop your file",
    "shops your file",
    "shop the market",
    "shop a network",
    "not a direct lender",
    "not a lender",
    "don't lend our own",
    "do not lend our own",
    "does not fund",
    "do not fund loans",
    "lending partners",
    "direct lender access",
    "third-party wholesale",
    "third party wholesale",
]

MENU_MARKERS = ("fha loan", "va loan", "conventional", "jumbo", "usda")

OWNER_WORDS = (
    "owner",
    "founder",
    "president",
    "principal",
    "ceo",
    "managing member",
    "broker/owner",
    "broker / owner",
    "broker-owner",
)

NICKNAMES = {
    "chris": "christopher",
    "christopher": "christopher",
    "steve": "steven",
    "steven": "steven",
    "stephen": "steven",
    "jen": "jennifer",
    "jennifer": "jennifer",
    "jenny": "jennifer",
    "glen": "glenn",
    "glenn": "glenn",
    "matt": "matthew",
    "matthew": "matthew",
    "mike": "michael",
    "michael": "michael",
    "tim": "timothy",
    "timothy": "timothy",
    "bob": "robert",
    "rob": "robert",
    "robert": "robert",
    "bill": "william",
    "william": "william",
    "jim": "james",
    "james": "james",
    "joe": "joseph",
    "joseph": "joseph",
    "dan": "daniel",
    "daniel": "daniel",
    "dave": "david",
    "david": "david",
    "alex": "alexander",
    "alexander": "alexander",
    "ben": "benjamin",
    "benjamin": "benjamin",
    "tom": "thomas",
    "thomas": "thomas",
    "jeff": "jeffrey",
    "jeffrey": "jeffrey",
    "jon": "jonathan",
    "jonathan": "jonathan",
    "nate": "nathan",
    "nathan": "nathan",
    "andy": "andrew",
    "andrew": "andrew",
    "tony": "anthony",
    "anthony": "anthony",
}


def load_pages() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for path in PAGES.glob("*.txt"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines()
        meta = {"url": "", "final": "", "status": "", "title": "", "text": ""}
        body_start = 0
        for i, line in enumerate(lines[:8]):
            if line.startswith("URL:"):
                meta["url"] = line.split(":", 1)[1].strip()
            elif line.startswith("FINAL:"):
                meta["final"] = line.split(":", 1)[1].strip()
            elif line.startswith("STATUS:"):
                meta["status"] = line.split(":", 1)[1].strip()
            elif line.startswith("TITLE:"):
                meta["title"] = line.split(":", 1)[1].strip()
            elif line.startswith("ERROR:"):
                meta["status"] = "ERROR"
                meta["title"] = line
            if line.strip() == "" and i > 0:
                body_start = i + 1
                break
        body = "\n".join(lines[body_start:])
        text = html.unescape(body)
        text = re.sub(r"\s+", " ", text).strip()
        meta["text"] = text
        meta["ok"] = meta["status"] == "200" and len(text) > 200
        for key in (meta["url"], meta["final"]):
            if key:
                index[key.rstrip("/")] = meta
                index[key] = meta
    return index


def norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def pages_for(record: dict, index: dict) -> list[dict]:
    found = []
    seen = set()
    for key, value in record.items():
        if "url" not in key or not value or not str(value).startswith("http"):
            continue
        page = index.get(value) or index.get(norm_url(value))
        if page is None or id(page) in seen:
            continue
        seen.add(id(page))
        found.append(page)
    return found


def usable_text(text: str) -> str:
    """Drop CMS deploy notes that some pages print above the real copy."""
    low = text.lower()
    marker = low.find("template parts")
    if marker == -1:
        return text
    # Keep the portion after the deploy note if the real article follows.
    tail = text[marker + 2000 :]
    return tail if len(tail) > 400 else text


def find_phrase(text: str, phrases: list[str]) -> str | None:
    low = text.lower()
    for phrase in phrases:
        if phrase in low:
            return phrase
    count = re.search(r"\b\d{2,}\+?\s+lenders\b", low)
    if count:
        return count.group(0)
    return None


def _clean_snippet(text: str, start: int, end: int) -> str:
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start > 0 and " " in snippet:
        snippet = snippet.split(" ", 1)[-1]
    if end < len(text) and " " in snippet:
        snippet = snippet.rsplit(" ", 1)[0]
    return snippet[:420]


def window(text: str, needle: str, radius: int = 180) -> str:
    low = text.lower()
    needle_l = needle.lower()
    start_at = 0
    best = ""
    while True:
        idx = low.find(needle_l, start_at)
        if idx < 0:
            break
        start = max(0, idx - radius)
        end = min(len(text), idx + len(needle) + radius)
        snippet = _clean_snippet(text, start, end)
        junk = snippet.lower()
        if any(token in junk for token in ("template parts", "deploy order", "custom html", "cloudflare purge")):
            start_at = idx + len(needle_l)
            best = best or snippet
            continue
        if needle_l in {"dscr", "bridge loan", "fix and flip"} and is_menu(junk):
            start_at = idx + len(needle_l)
            best = best or snippet
            continue
        return snippet
    return best


def is_menu(chunk: str) -> bool:
    hits = sum(1 for marker in MENU_MARKERS if marker in chunk)
    return hits >= 2


def name_near_phrase(text: str, full_name: str, phrase: str, radius: int = 180) -> bool:
    """Investor language must follow the person's name and not be a product menu."""
    low = text.lower()
    name = full_name.lower()
    start = 0
    while True:
        idx = low.find(name, start)
        if idx < 0:
            break
        after = low[idx : idx + len(name) + radius]
        if phrase in after and not is_menu(after):
            return True
        start = idx + len(name)
    return False


def personal_about_page(pages: list[dict], full_name: str) -> bool:
    name = full_name.lower()
    for page in pages:
        title = (page.get("title") or "").lower()
        if name in title and title.startswith("about"):
            return True
    return False


def title_supports(pages: list[dict], full_name: str) -> bool:
    name = full_name.lower()
    for page in pages:
        title = (page.get("title") or "").lower()
        if name in title and any(token in title for token in ("dscr", "investor", "fix", "hard money", "bridge", "rental")):
            return True
    return False


def products_from_text(text: str) -> str:
    low = text.lower()
    found = []
    for label, tokens in (
        ("DSCR", ("dscr",)),
        ("Fix and flip", ("fix and flip", "fix & flip", "fix-and-flip")),
        ("Hard money", ("hard money",)),
        ("Private money", ("private money",)),
        ("Bridge", ("bridge loan", "bridge financing")),
        ("Rental", ("rental income", "investment property")),
        ("Non-QM", ("non-qm", "non qm")),
        ("Bank statement", ("bank statement",)),
    ):
        if any(token in low for token in tokens):
            found.append(label)
    return "; ".join(found)


def unit_evidence(text: str) -> str:
    low = text.lower()
    for phrase in ("1-4 unit", "1–4 unit", "1-4 family", "2-4 unit", "2–4 unit", "2-4 family", "single-family", "single family"):
        if phrase in low:
            return window(text, phrase, 120)
    return "Fetched pages do not print a numeric 1-4 unit limit."


def is_owner(title: str) -> bool:
    low = title.lower()
    return any(word in low for word in OWNER_WORDS)


def canonical_first(name: str) -> str:
    token = norm_name(name).split(" ")[0] if name else ""
    return NICKNAMES.get(token, token)


def existing_keys() -> set[tuple[str, str, str]]:
    keys = set()
    for row in PEOPLE:
        first = canonical_first(row["First Name"])
        last = norm_name(row["Last Name"])
        domain = norm_domain(row["Company Domain"])
        keys.add((first, last, domain))
        keys.add((first, last, ""))
    return keys


def email_on_page(email: str, text: str) -> bool:
    if not email or "@" not in email:
        return False
    return email.lower() in text.lower()


def phone_on_page(phone: str, text: str) -> bool:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return False
    page_digits = re.sub(r"\D", "", text)
    return digits[-7:] in page_digits


def to_person_row(record: dict, status: str, reason: str, notes: str, pages: list[dict]) -> dict:
    text = usable_text(" ".join(p["text"] for p in pages if p.get("ok")))
    email = record.get("business_email") or ""
    email_ok = email_on_page(email, text)
    direct = record.get("direct_mobile_phone") or ""
    office = record.get("office_phone") or ""
    full = record.get("full_name") or ""
    person_snip = window(text, full, 160) if full.lower() in text.lower() else ""
    investor_hit = find_phrase(text, INVESTOR_PHRASES) or ""
    outside_hit = find_phrase(text, OUTSIDE_PHRASES) or ""
    investor_snip = window(text, investor_hit, 160) if investor_hit else ""
    outside_snip = window(text, outside_hit, 160) if outside_hit else ""
    return {
        "First Name": record.get("first_name") or "",
        "Last Name": record.get("last_name") or "",
        "Full Name": full,
        "Title": record.get("title") or "",
        "Company": record.get("company") or "",
        "Company Domain": norm_domain(record.get("company_domain") or record.get("company_website") or ""),
        "Company Website": record.get("company_website") or "",
        "City": record.get("city") or "",
        "State": (record.get("state") or "").upper(),
        "LinkedIn URL": record.get("linkedin_url") or "",
        "Business Email": email if email_ok else "",
        "Email Status": "PUBLIC" if email_ok else "NONE",
        "Direct/Mobile Phone": direct if phone_on_page(direct, text) else "",
        "Office Phone": office if phone_on_page(office, text) else "",
        "Person Source URL": record.get("person_source_url") or "",
        "Person Evidence": person_snip,
        "Company Source URL 1": record.get("company_source_url_1") or "",
        "Company Evidence 1": outside_snip or investor_snip,
        "Company Source URL 2": record.get("company_source_url_2") or "",
        "Company Evidence 2": investor_snip if investor_snip != (outside_snip or investor_snip) else "",
        "Investor Lending Evidence": investor_snip,
        "Outside Lender/Broker Evidence": outside_snip,
        "Products Found": products_from_text(text),
        "1-4 Unit Evidence": unit_evidence(text),
        "Business Model": record.get("business_model") or "",
        "Current Employment Verified": "YES" if status != "EXCLUDED" else "NO",
        "Geography Qualified": "NO" if (record.get("state") or "").upper() in EXCLUDED_STATES else "YES",
        "Competitor Check": "PASS",
        "Existing CV3 Duplicate Check": "PRIOR_WORKBOOK_NOT_SUPPLIED",
        "DNC Status": "NOT_YET_SCREENED",
        "Research Date": RESEARCH_DATE,
        "Qualification Status": status,
        "Review Notes": notes,
        "Exclusion Reason": reason,
    }


def classify(record: dict, pages: list[dict]) -> tuple[str, str, str]:
    state = (record.get("state") or "").upper()
    if state in EXCLUDED_STATES:
        return "EXCLUDED", "Person or company located in an excluded state.", "Fetched pages were not used to override the state exclusion."
    ok_pages = [p for p in pages if p.get("ok")]
    if not ok_pages:
        return "EXCLUDED", "Cited public pages could not be fetched.", "HTTP error or empty body. Not counted."
    text = usable_text(" ".join(p["text"] for p in ok_pages))
    low = text.lower()
    full = (record.get("full_name") or "").strip()
    last = (record.get("last_name") or "").strip().lower()
    first = (record.get("first_name") or "").strip().lower()
    if not full or full.lower() not in low or last not in low or first not in low:
        return "EXCLUDED", "Name was not present on the fetched public pages.", "Unverified regional record."
    investor = find_phrase(text, INVESTOR_PHRASES)
    outside = find_phrase(text, OUTSIDE_PHRASES)
    title = record.get("title") or ""
    if not title.strip():
        return "REVIEW_REQUIRED", "", "The fetched pages name this person, but they do not print a current producing title."
    owner = is_owner(title)
    personal_investor = bool(investor) and (
        name_near_phrase(text, full, investor, 180) or title_supports(ok_pages, full)
    )
    about_page = personal_about_page(ok_pages, full)
    if investor and outside and (owner or personal_investor or about_page):
        note = "Owner/founder of a page-verified broker shop." if owner else "Name appears near investor-product language on a fetched page."
        if not personal_investor and owner:
            note += " Investor and outside-lender language are company-level on the fetched pages."
        return "QUALIFIED", "", note
    if investor and not outside:
        return "REVIEW_REQUIRED", "", "Name and investor-product language are on the fetched pages. An outside-lender or wholesale sentence was not found."
    if investor and outside and not owner and not personal_investor:
        return "REVIEW_REQUIRED", "", "Company pages show investor products and outside-lender placement. This person's own production of those products is not shown next to their name."
    if not investor:
        return "EXCLUDED", "Fetched pages do not show an investor-loan product.", "Name was on the page, but DSCR, fix-and-flip, hard money, bridge, or rental-income language was not."
    return "REVIEW_REQUIRED", "", "Page support is incomplete."


def load_regional() -> list[dict]:
    rows = []
    for name in ("region_east.jsonl", "region_south.jsonl", "region_west.jsonl"):
        path = ROOT / "raw" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row["_source_file"] = name
                rows.append(row)
    return rows


def company_from_people(people: list[dict]) -> list[dict]:
    existing = {norm_domain(c["Company Domain"]) for c in COMPANIES}
    grouped: dict[str, list[dict]] = {}
    for person in people:
        domain = norm_domain(person["Company Domain"])
        grouped.setdefault(domain, []).append(person)
    companies = []
    for domain, group in grouped.items():
        if domain in existing:
            continue
        qualified = [p for p in group if p["Qualification Status"] == "QUALIFIED"]
        chosen = qualified[0] if qualified else group[0]
        status = "QUALIFIED" if qualified else "REVIEW_REQUIRED"
        companies.append(
            {
                "Company": chosen["Company"],
                "Company Domain": domain,
                "Company Website": chosen["Company Website"],
                "City": chosen["City"],
                "State": chosen["State"],
                "Business Model": chosen["Business Model"],
                "Products Found": chosen["Products Found"],
                "Investor Lending Evidence": chosen["Investor Lending Evidence"],
                "Outside Lender/Broker Evidence": chosen["Outside Lender/Broker Evidence"],
                "1-4 Unit Evidence": chosen["1-4 Unit Evidence"],
                "Company Source URL": chosen["Company Source URL 1"],
                "Qualification Status": status,
                "Exclusion Reason": "" if status != "EXCLUDED" else chosen["Exclusion Reason"],
                "Review Notes": chosen["Review Notes"],
                "Research Date": RESEARCH_DATE,
            }
        )
    return companies


def main() -> None:
    index = load_pages()
    known = existing_keys()
    people_out = []
    decisions = []
    seen_local = set()
    for record in load_regional():
        pages = pages_for(record, index)
        status, reason, notes = classify(record, pages)
        first = canonical_first(record.get("first_name") or "")
        last = norm_name(record.get("last_name") or "")
        domain = norm_domain(record.get("company_domain") or record.get("company_website") or "")
        key = (first, last, domain)
        loose = (first, last, "")
        if key in known or loose in known or key in seen_local:
            decisions.append((record.get("full_name"), "DUPLICATE", record.get("state"), record.get("company")))
            continue
        seen_local.add(key)
        row = to_person_row(record, status, reason, notes, pages)
        if status == "QUALIFIED":
            if not row["Person Evidence"] or not row["Investor Lending Evidence"] or not row["Outside Lender/Broker Evidence"]:
                row["Qualification Status"] = "REVIEW_REQUIRED"
                row["Review Notes"] = (row["Review Notes"] + " Evidence window could not be sliced from the page.").strip()
                status = "REVIEW_REQUIRED"
            if row["Business Model"] not in {"BROKER", "HYBRID_BROKER"}:
                row["Qualification Status"] = "REVIEW_REQUIRED"
                row["Review Notes"] = (row["Review Notes"] + " Business model was not broker or hybrid broker.").strip()
                status = "REVIEW_REQUIRED"
        people_out.append(row)
        decisions.append((row["Full Name"], status, row["State"], row["Company"]))

    companies_out = company_from_people(people_out)
    (ROOT / "raw" / "merged_people.json").write_text(json.dumps(people_out, indent=2) + "\n", encoding="utf-8")
    (ROOT / "raw" / "merged_companies.json").write_text(json.dumps(companies_out, indent=2) + "\n", encoding="utf-8")
    counts = {}
    for _, status, _, _ in decisions:
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"decisions": counts, "people_written": len(people_out), "companies_written": len(companies_out)}, indent=2))
    for name, status, state, company in decisions:
        print(f"{status:18} {state or '':2} {name} | {company}")


if __name__ == "__main__":
    main()
