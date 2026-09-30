#!/usr/bin/env python3
"""Rebuild Exit Factor CSV outputs from signals_master.csv."""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/workspace/exit_factor_250")
MASTER = ROOT / "signals_master.csv"
RESEARCH_DATE = "2026-09-30"

COLUMNS = [
    "Company",
    "Website",
    "City",
    "State",
    "Industry",
    "Approximate Company Size Evidence",
    "Owner First Name",
    "Owner Last Name",
    "Owner Full Name",
    "Owner Title",
    "Ownership Verified",
    "Owner LinkedIn",
    "Owner Email",
    "Owner Phone",
    "Company Phone",
    "Signal Type",
    "Signal Headline",
    "Signal Explanation",
    "Why Exit Factor",
    "Signal Date",
    "Source URL",
    "Source Title",
    "Evidence Excerpt",
    "Secondary Source URL",
    "Research Date",
    "Qualification Status",
    "Review Notes",
    "Exclusion Reason",
]


def load_rows():
    with MASTER.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def domain(url):
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def rank(status):
    return {"QUALIFIED": 0, "REVIEW_REQUIRED": 1, "EXCLUDED": 2}.get(status, 9)


ADDRESSES = {
    "Sage Homes": "301 NE Trilein Dr, Ankeny, IA",
    "Bella Homes of Iowa": "506 E 1st, Huxley, IA 50124",
    "Walk Your Plans": "1500 S.E. 19th St., Suite 255, Grimes, IA",
    "Stanbrough Realty Company": "2775 86th Street, Urbandale, IA 50322",
    "Cemen Tech": "1700 N. 14th St., Indianola, IA 50125",
    "Baker Group": "1600 Corporate Woods Drive, Ankeny, IA",
}

SAMPLE_COLUMNS = [
    "Company",
    "City",
    "State",
    "Industry",
    "Owner Full Name",
    "Owner Title",
    "Ownership Verified",
    "Company Phone",
    "Mailing Address",
    "Signal Headline",
    "Signal Date",
    "Signal Type",
    "Why Exit Factor",
    "Source URL",
    "Qualification Status",
    "Contact Completeness",
    "Sample Notes",
]


def completeness(row):
    phone = (row.get("Company Phone") or "").strip()
    email = (row.get("Owner Email") or "").strip()
    mobile = (row.get("Owner Phone") or "").strip()
    parts = []
    if phone:
        parts.append("company phone published")
    else:
        parts.append("no company phone published")
    if email:
        parts.append("owner email published")
    else:
        parts.append("owner email not published")
    if mobile:
        parts.append("owner phone published but not labeled mobile")
    else:
        parts.append("mobile not published")
    return "Not Florida-complete: " + "; ".join(parts)


def write_jeremy_sample(rows):
    """One call/mail row per company that is qualified or still in review."""
    best = {}
    for row in rows:
        if row["Qualification Status"] not in {"QUALIFIED", "REVIEW_REQUIRED"}:
            continue
        key = row["Company"].strip().lower()
        cur = best.get(key)
        if cur is None or rank(row["Qualification Status"]) < rank(cur["Qualification Status"]):
            best[key] = row
    sample = []
    for row in best.values():
        usable = (
            row["Qualification Status"] == "QUALIFIED"
            or (row.get("Company Phone") or "").strip()
            or row["Company"] in ADDRESSES
            or row.get("Ownership Verified") == "Yes"
        )
        if not usable:
            continue
        notes = []
        if row["Company"] in {"Stanbrough Realty Company", "Walk Your Plans", "Next Phase Development LLC", "Diligent Development"}:
            notes.append("Outside the core HVAC, plumbing, electrical, and field-trade list.")
        if row["Ownership Verified"] != "Yes":
            notes.append("Do not treat the named person as the owner until a source says so.")
        if not (row.get("Company Phone") or "").strip() and row["Company"] not in ADDRESSES:
            notes.append("No published phone or street address captured.")
        sample.append(
            {
                "Company": row["Company"],
                "City": row["City"],
                "State": row["State"],
                "Industry": row["Industry"],
                "Owner Full Name": row["Owner Full Name"],
                "Owner Title": row["Owner Title"],
                "Ownership Verified": row["Ownership Verified"],
                "Company Phone": row["Company Phone"],
                "Mailing Address": ADDRESSES.get(row["Company"], ""),
                "Signal Headline": row["Signal Headline"],
                "Signal Date": row["Signal Date"],
                "Signal Type": row["Signal Type"],
                "Why Exit Factor": row["Why Exit Factor"],
                "Source URL": row["Source URL"],
                "Qualification Status": row["Qualification Status"],
                "Contact Completeness": completeness(row),
                "Sample Notes": " ".join(notes),
            }
        )
    sample.sort(key=lambda r: (rank(r["Qualification Status"]), r["Company"].lower()))
    write_rows(ROOT / "jeremy_vos_sample.csv", sample, SAMPLE_COLUMNS)
    print("jeremy sample rows", len(sample))


def rebuild():
    rows = load_rows()
    for row in rows:
        missing = [c for c in COLUMNS if c not in row]
        if missing:
            raise SystemExit(f"missing columns: {missing}")
        if "sell" in (row.get("Why Exit Factor") or "").lower():
            raise SystemExit(f"sale language in Why Exit Factor: {row['Company']}")

    qualified_rows = [r for r in rows if r["Qualification Status"] == "QUALIFIED"]
    primary = []
    seen = set()
    for row in qualified_rows:
        key = row["Company"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        primary.append(row)

    review = [r for r in rows if r["Qualification Status"] == "REVIEW_REQUIRED"]
    excluded = [r for r in rows if r["Qualification Status"] == "EXCLUDED"]

    companies = {}
    for row in rows:
        key = row["Company"].strip().lower()
        cur = companies.get(key)
        if cur is None or rank(row["Qualification Status"]) < rank(cur["Qualification Status"]):
            companies[key] = {
                "Company": row["Company"],
                "Website": row["Website"],
                "City": row["City"],
                "State": row["State"],
                "Industry": row["Industry"],
                "Approximate Company Size Evidence": row["Approximate Company Size Evidence"],
                "Company Phone": row["Company Phone"],
                "Qualification Status": row["Qualification Status"],
                "Signals In File": 0,
            }
        companies[key]["Signals In File"] += 1
        if row["Website"] and not companies[key]["Website"]:
            companies[key]["Website"] = row["Website"]
        if row["Company Phone"] and not companies[key]["Company Phone"]:
            companies[key]["Company Phone"] = row["Company Phone"]

    owners = {}
    for row in rows:
        name = (row.get("Owner Full Name") or "").strip()
        if not name:
            continue
        owners[(name, row["Company"])] = {
            "Owner Full Name": name,
            "Owner First Name": row["Owner First Name"],
            "Owner Last Name": row["Owner Last Name"],
            "Owner Title": row["Owner Title"],
            "Ownership Verified": row["Ownership Verified"],
            "Owner LinkedIn": row["Owner LinkedIn"],
            "Owner Email": row["Owner Email"],
            "Owner Phone": row["Owner Phone"],
            "Company": row["Company"],
            "Company Phone": row["Company Phone"],
        }

    sources = []
    seen_src = set()
    for row in rows:
        for role, url, title in (
            ("primary", row["Source URL"], row["Source Title"]),
            ("secondary", row["Secondary Source URL"], ""),
        ):
            if not url or (row["Company"], role, url) in seen_src:
                continue
            seen_src.add((row["Company"], role, url))
            sources.append(
                {
                    "Company": row["Company"],
                    "Role": role,
                    "Source URL": url,
                    "Source Title": title,
                    "Signal Date": row["Signal Date"],
                    "Research Date": row["Research Date"],
                }
            )

    write_rows(ROOT / "qualified_250.csv", primary, COLUMNS)
    write_rows(ROOT / "review_required.csv", review, COLUMNS)
    write_rows(ROOT / "excluded.csv", excluded, COLUMNS)
    write_rows(
        ROOT / "companies_master.csv",
        list(companies.values()),
        [
            "Company",
            "Website",
            "City",
            "State",
            "Industry",
            "Approximate Company Size Evidence",
            "Company Phone",
            "Qualification Status",
            "Signals In File",
        ],
    )
    write_rows(
        ROOT / "owners_master.csv",
        list(owners.values()),
        [
            "Owner Full Name",
            "Owner First Name",
            "Owner Last Name",
            "Owner Title",
            "Ownership Verified",
            "Owner LinkedIn",
            "Owner Email",
            "Owner Phone",
            "Company",
            "Company Phone",
        ],
    )
    write_rows(
        ROOT / "source_log.csv",
        sources,
        ["Company", "Role", "Source URL", "Source Title", "Signal Date", "Research Date"],
    )

    by_cat = Counter(r["Signal Type"] for r in qualified_rows)
    by_ind = Counter(r["Industry"] for r in primary)
    by_city = Counter(r["City"] for r in primary)
    domains = Counter()
    for row in rows:
        for url in (row["Source URL"], row["Secondary Source URL"]):
            d = domain(url)
            if d:
                domains[d] += 1
    verified_owners = {
        r["Owner Full Name"]
        for r in rows
        if r.get("Ownership Verified") == "Yes" and r.get("Owner Full Name")
    }
    phones = {r["Company"] for r in rows if r.get("Company Phone")}
    progress = {
        "research_date": RESEARCH_DATE,
        "target_qualified": 250,
        "signals_discovered": len(rows),
        "signals_qualified_rows": len(qualified_rows),
        "signals_qualified_primary_companies": len(primary),
        "signals_excluded": len(excluded),
        "signals_requiring_review": len(review),
        "unique_companies": len(companies),
        "verified_owners": len(verified_owners),
        "companies_with_company_phone": len(phones),
        "signals_by_category_qualified_rows": dict(by_cat),
        "signals_by_industry_qualified_primary": dict(by_ind),
        "signals_by_city_qualified_primary": dict(by_city),
        "source_domains_on_recorded_signals": dict(domains),
        "qualified_gap": 250 - len(primary),
        "note": (
            "Only records with a dated observable event, Central Iowa fit, and a verified "
            "individual owner are in qualified_250.csv. One underlying event is one signal. "
            "One strongest signal per company is in the primary file. The count is not padded."
        ),
    }
    progress["jeremy_sample"] = (
        "jeremy_vos_sample.csv is a call and mail sheet for Jeremy Vos. "
        "A row is not Florida-complete unless a sourced mobile, company phone, and verified owner email are all present. "
        "None of the current rows meet that bar. Emails and mobiles are blank when they were not printed on a public page."
    )
    (ROOT / "progress.json").write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    write_jeremy_sample(rows)
    print(json.dumps({k: progress[k] for k in (
        "signals_discovered",
        "signals_qualified_primary_companies",
        "signals_requiring_review",
        "signals_excluded",
        "qualified_gap",
    )}, indent=2))
    print("qualified companies:")
    for row in primary:
        print("-", row["Company"])


if __name__ == "__main__":
    rebuild()
