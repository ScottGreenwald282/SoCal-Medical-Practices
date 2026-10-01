#!/usr/bin/env python3
"""Build the Greater Des Moines blue-collar company file from public directories."""

import csv
import json
import re
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/workspace/exit_factor_500")
RAW = ROOT / "raw"
CHECK = ROOT / "checkpoints"
RESEARCH_DATE = "2026-10-01"
STARTED = "2026-10-01T02:46:19Z"

# Nearby Central Iowa, not a statewide fill. City is always stored as published.
CORE_CITIES = {
    "DES MOINES", "WEST DES MOINES", "ANKENY", "URBANDALE", "CLIVE", "WAUKEE",
    "JOHNSTON", "ALTOONA", "BONDURANT", "PLEASANT HILL", "NORWALK", "INDIANOLA",
    "GRIMES", "ADEL", "DALLAS CENTER", "PERRY", "BOONE", "AMES", "NEVADA",
    "HUXLEY", "STORY CITY", "NEWTON", "WINTERSET", "CARLISLE", "POLK CITY",
    "GRANGER", "MITCHELLVILLE", "ELKHART", "COLFAX", "PRAIRIE CITY",
    "WINDSOR HEIGHTS", "CUMMING", "VAN METER", "DE SOTO", "DESOTO", "EARLHAM",
    "MADRID", "WOODWARD", "OGDEN", "SLATER", "GILBERT", "ROLAND", "KNOXVILLE",
    "PELLA", "PANORA", "STUART", "GUTHRIE CENTER", "BROOKLYN", "COLO",
    "MAXWELL", "ALLEMAN", "SHELDAHL", "MINBURN", "REDFIELD", "DEXTER",
    "MARTENSDALE", "HARTFORD", "RUNNELLS", "CAMBRIDGE", "KELLEY", "LUTHER",
    "BERWICK", "SAYLORVILLE", "MONROE", "BAXTER", "MINGO", "PRAIRIE CITY",
    "ST CHARLES", "BEVINGTON", "ACKWORTH", "SANDYVILLE", "PATTERSON",
}

COLUMNS = [
    "Company",
    "Website",
    "Domain",
    "City",
    "State",
    "Industry",
    "Revenue Amount Or Range",
    "Revenue Evidence Type",
    "Revenue Source URL",
    "Operating Scale Evidence",
    "Owner Name",
    "Owner Title",
    "Ownership Source",
    "Public Company Phone",
    "Public Business Email",
    "Fit Rationale",
    "Observed Signal",
    "Signal Date",
    "Signal Source",
    "Qualification Status",
    "Research Date",
    "Notes",
]

NATIONAL = re.compile(
    r"\b(lennar|d\.?\s*r\.?\s*horton|pulte|meritage|toll brothers|united rentals|"
    r"sunbelt rentals|home depot|lowe'?s|waste management|republic services|"
    r"builders firstsource|ferguson|84 lumber|menards|cemex|martin marietta|"
    r"knife river|oldcastle|vulcan materials|quanta services|emcor|"
    r"johnson controls|sherwin-williams|century 21|re/max|coldwell banker|"
    r"keller williams|berkshire hathaway|abc supply|owens corning|certainteed|"
    r"james hardie|beacon roofing|wells fargo|state farm|allstate insurance|"
    r"gaf\b|carrier corporation|general mills|andersen window|nucor|"
    r"graphic packaging|arcosa|fidium|renewable energy group|john deere)\b",
    re.I,
)
WHITE = re.compile(
    r"\b(law firm|attorney|insurance|bank|accounting|cpa|realty|realtor|"
    r"real estate|mortgage|title company|engineering|architect|survey|"
    r"staffing|marketing agency|advertising|software|financial|wealth|"
    r"dental|medical|clinic|church|nonprofit|foundation|law)\b",
    re.I,
)
TRADE_CAT = re.compile(
    r"asphalt|paving|grading|underground|utilit|ready mix|concrete|structure|"
    r"surfacing|specialty|erosion|cement|sand|gravel|transport|truck|"
    r"bridge|culvert|excav|hvac|plumb|electric|roof|mechanical|landscape|"
    r"builder|remodel|demolit|sewer|fence|paint|drywall|mason|restor|"
    r"machine|fabricat|weld|millwork|manufactur|heating|cooling|siding|"
    r"gutter|insulat|flooring|cabinet|septic|waterproof|excavat",
    re.I,
)
FRANCHISE = re.compile(
    r"\b(roto-?rooter|mr\.?\s*rooter|benjamin franklin|one hour heat|"
    r"1-tom plumber|ace handyman|stanley steemer|servpro|service experts|"
    r"servicemaster|paul davis|belfor|rainbow international|mister sparky|"
    r"mr\.?\s*electric|mr\.?\s*handyman|two men and a truck|college hunks|"
    r"aire serv|ars rescue|rescue rooter|u\.?s\.?\s*lawns|"
    r"molly maid|merry maids|chem-dry|servicemaster)\b",
    re.I,
)
GOV = re.compile(
    r"\b(public works|school district|city of |county of |state of iowa|"
    r"iowa department|department of transportation|group home)\b",
    re.I,
)
PLATFORM_HOSTS = {
    "facebook.com", "instagram.com", "linkedin.com", "yelp.com", "yellowpages.com",
    "superpages.com", "angi.com", "homeadvisor.com", "bbb.org", "google.com",
    "youtube.com", "twitter.com", "x.com", "mapquest.com", "wixsite.com",
    "godaddysites.com", "square.site", "business.site", "sites.google.com",
    "yp.com", "nextdoor.com", "localsearch.com", "citysearch.com", "ypcdn.com",
}
MAJOR_QUAL = re.compile(
    r"\b(BRIDGE|PCC|HMA|HOT MIX|GRADING|STRUCTURE|CULVERT|CONCRETE PAVEMENT|"
    r"PORTLAND CEMENT|SEWER|DEMOLITION|EXCAVAT)\b",
    re.I,
)
MINOR_ONLY = re.compile(
    r"fenc|traffic control|pavement marking|seeding|mulch|mowing|sign\b|"
    r"miscellaneous|flagger",
    re.I,
)

ESOP_NAMES = {
    "baker group",
    "story construction",
    "united contractors",
    "united contractors inc",
    "woodruff construction",
    "cemen tech",
    "lbs",
}
ACQUIRED = {
    "metro heating cooling": "Acquired by Merit Management Group; no longer an independent owner-led company.",
    "dorrian heating cooling": "Acquired by Merit Management Group; no longer an independent owner-led company.",
    "heartland heating cooling": "Acquired by Merit Management Group; no longer an independent owner-led company.",
    "swan creek cabinetry": "Acquired by Merit Management Group; no longer an independent owner-led company.",
    "clow valve": "McWane subsidiary, not an independent local owner.",
    "origin homes": "Subsidiary of Hubbell Realty Co.; no individual owner named.",
}


def norm_name(name):
    s = unescape(name or "")
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip(" -")
    legal = ""
    dba = re.search(r"\b(?:d/?b/?a)\b\s+(.+)$", s, re.I)
    if dba:
        legal = s
        s = dba.group(1).strip()
    s = re.sub(r"\s+[–—-]\s+.*$", "", s)
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    key = s.lower()
    key = key.replace("&", " and ")
    key = re.sub(r"\b(incorporated|corporation|company|inc|llc|l\.l\.c|co|corp|ltd|the)\b", " ", key)
    key = re.sub(r"[^a-z0-9]+", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return s, key, legal


def domain_of(url):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"https?://", url, re.I):
        url = "https://" + url
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"", "members.agcia.org", "www.dsmhba.com", "dsmhba.com", "members.dsmpartnership.com"}:
        return ""
    if host in PLATFORM_HOSTS or any(host.endswith("." + h) for h in PLATFORM_HOSTS):
        return ""
    return host


def clean_phone(phone):
    if not phone:
        return ""
    phone = unescape(phone).strip()
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return phone
    return f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"


def decode_cfemail(hexstr):
    try:
        raw = bytes.fromhex(hexstr)
    except ValueError:
        return ""
    if len(raw) < 2:
        return ""
    key = raw[0]
    return "".join(chr(b ^ key) for b in raw[1:])


def fit(industry, city, signal):
    base = (
        f"Potential fit only. Exit Factor's Des Moines office is built around exit-planning support, "
        f"a defined process, and a business-valuation calculator "
        f"(https://exitfactor.com/offices/des-moines/; live page was Cloudflare-blocked on {RESEARCH_DATE}; "
        f"the 2026-02-14 archive of that URL exposes those program paths). "
        f"An independent {industry.lower()} company in {city} is a plausible conversation about business value, "
        f"profitability, systems, management depth, or succession. This is not a sourced current need."
    )
    if signal:
        base += " The observed event below is an operating fact. It is not evidence of an ownership change."
    return base


def blank():
    return {c: "" for c in COLUMNS}


class Store:
    def __init__(self):
        self.rows = []
        self.by_key = {}
        self.by_domain = {}
        self.sources = []
        self.checkpoint_n = 0

    def add_source(self, company, role, url, title):
        self.sources.append(
            {
                "Company": company,
                "Role": role,
                "Source URL": url,
                "Source Title": title,
                "Research Date": RESEARCH_DATE,
            }
        )

    def checkpoint(self):
        n = len(self.rows)
        mark = (n // 50) * 50
        if mark >= 50 and mark > self.checkpoint_n:
            path = CHECK / f"companies_{mark-49:04d}_{mark:04d}.csv"
            write_csv(path, self.rows[mark - 50:mark], COLUMNS)
            self.checkpoint_n = mark
            print("checkpoint", path.name, mark)

    def upsert(self, row):
        display, key, legal = norm_name(row["Company"])
        if not key or len(key) < 3:
            return
        row["Company"] = display
        if legal and legal.lower() not in (row.get("Notes") or "").lower():
            row["Notes"] = ((row.get("Notes") or "") + f" Directory name included a DBA; legal name: {legal}.").strip()
        row["Research Date"] = RESEARCH_DATE
        st = (row.get("State") or "IA").upper().strip()
        row["State"] = "IA" if st in {"IA", "IOWA", ""} else st
        if row.get("City"):
            row["City"] = norm_city(row["City"]).title()
        dom = domain_of(row.get("Website") or "")
        row["Domain"] = dom or row.get("Domain") or ""
        if row.get("Public Company Phone"):
            row["Public Company Phone"] = clean_phone(row["Public Company Phone"])
            note = "Published business phone. The source did not label it a mobile line."
            row["Notes"] = (row.get("Notes") or "").strip()
            if note not in row["Notes"]:
                row["Notes"] = (row["Notes"] + " " + note).strip()
        if row.get("Public Business Email"):
            note = "Published business contact email. Not verified as the owner's personal inbox."
            row["Notes"] = (row.get("Notes") or "").strip()
            if note not in row["Notes"]:
                row["Notes"] = (row["Notes"] + " " + note).strip()
        if not row.get("Fit Rationale"):
            row["Fit Rationale"] = fit(row.get("Industry") or "trade", row.get("City") or "Central Iowa", row.get("Observed Signal"))
        existing = self.by_key.get(key)
        if existing is None and row["Domain"]:
            existing = self.by_domain.get(row["Domain"])
        if existing is None:
            self.rows.append(row)
            self.by_key[key] = row
            if row["Domain"]:
                self.by_domain[row["Domain"]] = row
            self.checkpoint()
            return
        # Fill blanks; do not overwrite a stronger status with a weaker one.
        rank = {"EXCLUDED": 0, "REVIEW_REQUIRED": 1, "LIKELY_SCALE": 2, "REVENUE_QUALIFIED": 3}
        for col in COLUMNS:
            if col in {"Company", "Qualification Status", "Research Date", "Notes", "Fit Rationale"}:
                continue
            if not existing.get(col) and row.get(col):
                existing[col] = row[col]
        if row["Qualification Status"] == "EXCLUDED" or rank.get(row["Qualification Status"], 0) > rank.get(existing["Qualification Status"], 0):
            existing["Qualification Status"] = row["Qualification Status"]
        if row.get("Notes") and row["Notes"] not in (existing.get("Notes") or ""):
            existing["Notes"] = ((existing.get("Notes") or "") + " " + row["Notes"]).strip()
        if row["Domain"] and not existing.get("Domain"):
            existing["Domain"] = row["Domain"]
            self.by_domain[row["Domain"]] = existing
        self.by_key[key] = existing


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def norm_city(city):
    c = (city or "").upper().replace(".", "").replace(",", "").strip()
    c = re.sub(r"\s+", " ", c)
    c = re.sub(r"\bSAINT\b", "ST", c)
    return c


def city_ok(city, state):
    st = (state or "").upper().strip()
    if st in {"IOWA"}:
        st = "IA"
    if st not in {"IA"}:
        return False
    return norm_city(city) in CORE_CITIES


def parse_agc(store):
    src = "https://members.agcia.org/active-member-directory"
    for i in range(26):
        html = Path(f"/tmp/ef500/agc/{i:02d}.html").read_text(errors="ignore")
        cards = re.split(r'<div class="card gz-directory-card', html)[1:]
        for card in cards:
            name_m = re.search(r'itemprop="name">\s*<a[^>]*>([^<]+)</a>', card)
            if not name_m:
                continue
            name = unescape(name_m.group(1)).strip()
            city = ""
            state = ""
            cm = re.search(r'itemprop="addressLocality">([^<]+)', card)
            sm = re.search(r'itemprop="addressRegion">([^<]+)', card)
            if cm:
                city = unescape(cm.group(1)).strip().rstrip(",")
            if sm:
                state = unescape(sm.group(1)).strip()
            phone = ""
            pm = re.search(r'itemprop="telephone">([^<]+)', card)
            if pm:
                phone = unescape(pm.group(1)).strip()
            website = ""
            wm = re.search(r'gz-card-website[\s\S]*?<a href="([^"]+)"', card)
            if wm:
                website = unescape(wm.group(1)).replace("&quot;", "")
            cats = [unescape(c).strip() for c in re.findall(r'class="gz-cat[^"]*">([^<]+)', card)]
            cat_text = "; ".join(dict.fromkeys(cats))
            row = blank()
            row.update(
                {
                    "Company": name,
                    "Website": website,
                    "City": city,
                    "State": state,
                    "Industry": industry_from_cats(cat_text) or "Construction",
                    "Revenue Evidence Type": "none",
                    "Public Company Phone": phone,
                    "Qualification Status": "REVIEW_REQUIRED",
                    "Notes": f"AGC of Iowa member categories: {cat_text}." if cat_text else "AGC of Iowa member directory.",
                }
            )
            apply_gates(store, row, src, "AGC of Iowa active member directory")


def industry_from_cats(cat_text):
    t = cat_text.lower()
    if "ready mix" in t or "concrete" in t:
        return "Concrete"
    if "asphalt" in t or "paving" in t or "surfacing" in t:
        return "Asphalt paving"
    if "grading" in t or "underground" in t:
        return "Excavation and underground utilities"
    if "structure" in t or "bridge" in t:
        return "Structures and heavy construction"
    if "transport" in t or "truck" in t:
        return "Trucking"
    if "erosion" in t:
        return "Erosion control"
    if "sand" in t or "gravel" in t or "cement" in t:
        return "Aggregates and cement"
    if "specialty" in t:
        return "Specialty trade contractor"
    return ""


def apply_gates(store, row, source_url, source_title):
    name = row["Company"]
    _, key, _legal = norm_name(name)
    if NATIONAL.search(name) or FRANCHISE.search(name):
        row["Qualification Status"] = "EXCLUDED"
        row["Notes"] = (row.get("Notes") or "") + " Excluded as a national chain, national brand, or franchise."
        store.add_source(name, "directory", source_url, source_title)
        if city_ok(row["City"], row["State"]):
            store.upsert(row)
        return
    if GOV.search(name):
        row["Qualification Status"] = "EXCLUDED"
        row["Notes"] = (row.get("Notes") or "") + " Excluded as a government or public agency."
        if city_ok(row["City"], row["State"]):
            store.add_source(name, "directory", source_url, source_title)
            store.upsert(row)
        return
    if key in ESOP_NAMES or any(key.startswith(n + " ") or key == n for n in ESOP_NAMES):
        row["Qualification Status"] = "EXCLUDED"
        row["Notes"] = (row.get("Notes") or "") + " Excluded as employee-owned; no individual owner to attach."
        if city_ok(row["City"], row["State"]):
            store.add_source(name, "directory", source_url, source_title)
            store.upsert(row)
        return
    for ak, reason in ACQUIRED.items():
        if ak in key:
            row["Qualification Status"] = "EXCLUDED"
            row["Notes"] = (row.get("Notes") or "") + " " + reason
            if city_ok(row["City"], row["State"]):
                store.add_source(name, "directory", source_url, source_title)
                store.upsert(row)
            return
    cats = row.get("Notes") or ""
    if (WHITE.search(name) and not TRADE_CAT.search(name)) or (
        re.search(r"law", row.get("Domain") or row.get("Website") or "", re.I) and not TRADE_CAT.search(name)
    ):
        row["Qualification Status"] = "EXCLUDED"
        row["Notes"] = cats + " Excluded as white-collar or outside the trade list based on the published name or website."
        if city_ok(row["City"], row["State"]):
            store.add_source(name, "directory", source_url, source_title)
            store.upsert(row)
        return
    if not city_ok(row["City"], row["State"]):
        return
    # AGC associate-only professional categories
    if "AGC of Iowa member categories:" in cats:
        cat_part = cats.split("AGC of Iowa member categories:", 1)[-1]
        if not TRADE_CAT.search(cat_part) and WHITE.search(cat_part):
            row["Qualification Status"] = "EXCLUDED"
            row["Notes"] = cats + " Excluded because the AGC categories are professional services, not field trades."
    store.add_source(name, "directory", source_url, source_title)
    store.upsert(row)


def parse_hba(store):
    files = list(Path("/tmp/ef500/hba").glob("b*.html")) + list(Path("/tmp/ef500/hba").glob("r*.html"))
    for path in files:
        kind = "Home builder" if path.name.startswith("b") else "Remodeling contractor"
        html = path.read_text(errors="ignore")
        items = re.findall(
            r'<h3><a href="([^"]+)">([^<]+)</a></h3>\s*<address>(.*?)</address>[\s\S]*?href="tel:([^"]+)"[\s\S]*?data-cfemail="([0-9a-f]+)"',
            html,
            re.I,
        )
        for href, name, address, tel, cf in items:
            name = unescape(name)
            address = unescape(re.sub(r"<br\s*/?>", ", ", address))
            address = re.sub(r"\s+", " ", address).strip()
            city, state = "", "IA"
            m = re.search(r",?\s*([A-Za-z .]+),\s*IA\b", address)
            if m:
                city = m.group(1).strip()
            email = decode_cfemail(cf)
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""):
                email = ""
            contact = ""
            if "–" in name or "&#" in name:
                parts = re.split(r"\s+[–—-]\s+", unescape(name), maxsplit=1)
                if len(parts) == 2 and len(parts[1].split()) <= 4:
                    name, contact = parts
            row = blank()
            row.update(
                {
                    "Company": name,
                    "Website": href if "dsmhba.com/members/" not in href else "",
                    "City": city,
                    "State": state,
                    "Industry": kind,
                    "Revenue Evidence Type": "none",
                    "Public Company Phone": tel,
                    "Public Business Email": email,
                    "Qualification Status": "REVIEW_REQUIRED",
                    "Notes": f"Home Builders Association of Greater Des Moines {kind.lower()} listing. Address: {address}."
                    + (f" Listing contact name: {contact}. Not recorded as a verified owner." if contact else ""),
                }
            )
            src = "https://www.dsmhba.com/members/?mt[0]=Builder+Members" if kind.startswith("Home") else "https://www.dsmhba.com/members/?mt[0]=Remodeler+Members"
            apply_gates(store, row, src, "HBA of Greater Des Moines member directory")


def parse_mca(store):
    text = Path("/tmp/src/mca_lines.txt").read_text(errors="ignore")
    blocks = re.split(r"\n\s*\n", text)
    # File is line-oriented without consistent blank lines. Parse by member-type markers.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    i = 0
    types = {"Contractor Member", "Affiliate Member"}
    while i < len(lines):
        if i + 1 < len(lines) and lines[i + 1] in types:
            name = lines[i]
            mtype = lines[i + 1]
            j = i + 2
            chunk = []
            while j < len(lines) and not (j + 1 < len(lines) and lines[j + 1] in types):
                chunk.append(lines[j])
                j += 1
            city = state = phone = website = ""
            for line in chunk:
                cm = re.search(r"^(.+),\s*([A-Z]{2})\s+\d", line)
                if cm and not city:
                    city = cm.group(1).strip()
                    state = cm.group(2)
                elif re.match(r"^[\d().\-\s]{7,}$", line) and not phone:
                    phone = line
                elif line.startswith("www.") or line.startswith("http"):
                    website = line
            if mtype == "Affiliate Member" and not TRADE_CAT.search(name):
                i = j
                continue
            row = blank()
            row.update(
                {
                    "Company": name,
                    "Website": website,
                    "City": city,
                    "State": state,
                    "Industry": "Mechanical contractor",
                    "Revenue Evidence Type": "none",
                    "Public Company Phone": phone,
                    "Qualification Status": "REVIEW_REQUIRED",
                    "Notes": f"Mechanical Contractors Association of Iowa {mtype.lower()}.",
                }
            )
            apply_gates(store, row, "https://www.mcaofiowa.org/member-directory/", "MCA of Iowa member directory")
            i = j
        else:
            i += 1


def parse_dot(store):
    data = json.loads(Path("/tmp/ef500/prequal.json").read_text())
    src = "https://www.iceasb.org/prequalified-contractors/"
    for rec in data["records"]:
        if not rec.get("active"):
            continue
        quals = rec.get("qualifications") or []
        if quals and isinstance(quals[0], dict):
            qnames = [q.get("name") or "" for q in quals]
        else:
            qnames = [str(q) for q in quals]
        qtext = "; ".join(dict.fromkeys(qnames))
        emails = rec.get("officialEmails") or []
        email = ""
        if emails:
            if isinstance(emails[0], dict):
                email = emails[0].get("email") or ""
            else:
                email = str(emails[0])
        major = any(MAJOR_QUAL.search(q) and "MINOR" not in q.upper() for q in qnames)
        only_minor = qnames and all(MINOR_ONLY.search(q) for q in qnames)
        row = blank()
        industry = "Highway and heavy construction"
        if any(re.search(r"FENC", q, re.I) for q in qnames) and not major:
            industry = "Fencing"
        row.update(
            {
                "Company": rec.get("name") or "",
                "City": (rec.get("city") or "").title(),
                "State": rec.get("state") or "",
                "Industry": industry,
                "Revenue Evidence Type": "none",
                "Operating Scale Evidence": (
                    f"Iowa DOT prequalified for: {qtext}."
                    if major
                    else ""
                ),
                "Public Company Phone": rec.get("phone") or "",
                "Public Business Email": email,
                "Qualification Status": "LIKELY_SCALE" if major and not only_minor else "REVIEW_REQUIRED",
                "Notes": f"Iowa DOT prequalification list retrieved {RESEARCH_DATE}. Work classes: {qtext}. "
                "Prequalification is not annual revenue. "
                + (f"Street: {rec.get('streetAddress') or ''}." if rec.get("streetAddress") else ""),
            }
        )
        if not major:
            row["Notes"] += " Work classes are not, by themselves, evidence of $1 million revenue."
        apply_gates(store, row, src, "Iowa DOT prequalified contractors")


def overlay_prior(store):
    path = Path("/workspace/exit_factor_250/signals_master.csv")
    if not path.exists():
        return
    with path.open(newline="", encoding="utf-8") as f:
        for old in csv.DictReader(f):
            _, key, _legal = norm_name(old["Company"])
            row = store.by_key.get(key)
            if row is None:
                # Add prior in-territory trade companies that directories missed.
                if not city_ok(old["City"], old["State"]):
                    continue
                if old["Industry"] and WHITE.search(old["Industry"]) and not TRADE_CAT.search(old["Industry"]):
                    continue
                row = blank()
                row["Company"] = old["Company"]
                row["Website"] = old.get("Website") or ""
                row["City"] = old["City"]
                row["State"] = old["State"]
                row["Industry"] = old["Industry"]
                row["Revenue Evidence Type"] = "none"
                row["Qualification Status"] = "REVIEW_REQUIRED"
                row["Public Company Phone"] = old.get("Company Phone") or ""
                apply_gates(store, row, old.get("Source URL") or "", old.get("Source Title") or "Prior Exit Factor research")
                row = store.by_key.get(key)
                if row is None:
                    continue
            if old.get("Company Phone") and not row.get("Public Company Phone"):
                row["Public Company Phone"] = clean_phone(old["Company Phone"])
            if old.get("Website") and not row.get("Website"):
                row["Website"] = old["Website"]
                row["Domain"] = domain_of(old["Website"])
            if old.get("Owner Full Name") and old.get("Ownership Verified") == "Yes" and not row.get("Owner Name"):
                row["Owner Name"] = old["Owner Full Name"]
                row["Owner Title"] = old.get("Owner Title") or ""
                row["Ownership Source"] = old.get("Source URL") or ""
            size = old.get("Approximate Company Size Evidence") or ""
            if size and not row.get("Operating Scale Evidence"):
                # Project dollars and employee counts are scale, not revenue.
                if re.search(r"\b\d+\+?\s+employees\b", size, re.I) or re.search(r"fleet|permits", size, re.I):
                    row["Operating Scale Evidence"] = size
                    if row["Qualification Status"] == "REVIEW_REQUIRED":
                        row["Qualification Status"] = "LIKELY_SCALE"
            if old.get("Qualification Status") == "QUALIFIED" and old.get("Signal Headline"):
                if not row.get("Observed Signal"):
                    row["Observed Signal"] = old["Signal Headline"]
                    row["Signal Date"] = old.get("Signal Date") or ""
                    row["Signal Source"] = old.get("Source URL") or ""
                    row["Fit Rationale"] = fit(row.get("Industry") or "trade", row.get("City") or "", row["Observed Signal"])
            if old.get("Qualification Status") == "EXCLUDED":
                reason = old.get("Exclusion Reason") or ""
                if re.search(r"employee-owned|ESOP|public|subsidiary|acquired", reason, re.I):
                    row["Qualification Status"] = "EXCLUDED"
                    row["Notes"] = ((row.get("Notes") or "") + " " + reason).strip()


def attach_dot_awards(store):
    path = Path("/tmp/tabs/central.json")
    if not path.exists():
        return
    data = json.loads(path.read_text())
    # central.json shape from the prior parser: list or dict
    rows = data if isinstance(data, list) else data.get("awards") or data.get("rows") or []
    if isinstance(data, dict) and not rows:
        # maybe vendor -> awards
        return
    for award in rows:
        if not isinstance(award, dict):
            continue
        name = award.get("vendor") or award.get("Vendor") or award.get("name") or ""
        amount = award.get("amount") or award.get("Prj Awd Amt") or award.get("award") or ""
        _, key, _legal = norm_name(str(name))
        row = store.by_key.get(key)
        if row is None:
            continue
        text = f"Iowa DOT award context: {name} {amount}."
        if text not in (row.get("Operating Scale Evidence") or ""):
            row["Operating Scale Evidence"] = ((row.get("Operating Scale Evidence") or "") + " " + text).strip()
        if row["Qualification Status"] == "REVIEW_REQUIRED" and re.search(r"\$\s*[1-9]\d{0,2}(?:,\d{3})+", str(amount)):
            row["Qualification Status"] = "LIKELY_SCALE"


YP_INDUSTRY = [
    ("heating-and-air", "HVAC"),
    ("air-conditioning", "HVAC"),
    ("heating-contractor", "HVAC"),
    ("plumber", "Plumbing"),
    ("electrician", "Electrical"),
    ("electrical-contractor", "Electrical"),
    ("roofing", "Roofing"),
    ("ready-mixed", "Concrete"),
    ("concrete", "Concrete"),
    ("excavation", "Excavation"),
    ("landscape", "Landscaping"),
    ("tree-service", "Tree service"),
    ("home-builder", "Home builder"),
    ("general-contractor", "General contractor"),
    ("building-contractor", "Construction"),
    ("remodel", "Remodeling contractor"),
    ("dump-truck", "Trucking"),
    ("trucking", "Trucking"),
    ("asphalt", "Asphalt paving"),
    ("paving", "Asphalt paving"),
    ("painter", "Painting"),
    ("fire-water", "Restoration"),
    ("water-damage", "Restoration"),
    ("restoration", "Restoration"),
    ("demolition", "Demolition"),
    ("masonry", "Masonry"),
    ("drywall", "Drywall"),
    ("insulation", "Insulation"),
    ("septic", "Septic systems"),
    ("welding", "Welding"),
    ("machine-shop", "Machine shop"),
    ("sheet-metal", "Sheet metal"),
    ("siding", "Siding"),
    ("foundation", "Foundation"),
    ("mechanical", "Mechanical contractor"),
    ("cabinet", "Cabinetry"),
    ("gutter", "Gutters"),
    ("steel-fabricat", "Steel fabrication"),
    ("waterproof", "Waterproofing"),
    ("crane", "Crane service"),
    ("well-drilling", "Well drilling"),
    ("pump-repair", "Industrial maintenance"),
    ("industrial-equipment", "Industrial maintenance"),
    ("grading", "Excavation"),
    ("flooring", "Flooring"),
    ("garage", "Garage doors"),
    ("countertop", "Countertops"),
]


def industry_from_filename(name):
    for slug, industry in YP_INDUSTRY:
        if slug in name:
            return industry
    return "Field trade"


def industry_from_name(name):
    n = name.lower()
    pairs = [
        ("plumb", "Plumbing"), ("hvac", "HVAC"), ("heat", "HVAC"), ("cool", "HVAC"),
        ("electric", "Electrical"), ("roof", "Roofing"), ("landscap", "Landscaping"),
        ("lawn", "Landscaping"), ("concrete", "Concrete"), ("excavat", "Excavation"),
        ("paint", "Painting"), ("restor", "Restoration"), ("remodel", "Remodeling contractor"),
        ("paving", "Asphalt paving"), ("asphalt", "Asphalt paving"), ("truck", "Trucking"),
        ("weld", "Welding"), ("mechanical", "Mechanical contractor"), ("septic", "Septic systems"),
        ("home", "Home builder"), ("build", "Construction"), ("construct", "Construction"),
    ]
    for word, industry in pairs:
        if word in n:
            return industry
    return "Field trade"


CHAMBER_INDUSTRY = {
    "967": "Plumbing", "744": "Electrical", "818": "HVAC", "1016": "Roofing",
    "679": "Concrete", "762": "Excavation", "864": "Landscaping", "870": "Landscaping",
    "823": "Home builder", "1002": "Remodeling contractor", "801": "General contractor",
    "674": "Commercial construction", "896": "Mechanical contractor", "937": "Painting",
    "605": "Asphalt paving", "677": "Trucking", "906": "Trucking", "728": "Restoration",
    "1135": "Restoration", "1262": "Manufacturing", "583": "Manufacturing",
    "590": "Manufacturing", "641": "Manufacturing", "826": "Home manufacturing",
    "1123": "Manufacturing", "1143": "Manufacturing", "1192": "Industrial equipment",
    "689": "Utility contractor", "1048": "Sheet metal", "767": "Fabrication",
    "1052": "Siding", "848": "Insulation", "773": "Fencing", "931": "Garage doors",
    "1166": "Flooring", "654": "Tile", "701": "Countertops", "1168": "Glass",
    "802": "Geothermal", "902": "Millwork", "747": "Elevators", "812": "Handyman",
    "1074": "Specialty trade contractor", "1024": "Aggregates", "1165": "Construction management",
    "880": "Building materials", "892": "Building materials", "786": "Construction",
    "859": "Kitchen and bath", "1288": "Windows",
}


def parse_chamber(store):
    files = sorted(Path("/tmp/ef500/chambers").glob("cat_*.html"), key=lambda p: p.stem in {"cat_1233", "cat_1234", "cat_1262"})
    for path in files:
        cid = path.stem.replace("cat_", "")
        industry = CHAMBER_INDUSTRY.get(cid, "Construction")
        html = path.read_text(errors="ignore")
        for block in re.split(r'class="mn-listing ', html)[1:]:
            nm = re.search(r'class="mn-title"[^>]*>\s*<a[^>]*>([^<]+)', block)
            if not nm:
                continue
            city = ""
            cm = re.search(r'addressLocality[^>]*>([^<]+)', block)
            if cm:
                city = unescape(cm.group(1))
            state = "IA"
            sm = re.search(r'addressRegion[^>]*>([^<]+)', block)
            if sm:
                state = unescape(sm.group(1)).strip()
            phone = ""
            pm = re.search(r'class="mn-phone"[^>]*>([^<]+)', block)
            if pm:
                phone = unescape(pm.group(1))
            row = blank()
            row.update({
                "Company": unescape(nm.group(1)),
                "City": city,
                "State": state,
                "Industry": industry,
                "Revenue Evidence Type": "none",
                "Public Company Phone": phone,
                "Qualification Status": "REVIEW_REQUIRED",
                "Notes": f"Greater Des Moines Partnership member directory, category id {cid}. Membership is not annual revenue.",
            })
            apply_gates(
                store,
                row,
                f"https://members.dsmpartnership.com/list/search?c={cid}",
                "Greater Des Moines Partnership member directory",
            )


def parse_yp(store):
    skip = {"plumbers.html", "sp.html", "gdmp.html"}
    for path in sorted(Path("/tmp/ef500/yp").glob("*.html")):
        if path.name in skip:
            continue
        html = path.read_text(errors="ignore")
        if html.startswith("ERROR") or "business-name" not in html:
            continue
        title = ""
        tm = re.search(r"<title>([^<]+)", html, re.I)
        if tm:
            title = tm.group(1)
        if "Manufactured Homes" in title:
            continue
        industry = industry_from_filename(path.name)
        for card in re.split(r'<a class="business-name"', html)[1:]:
            nm = re.search(r'>(?:<span>)?([^<]+)', card)
            href = re.search(r'href="(/[^"]+)"', card)
            if not nm or not href:
                continue
            city = ""
            adr = re.search(r'class="adr"[^>]*>([\s\S]*?)</div>', card)
            if adr:
                plain = re.sub(r"<[^>]+>", " ", adr.group(1))
                m = re.search(r"([A-Za-z][A-Za-z .]+),\s*IA\b", plain)
                if m:
                    city = m.group(1).split(",")[-1].strip()
            if not city:
                slug = re.search(r"/([a-z0-9-]+)-ia/", href.group(1))
                if slug:
                    city = slug.group(1).replace("-", " ")
            phone = ""
            pm = re.search(r"\(\d{3}\) \d{3}-\d{4}", card)
            if pm:
                phone = pm.group(0)
            website = ""
            for tag in re.findall(r"<a([^>]*)>\s*Website\s*</a>", card, re.I):
                if re.search(r"adclick(?:&quot;|\")\s*:\s*true", tag):
                    continue
                hm = re.search(r'href="(https?://[^"]+)"', tag)
                if hm:
                    website = unescape(hm.group(1))
                    break
            row = blank()
            row.update({
                "Company": unescape(nm.group(1)),
                "Website": website,
                "City": city,
                "State": "IA",
                "Industry": industry,
                "Revenue Evidence Type": "none",
                "Public Company Phone": phone,
                "Qualification Status": "REVIEW_REQUIRED",
                "Notes": "Yellow Pages Des Moines-area trade listing. A directory listing is not annual revenue. City is the city on the listing address when shown, otherwise the city in the listing URL.",
            })
            apply_gates(store, row, "https://www.yellowpages.com/des-moines-ia/", "Yellow Pages Des Moines trade listings")


def parse_inla(store):
    path = Path("/tmp/ef500/more/inla_all.html")
    if not path.exists():
        return
    html = path.read_text(errors="ignore")
    for block in re.split(r'<div class="listing-title">', html)[1:]:
        nm = re.search(r"<h3><a[^>]*>([^<]+)", block)
        if not nm:
            continue
        cat_m = re.search(r"wpbdp_category/([^/\"]+)/", block)
        cat = cat_m.group(1) if cat_m else ""
        if cat in {"individual", "honorary"}:
            continue
        city, state = "", "IA"
        adr = re.search(r"<div>([^<]*\d{5})</div>", block)
        if adr:
            m = re.search(r",\s*([^,]+),\s*([A-Z]{2})\s+\d", adr.group(1))
            if m:
                city, state = m.group(1), m.group(2)
        phone = ""
        pm = re.search(r'wpbdp-field-phone[\s\S]*?<div class="value">([^<]+)', block)
        if pm:
            phone = pm.group(1).strip()
        website = ""
        wm = re.search(r'wpbdp-field-website[\s\S]*?href="(https?://[^"]+)"', block)
        if wm:
            website = unescape(wm.group(1))
        row = blank()
        row.update({
            "Company": unescape(nm.group(1)),
            "Website": website,
            "City": city,
            "State": state,
            "Industry": "Landscaping",
            "Revenue Evidence Type": "none",
            "Public Company Phone": phone,
            "Qualification Status": "REVIEW_REQUIRED",
            "Notes": f"Iowa Nursery and Landscape Association directory, category {cat or 'unspecified'}. Membership is not annual revenue.",
        })
        apply_gates(store, row, "https://iowanla.org/directory/?wpbdp_view=all_listings", "Iowa Nursery and Landscape Association directory")


def parse_hba_trades(store):
    field = re.compile(
        r"plumb|heat|cool|hvac|electric|roof|landscap|lawn|excavat|concrete|construct|"
        r"build|remodel|restor|paint|fence|mason|drywall|cabinet|siding|gutter|insulat|"
        r"sewer|drain|mechanic|weld|truck|paving|asphalt|grading|septic|waterproof|"
        r"fabricat|floor|garage|millwork|home|nursery|irrigat|basement|excav",
        re.I,
    )
    for path in sorted(Path("/tmp/ef500/hba").glob("a*.html")):
        html = path.read_text(errors="ignore")
        items = re.findall(
            r'<h3><a href="([^"]+)">([^<]+)</a></h3>\s*<address>(.*?)</address>[\s\S]*?href="tel:([^"]+)"[\s\S]*?data-cfemail="([0-9a-f]+)"',
            html,
            re.I,
        )
        for href, name, address, tel, cf in items:
            name = unescape(name)
            if not field.search(name):
                continue
            address = unescape(re.sub(r"<br\s*/?>", ", ", address))
            address = re.sub(r"\s+", " ", address).strip()
            city = ""
            m = re.search(r",?\s*([A-Za-z .]+),\s*IA\b", address)
            if m:
                city = m.group(1).strip()
            email = decode_cfemail(cf)
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""):
                email = ""
            row = blank()
            row.update({
                "Company": name,
                "City": city,
                "State": "IA",
                "Industry": industry_from_name(name),
                "Revenue Evidence Type": "none",
                "Public Company Phone": tel,
                "Public Business Email": email,
                "Qualification Status": "REVIEW_REQUIRED",
                "Notes": f"Home Builders Association of Greater Des Moines member list. Address: {address}.",
            })
            apply_gates(store, row, "https://www.dsmhba.com/members/", "HBA of Greater Des Moines member directory")


REV_RE = re.compile(
    r"(?:annual\s+(?:revenue|sales)|(?:revenue|sales)\s+of|in\s+(?:annual\s+)?(?:revenue|sales))\s*\$?\s*([\d,.]+)\s*(million|billion)?",
    re.I,
)
REV_RE2 = re.compile(
    r"\$\s*([\d,.]+)\s*(million|billion)\s+(?:in\s+)?(?:annual\s+)?(?:revenue|sales)",
    re.I,
)
EMP_RE = re.compile(
    r"\b(?:(?:more than|over|nearly|about|approximately)\s+)?(\d{2,4})\s*\+?\s*(?:full[- ]time\s+)?employees\b"
    r"|\b(?:employs|employing|staff of|crew of|team of)\s+(\d{2,4})\b",
    re.I,
)
NOT_REVENUE = re.compile(r"project|awarded|contract|permit|investment|square foot|sq\.?\s*ft", re.I)


def html_text(html):
    html = re.sub(r"(?is)<script[\s\S]*?</script>", " ", html)
    html = re.sub(r"(?is)<style[\s\S]*?</style>", " ", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\s+", " ", text)


def money_phrase(num, unit):
    try:
        n = float(num.replace(",", ""))
    except ValueError:
        return ""
    if unit and unit.lower().startswith("b"):
        return f"${num} billion" if n > 0 else ""
    if unit and unit.lower().startswith("m"):
        return f"${num} million" if n >= 1 else ""
    if n >= 1_000_000:
        return f"${num}"
    return ""


def scan_sites(store, limit=400):
    cache = RAW / "sites"
    cache.mkdir(parents=True, exist_ok=True)
    by_domain = {}
    for row in store.rows:
        if row["Qualification Status"] == "EXCLUDED" or not row.get("Domain"):
            continue
        priority = 0 if "Yellow Pages" not in (row.get("Notes") or "") else 1
        current = by_domain.get(row["Domain"])
        if current is None or priority < current[0]:
            by_domain[row["Domain"]] = (priority, row)
    ordered = [row for _pri, row in sorted(by_domain.values(), key=lambda item: item[0])][:limit]

    def fetch(domain):
        path = cache / f"{domain}.html"
        if path.exists() and path.stat().st_size > 80:
            return domain, path.read_text(errors="ignore")
        text = ""
        for url in (f"https://{domain}/", f"https://www.{domain}/"):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=6) as resp:
                    raw = resp.read(350000)
                text = raw.decode("utf-8", "ignore")
                if "Just a moment" not in text and len(text) > 200:
                    break
            except Exception as exc:
                text = f"ERROR {exc}"
        path.write_text(text, encoding="utf-8")
        return domain, text

    found = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, row["Domain"]) for row in ordered]
        pages = {}
        for fut in as_completed(futures):
            domain, text = fut.result()
            pages[domain] = text
    for row in ordered:
        text = html_text(pages.get(row["Domain"]) or "")
        if not text or text.startswith("ERROR"):
            continue
        revenue_hit = ""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if NOT_REVENUE.search(sentence):
                continue
            m = REV_RE2.search(sentence) or REV_RE.search(sentence)
            if not m:
                continue
            phrase = money_phrase(m.group(1), m.group(2) or "")
            if phrase:
                revenue_hit = sentence.strip()[:280]
                row["Revenue Amount Or Range"] = phrase
                row["Revenue Evidence Type"] = "company website statement"
                row["Revenue Source URL"] = f"https://{row['Domain']}/"
                row["Qualification Status"] = "REVENUE_QUALIFIED"
                row["Notes"] = ((row.get("Notes") or "") + " Revenue figure is the company site's own wording, not an estimate.").strip()
                store.add_source(row["Company"], "revenue", f"https://{row['Domain']}/", "Company website")
                found += 1
                break
        if row["Qualification Status"] == "REVENUE_QUALIFIED":
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if re.search(r"client|customer|served|serving", sentence, re.I):
                continue
            em = EMP_RE.search(sentence)
            count = ""
            if em:
                count = next(g for g in em.groups() if g)
            if count and 20 <= int(count) <= 5000 and not row.get("Operating Scale Evidence"):
                row["Operating Scale Evidence"] = f"Company website says {count} employees. Quoted: {sentence.strip()[:220]}"
                if row["Qualification Status"] == "REVIEW_REQUIRED":
                    row["Qualification Status"] = "LIKELY_SCALE"
                store.add_source(row["Company"], "scale", f"https://{row['Domain']}/", "Company website employee count")
                break
    print("site scan domains", len(ordered), "revenue hits", found)


def write_readme(progress):
    text = f"""# Greater Des Moines blue-collar companies for Exit Factor

Research date: {RESEARCH_DATE}. Elapsed time from the start of this run: {progress['elapsed_seconds']} seconds ({progress['started_utc']} to {progress['finished_utc']}).

This folder is a company list, separate from `exit_factor_250/`. A row is revenue-qualified only when a public source states annual revenue or annual sales of at least $1 million, or a clearly attributed third-party estimate does. Employee counts, fleets, permit volume, and Iowa DOT work classes are operating scale, not revenue. A project value is not annual revenue.

## Counts

| Bucket | Count |
| --- | ---: |
| Discovered (all rows) | {progress['discovered']} |
| Revenue-qualified | {progress['revenue_qualified']} |
| Likely scale, revenue unverified | {progress['likely_scale']} |
| Review required | {progress['review_required']} |
| Excluded | {progress['excluded']} |
| Shortfall versus 500 revenue-qualified | {progress['revenue_qualified_shortfall']} |

Rows were not added to close that gap. Geography stayed on the Des Moines metro and the nearby Central Iowa cities listed in `progress.json`.

{progress['yellow_pages_only']} rows were found only in Yellow Pages trade categories. The other rows come from Iowa DOT prequalification, the Mechanical Contractors Association of Iowa, AGC of Iowa, the Home Builders Association of Greater Des Moines, the Greater Des Moines Partnership, the Iowa Nursery and Landscape Association, or earlier public-source notes. A directory listing is not annual revenue.

## Files

- `companies_master.csv` — every discovered company, one row each
- `qualified_companies.csv` — revenue-qualified only
- `likely_scale.csv` — operating-scale evidence, revenue unverified
- `review_required.csv` — local trade companies without scale or revenue evidence
- `excluded.csv` — chains, franchises, government, white-collar, ESOPs, and acquired companies that appeared in the local sources
- `source_log.csv` — source URL for each kept company
- `checkpoints/` — snapshots every 50 companies during the build
- `progress.json` — counts and sources

## Fit

Exit Factor's Des Moines page (`https://exitfactor.com/offices/des-moines/`) returned a Cloudflare challenge on {RESEARCH_DATE}. A 2026-02-14 archive of that URL exposes the public program paths for exit-planning support, the process page, and a business-valuation calculator. The fit sentence on each row is a potential fit around business value, profitability, systems, management depth, or succession. It is not a sourced statement that the company currently wants that help. Dated events are copied only when a source states them. Nothing here infers distress, burnout, retirement, or an intent to sell.

## Contacts

`Public Company Phone` is a published office or main business number. No number is labeled a mobile line. `Public Business Email` is a published business address, including Cloudflare-decoded addresses printed on the HBA directory. Those addresses were not guessed, and they are not treated as an owner's personal inbox.

## Sources

Iowa DOT prequalified contractors, Mechanical Contractors Association of Iowa, AGC of Iowa, Home Builders Association of Greater Des Moines, Greater Des Moines Partnership category directory, Yellow Pages Des Moines trade categories, and the Iowa Nursery and Landscape Association. Company homepages were fetched only to look for an explicit revenue or employee statement. Paid enrichment APIs were not used.

ABC of Iowa's public directory page did not contain a member list. The NECA Local 347 page was password-protected. PHCC and one roofing association page were blocked. Those sources were skipped.
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def main():
    t0 = time.time()
    RAW.mkdir(parents=True, exist_ok=True)
    CHECK.mkdir(parents=True, exist_ok=True)
    for old in CHECK.glob("companies_*.csv"):
        old.unlink()
    store = Store()
    parse_dot(store)
    print("after dot", len(store.rows))
    parse_mca(store)
    print("after mca", len(store.rows))
    parse_agc(store)
    print("after agc", len(store.rows))
    parse_hba(store)
    print("after hba", len(store.rows))
    parse_hba_trades(store)
    print("after hba trades", len(store.rows))
    parse_chamber(store)
    print("after chamber", len(store.rows))
    parse_inla(store)
    print("after inla", len(store.rows))
    parse_yp(store)
    print("after yp", len(store.rows))
    overlay_prior(store)
    print("after prior", len(store.rows))
    attach_dot_awards(store)
    scan_sites(store, limit=400)

    # Final checkpoint of the full discovered set.
    write_csv(CHECK / "companies_full_pass.csv", store.rows, COLUMNS)

    counts = Counter(r["Qualification Status"] for r in store.rows)
    qualified = [r for r in store.rows if r["Qualification Status"] == "REVENUE_QUALIFIED"]
    likely = [r for r in store.rows if r["Qualification Status"] == "LIKELY_SCALE"]
    review = [r for r in store.rows if r["Qualification Status"] == "REVIEW_REQUIRED"]
    excluded = [r for r in store.rows if r["Qualification Status"] == "EXCLUDED"]
    write_csv(ROOT / "companies_master.csv", store.rows, COLUMNS)
    write_csv(ROOT / "qualified_companies.csv", qualified, COLUMNS)
    write_csv(ROOT / "likely_scale.csv", likely, COLUMNS)
    write_csv(ROOT / "review_required.csv", review, COLUMNS)
    write_csv(ROOT / "excluded.csv", excluded, COLUMNS)
    write_csv(
        ROOT / "source_log.csv",
        store.sources,
        ["Company", "Role", "Source URL", "Source Title", "Research Date"],
    )
    ended_dt = datetime.now(timezone.utc)
    ended = ended_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    started_dt = datetime.fromisoformat(STARTED.replace("Z", "+00:00"))
    progress = {
        "started_utc": STARTED,
        "finished_utc": ended,
        "elapsed_seconds": round((ended_dt - started_dt).total_seconds(), 1),
        "research_date": RESEARCH_DATE,
        "target_revenue_qualified": 500,
        "discovered": len(store.rows),
        "revenue_qualified": len(qualified),
        "likely_scale": len(likely),
        "review_required": len(review),
        "excluded": len(excluded),
        "revenue_qualified_shortfall": 500 - len(qualified),
        "yellow_pages_only": sum(
            1 for r in store.rows
            if "Yellow Pages" in (r.get("Notes") or "")
            and "Partnership" not in (r.get("Notes") or "")
            and "Association" not in (r.get("Notes") or "")
            and "AGC of Iowa" not in (r.get("Notes") or "")
            and "Iowa DOT" not in (r.get("Notes") or "")
        ),
        "geography": sorted(CORE_CITIES),
        "sources": [
            "https://www.iceasb.org/prequalified-contractors/",
            "https://www.mcaofiowa.org/member-directory/",
            "https://members.agcia.org/active-member-directory",
            "https://www.dsmhba.com/members/",
            "https://members.dsmpartnership.com/list/search",
            "https://www.yellowpages.com/des-moines-ia/",
            "https://iowanla.org/directory/?wpbdp_view=all_listings",
            "https://exitfactor.com/offices/des-moines/",
            "/workspace/exit_factor_250 prior public-source research",
        ],
        "note": (
            "REVENUE_QUALIFIED requires a sourced revenue or attributed estimate of at least $1 million. "
            "LIKELY_SCALE uses employees, fleet, permit volume, or substantial DOT work classes and is not revenue. "
            "Directory listings without scale evidence stay REVIEW_REQUIRED. "
            "Phones are published business numbers and were not labeled mobiles. "
            "Rows were not manufactured to reach 500."
        ),
    }
    (ROOT / "progress.json").write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    write_readme(progress)
    print(json.dumps({k: progress[k] for k in ("discovered", "revenue_qualified", "likely_scale", "review_required", "excluded", "revenue_qualified_shortfall", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
