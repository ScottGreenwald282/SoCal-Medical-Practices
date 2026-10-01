# Wave 2 research brief

Find 2 or 3 local field-trade companies for your assigned trade and cities. Write only your assigned CSV. Do not run git. Do not edit other files. Do not print API keys, tokens, or the contents of /tmp/fc_secret.

Use the shared cached fetcher, at most 2 searches and 6 scrapes:

- `python3 /tmp/fc_fetch.py search "your query"`
- `python3 /tmp/fc_fetch.py scrape "https://official-page"`

If the fetcher returns budget_exhausted, http_429, or another error, stop calling it and write the rows you can support. Prefer companies that are not already in /workspace/exit_factor_500/priority_100.csv.

Accept a company only when a public page shows a street address in your assigned cities, the business performs the assigned field trade, and you have an official website or a chamber/association page that names the company. A supplier, dealer, or manufacturer is not a trade contractor. A national chain branch or a company owned by a public parent is not a local owner prospect; note it and skip it. Franchise brands stay in the file only when a page names the local owner.

Owner name: use it only when the page gives a current full name and says Owner, Founder, Co-Founder, or Managing Member. A historical founder is not automatically the current owner. A first name alone is not enough; leave owner_name blank and say so in notes. President or CEO is not an owner title. Do not invent email, phone, mobile, revenue, or a need to sell. If a page labels a number Cell or mobile, do not put it in the phone column.

CSV header:

company,role,identity_verified,street_address,city,state,trade_verified,website,domain,owner_name,owner_title,ownership_status,ownership_evidence_url,ownership_excerpt,phone,email,contact_status,evidence_url,evidence_excerpt,accessed_date,notes

role is priority. identity_verified and trade_verified are YES or NO. ownership_status is OWNER_VERIFIED or OWNER_UNKNOWN. contact_status is PHONE_AND_EMAIL, PHONE_ONLY, EMAIL_ONLY, or NONE. state is IA. accessed_date is 2026-10-01. Excerpts are short quotes from the page you fetched.
