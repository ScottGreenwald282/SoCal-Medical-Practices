# Worker rules

Read `../baseline_excluded.tsv` before writing a row. Skip every name on it, including aliases and duplicate locations. Do not use MacPro Restore or the other delivered names.

Find an event first, then match the exact local blue-collar business, then verify a current full-name owner, then a published business phone or email if one is printed. Use `python3 /tmp/fc_fetch.py search "query"` and `python3 /tmp/fc_fetch.py scrape "URL"`. At most 3 searches and 6 scrapes. Stop on budget_exhausted or http_429. Do not print secrets. Do not run git. Do not edit `priority_100.csv` or `qualified_signals.csv`. Write only your own CSV.

Owner evidence must say Owner, Co-Owner, owned by, majority shareholder, or managing member for a current full name. President, CEO, or founder alone is not enough. Do not invent dates, emails, or phones. Do not store a number labeled cell or mobile. Do not infer distress, burnout, retirement, or sale intent.

Geography: Greater Des Moines and nearby Central Iowa cities that operate in that market. Do not use Cedar Rapids, Iowa City, Waterloo, Dubuque, Sioux City, Council Bluffs, Ottumwa, Mason City, Fort Dodge, Marshalltown, or Oskaloosa to fill the file.

Signal types: expansion_facility, new_branch, acquisition_by_company, succession_handoff, new_management, capacity_or_fleet, owner_operations_comment. State whether the event is an announcement, completed, or ongoing. Separate publication date from event date. Date precision is day, month, or year. why_exit_factor is labeled inference and must not say the company needs to sell.

CSV header: company,canonical_website,city,state,trade,owner_name,owner_title,ownership_source_url,ownership_excerpt,business_phone,business_email,signal_type,event,event_date,date_precision,publication_date,signal_source_url,signal_source_title,evidence_excerpt,event_status,researched_date,why_exit_factor,personalized_opener,confidence,review_notes,baseline_duplicate_check

researched_date is 2026-10-01. baseline_duplicate_check is PASS only after the name was compared with the baseline file.
