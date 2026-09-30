# Exit Factor: Central Iowa owner-level signals

Research file for Accel Corporate Solutions. The target is 250 distinct, source-backed business signals tied to a verified owner of a privately held company in Central Iowa / Greater Des Moines.

This pass does not reach 250. The qualified file contains only records that survived the evidence test. The gap is recorded in `progress.json` and is not filled with company lists, anniversaries, or guessed sale intent.

## How a row gets into `qualified_250.csv`

1. A dated business event is found in a public source.
2. The company is a real private operator in or serving Greater Des Moines / Central Iowa, at a scale that is plausibly $1 million or more from operating evidence.
3. A current individual owner is verified. President or CEO is not treated as owner unless the source says so.
4. The event supports a plain-English Exit Factor conversation about complexity, management depth, systems, profitability, owner dependence, succession, or enterprise value.

One underlying event is one signal. One strongest signal per company is copied into `qualified_250.csv`. Extra events stay in `signals_master.csv`.

## Files

| File | Contents |
| --- | --- |
| `signals_master.csv` | Every researched signal, including review and excluded rows |
| `qualified_250.csv` | One strongest qualified signal per company |
| `review_required.csv` | Real events that still fail owner, geography, scale, or identity checks |
| `excluded.csv` | Events that were researched and rejected, with the reason kept |
| `companies_master.csv` | One row per company and its best status |
| `owners_master.csv` | Named people attached to a company |
| `source_log.csv` | Primary and secondary URLs |
| `progress.json` | Counts as of the research date |
| `scripts/rebuild_outputs.py` | Rebuilds the derived CSVs and `progress.json` from `signals_master.csv` |

## Current qualified companies

- Manatt's, Inc. (Brooklyn / Ankeny office): $12.4 million Polk County paving award, December 16, 2025 Iowa DOT letting. Brian Manatt, third-generation family partner.
- Beal Derkenne Construction (Des Moines): 515 Walnut tower topped out, August 12, 2026. Andy Beal, co-owner.
- Haverkamp Group (Ames): groundbreaking of the 387-unit Sloane in north Ankeny, reported September 16, 2026. Brent Haverkamp, founder and CEO.
- Strahan Construction (Ankeny): $1.5 million purchase of seven Polk City lots, recorded July 16, 2026. Reid Strahan, co-founder. Cindy Strahan is also a co-founder.

## What was kept out on purpose

- Employee-owned contractors (Baker Group, Story Construction, United Contractors, Woodruff Construction) have no individual owner to attach.
- Completed private-equity purchases of Metro, Dorrian, and Heartland Heating & Cooling, and of Swan Creek Cabinetry, do not leave a verified operating owner in the articles.
- Single custom-home closings (Black Birch, Prairieland) are ordinary builder work, not a new event.
- Vermeer (Bondurant groundbreaking, May 21, 2026) and Accumold (Ankeny expansion, September 18, 2026) are real events. Jason Andringa and Roger Hargens are family-company or founder-era chief executives in the sources read here, but those sources do not explicitly say they currently own the equity. Both stay in review.
- Jerry's Homes and Greenland Homes each have a reported $1.7 million, 18-lot Altoona purchase from Wolf Pack LLC, recorded six days apart. They stay in review until those deeds are shown to be different deals.
- Hubbell Realty leadership and the Edencrest sale are recorded only as context in the research notes inside other files where relevant. Kyle Gamble is president and CEO, not a verified owner.

## Method

Public pages only: company sites, Iowa DOT bid-tab PDFs, Business Record articles and its public RSS feed, and the Greater Des Moines Partnership story pages. No paid data source and no enrichment API was used. Search-engine HTML was tried and was mostly unusable from this environment because results were degraded or blocked. Business Record article pages and the RSS feed were readable.

Revenue is not estimated. Where a figure is unknown, the size column quotes operating evidence or says the scale was not established.

Research date on these rows: 2026-09-30.
