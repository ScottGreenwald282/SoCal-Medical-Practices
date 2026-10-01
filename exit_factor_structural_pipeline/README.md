# Structural ingestion pilot

Research date: 2026-10-01. Claude summarizer: unavailable.

This run is a partial Iowa Secretary of State name-prefix sample plus one business-number lookup. It is not a list of all active construction, specialty-trade, or manufacturing LLCs in Polk, Dallas, and Warren counties.

## Live counts

- Entities parsed: 50
- Filing-index or document changes: 6
- Those changes with a filing date in the last 12 months: 1
- Management jobs with an exact company match: 0
- Filing-change AND management-job intersection: 0
- Single-lane rows: 6
- Rejected or not-accepted rows: 160
- Owner-verified new companies: 0
- Shortfall versus 50 accepted companies: 50
- Biennial documents sampled: 2
- Sampled biennials with an officer, manager, or member roster: 0
- Registered-agent change documents read: 6
- Live source time recorded on the fetch counters: 1110.4 seconds
- Firecrawl local spend after the run: 780 of 4000

Search pages opened:

- PLUMBING: showed 1-25 of 1000; parser kept 25 rows
- ROOFING: showed 1-25 of 1000; parser kept 24 rows
- CONCRETE: showed 1-25 of 1000; parser kept 25 rows
- EXCAVAT: showed 1-25 of 1000; parser kept 24 rows
- HEATING: showed 1-25 of 1000; parser kept 19 rows
- WELDING: showed 1-25 of 886; parser kept 24 rows
- PAVING: showed 1-25 of 146; parser kept 25 rows

## What the sources actually returned

The HTML search has no county, industry, or formation-year filter. The public JSON schema also has no NAICS or county field. Entity JSON calls returned HTTP 401 without a subscription, and the subscription was not purchased.

The officers tab on the sampled entity was a current list and said none were on file. Two fields are required before OFFICER_ADDED, OFFICER_REMOVED, or OFFICER_ROLE_CHANGED can be emitted: a prior snapshot and a later snapshot with filing ids. Those snapshots were not on the officers tab.

The sampled LLC biennial report listed the registered agent, principal office, and an authorized signer. It did not list members, managers, or officers. Further biennial downloads stopped after that representative sample.

A Change of Registered Agent document can supply the previous agent name and the new agent name. That comparison is REGISTERED_AGENT_CHANGED. It is not an ownership transfer, and the agent is not recorded as the owner.

County is taken from the principal-office city when that city sits in only one of Polk, Dallas, or Warren. Registered-agent cities are not used. Split cities stay unresolved. Formation year comes from a certificate of organization or articles filing, not from the summary filing date alone.

Apify and Bright Data tokens were unset. Indeed actors in the Apify store are pay-per-result and were not run. No management-job row was created. The intersection is empty, so owner verification and openers were not started.

## Reproduce

```bash
pip install -r exit_factor_structural_pipeline/requirements.txt
PYTHONPATH=. python -m exit_factor_structural_pipeline pilot --max-details 50
PYTHONPATH=. python -m pytest exit_factor_structural_pipeline/tests
```

The Firecrawl key is read from the existing secret file outside the repository. Snapshots and checkpoint state stay in `exit_factor_structural_pipeline/cache/`, which is gitignored.

## Notes from this run

- Biennial A25753682 for 753682 has no officer, manager, or member roster.
- prefix PLUMBING showed 1-25 of 1000. Later pages were not opened. This is not all matching entities.
- Biennial A25694761 for 694761 has no officer, manager, or member roster.
- Stopped further biennial document downloads. 2 sampled LLC biennial reports had no officer, manager, or member roster.
- prefix ROOFING showed 1-25 of 1000. Later pages were not opened. This is not all matching entities.
- prefix CONCRETE showed 1-25 of 1000. Later pages were not opened. This is not all matching entities.
- prefix EXCAVAT showed 1-25 of 1000. Later pages were not opened. This is not all matching entities.
- prefix HEATING showed 1-25 of 1000. Later pages were not opened. This is not all matching entities.
- prefix WELDING showed 1-25 of 886. Later pages were not opened. This is not all matching entities.
- prefix PAVING showed 1-25 of 146. Later pages were not opened. This is not all matching entities.
- Stopped prefix searches at the 50-entity detail cap.
- Apify job actors were not run. APIFY_TOKEN is unset and the store actors found earlier are pay-per-result.
- Owner verification was not started. Openers are drafted only after a current full-name owner is verified, and only for the filing-change AND management-job intersection. Claude did not run.
- No parsed entity cleared the active LLC, 1985-2005 formation, and Polk, Dallas, or Warren principal-office screens. Company career pages were not searched. Formation years present in this first-page sample: 2005, 2008, 2009, 2010, 2011, 2014, 2015, 2016, 2017, 2018, 2020, 2021, 2022, 2023, 2024, 2025, 2026, unknown. The opened page was the first 25 rows of a larger result, and searches stop at 1,000 matches. That page is not a formation-year or county filter.
