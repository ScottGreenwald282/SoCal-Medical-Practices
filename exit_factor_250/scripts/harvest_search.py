#!/usr/bin/env python3
"""Harvest public search-engine result pages (DuckDuckGo HTML). No APIs."""
import json, re, time, urllib.parse, urllib.request
from html import unescape
from pathlib import Path

OUT = Path("/workspace/exit_factor_250/raw/search")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

QUERIES = [
    # succession / leadership
    '"Des Moines" contractor retirement OR succession OR "stepping down" OR "named president"',
    '"Des Moines" (HVAC OR plumbing OR electrical OR roofing) (owner OR founder) (retirement OR succession OR "next generation")',
    '"West Des Moines" OR Ankeny OR Urbandale contractor "family business" succession OR retirement',
    '"Des Moines" construction "hired" (COO OR "general manager" OR president) 2024 OR 2025 OR 2026',
    'Iowa contractor "succession" "Des Moines" OR Ankeny OR Waukee',
    # growth / facility
    '"Des Moines" (HVAC OR plumbing OR roofing OR electrical) ("new location" OR "second location" OR "new facility" OR "grand opening")',
    '"Des Moines" (contractor OR construction) ("new headquarters" OR "broke ground" OR "new building" OR expansion) 2024 OR 2025 OR 2026',
    'Ankeny (HVAC OR plumbing OR roofing OR electrical OR contractor) (expansion OR "new location" OR facility)',
    '"West Des Moines" (contractor OR HVAC OR plumbing OR roofing) (expansion OR acquisition OR "new location")',
    'Waukee OR Grimes OR Altoona OR Johnston contractor ("new location" OR expansion OR headquarters)',
    # acquisitions
    '"Des Moines" (acquired OR acquisition) (contractor OR HVAC OR plumbing OR electrical OR roofing OR construction)',
    'Iowa (HVAC OR plumbing OR "mechanical contractor" OR roofing) acquisition "Des Moines" OR Ankeny',
    '"joins" OR "acquired by" contractor "Des Moines" 2024 OR 2025 OR 2026',
    # hiring / growth
    '"Des Moines" (HVAC OR plumbing OR electrical OR roofing OR excavation) (hiring OR "now hiring" OR "adding" crews OR technicians) 2025 OR 2026',
    '"central Iowa" contractor (expansion OR growth OR "new division")',
    # home builders
    '"Des Moines" OR Ankeny OR Waukee ("home builder" OR homebuilder) (expansion OR community OR "new model" OR acquired)',
    # concrete excavation landscaping restoration
    '"Des Moines" (excavation OR concrete OR landscaping OR restoration) (expansion OR "new location" OR acquisition OR hired)',
    '"Des Moines" "mechanical contractor" OR "mechanical contracting" (expansion OR project OR hired OR acquisition)',
    # business record
    'site:businessrecord.com (HVAC OR plumbing OR roofing OR electrical OR contractor) (expansion OR acquisition OR hired OR opens)',
    'site:businessrecord.com "construction" (acquisition OR expansion OR "new" president OR facility)',
    'site:kcci.com (contractor OR HVAC OR construction) (Des Moines) (expansion OR new OR opens OR acquired)',
    'site:desmoinesregister.com (contractor OR HVAC OR plumbing) (expansion OR acquisition OR retirement OR hired)',
    'site:who13.com contractor OR construction "Des Moines" expansion OR business',
    # awards / projects as signals of major work
    '"Des Moines" contractor "awarded" OR "wins contract" OR "selected" (project OR construction) 2025 OR 2026',
    'Iowa "general contractor" "Des Moines" "million" project 2025 OR 2026',
    # more specific trades
    '"Des Moines" roofing (company OR contractor) (expansion OR acquired OR "new" OR hiring OR owner)',
    '"Des Moines" plumbing (company) (expansion OR "new location" OR acquired OR owner OR founder)',
    '"Des Moines" electrical contractor (expansion OR acquisition OR "new facility" OR hired)',
    '"Ames" Iowa (contractor OR HVAC OR plumbing OR construction) (expansion OR acquisition OR "new location" OR retirement)',
    'Indianola OR Norwalk OR Carlisle OR Newton Iowa contractor expansion OR "new shop" OR acquisition',
    # leadership pages / interviews
    '"owner of" (HVAC OR plumbing OR roofing OR electrical) "Des Moines" (expanding OR opened OR hired OR acquired)',
    '"founded" (HVAC OR plumbing) "Des Moines" (son OR daughter OR "next generation" OR retirement)',
    # facilities / fleet
    '"Des Moines" (contractor) ("new shop" OR "new warehouse" OR "fleet" OR "service trucks")',
    'Polk County Iowa contractor "groundbreaking" OR "ribbon cutting" OR "open house" 2025 OR 2026',
]

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")

def parse_ddg(html):
    results = []
    # result blocks
    blocks = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    if not blocks:
        blocks = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
        blocks = [(h, a, "") for h, a in blocks]
    for href, title, snip in blocks:
        href = unescape(href)
        if "uddg=" in href:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href if href.startswith("http") else "https:" + href).query)
            if "uddg" in q:
                href = q["uddg"][0]
        title = re.sub(r"<.*?>", "", unescape(title))
        snip = re.sub(r"<.*?>", "", unescape(snip))
        if href.startswith("http"):
            results.append({"url": href, "title": title.strip(), "snippet": snip.strip()})
    return results

def main():
    all_rows = []
    for i, q in enumerate(QUERIES):
        slug = re.sub(r'[^a-z0-9]+', '-', q.lower())[:80]
        path = OUT / f"{i:03d}-{slug}.json"
        if path.exists():
            rows = json.loads(path.read_text())
            print(f"cached {i} {len(rows)}")
            all_rows.extend(rows)
            continue
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
        try:
            html = fetch(url)
            rows = parse_ddg(html)
        except Exception as e:
            rows = []
            print("ERR", i, e)
        for r in rows:
            r["query"] = q
        path.write_text(json.dumps(rows, indent=2))
        print(f"{i:03d} {len(rows):2d} {q[:70]}")
        all_rows.extend(rows)
        time.sleep(1.1)
    # dedupe urls
    seen = {}
    for r in all_rows:
        u = r["url"].split("#")[0]
        if u not in seen:
            seen[u] = r
    summary = list(seen.values())
    (OUT / "_all_unique.json").write_text(json.dumps(summary, indent=2))
    print("UNIQUE", len(summary))

if __name__ == "__main__":
    main()
