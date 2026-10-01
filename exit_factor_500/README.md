# Greater Des Moines blue-collar companies for Exit Factor

Current target: 100 distinct Greater Des Moines field-trade companies that each have a verified current owner. There is no revenue requirement and no revenue search. A row in `priority_100.csv` is accepted only when a public page supports the identity, a real street address, the trade, and a current full-name owner. Owner, co-owner, "owned by," majority shareholder, or managing member counts. Founder, co-founder, president, or CEO alone does not. A historical ownership change does not count unless the page says that person owns it now. A blank owner is unfinished research and stays out of this file. Published phones are business numbers. A business email is not labeled as the owner's email unless the page says so. Nothing in the priority file says a company needs to sell.

`priority_100.csv` and `owner_ready.csv` currently hold 56 coordinator-checked companies, all with a verified current owner and a published business phone. Shortfall versus 100 is 44. The verified-owner checkpoint is `checkpoints/owners_verified_current.csv`. Earlier company-only checkpoints remain in `checkpoints/priority_0010.csv`, `checkpoints/priority_0025.csv`, and `checkpoints/priority_0050.csv`. Companies that failed the owner gate are in `research/`, including `research/priority_100_before_owner_gate.csv`. Counts are in `priority_progress.json`.

The first pass used 50 workers and published 50 company-qualified rows, 27 of them with an owner label. Three of those 27 failed this re-audit: Elder Corporation (a 2000 majority-owner timeline), Fisher Construction (founder only), and Housby (truck dealer). A later 100-task public-web pass added the other accepted owners after the cited page was checked. All 100 task files are on disk. The Waukee excavation, Norwalk excavation, and Altoona concrete files name companies and streets, and they do not name a current owner, so those rows stay out of the final file.

The sections below describe the earlier discovery pass. That pass looked for a sourced $1 million revenue figure, found none, and is not the current qualification rule.

Research date: 2026-10-01. Elapsed time for the discovery pass: 1558.8 seconds (2026-10-01T02:46:19Z to 2026-10-01T03:12:17Z).

This folder is a company list, separate from `exit_factor_250/`. In that earlier pass, a row was revenue-qualified only when a public source stated annual revenue or annual sales of at least $1 million, or a clearly attributed third-party estimate did. Employee counts, fleets, permit volume, and Iowa DOT work classes are operating scale, not revenue. A project value is not annual revenue.

## Counts

| Bucket | Count |
| --- | ---: |
| Discovered (all rows) | 2663 |
| Revenue-qualified | 0 |
| Likely scale, revenue unverified | 30 |
| Review required | 2512 |
| Excluded | 121 |
| Shortfall versus 500 revenue-qualified | 500 |

Rows were not added to close that gap. Geography stayed on the Des Moines metro and the nearby Central Iowa cities listed in `progress.json`.

1949 rows were found only in Yellow Pages trade categories. The other rows come from Iowa DOT prequalification, the Mechanical Contractors Association of Iowa, AGC of Iowa, the Home Builders Association of Greater Des Moines, the Greater Des Moines Partnership, the Iowa Nursery and Landscape Association, or earlier public-source notes. A directory listing is not annual revenue.

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

Exit Factor's Des Moines page (`https://exitfactor.com/offices/des-moines/`) returned a Cloudflare challenge on 2026-10-01. A 2026-02-14 archive of that URL exposes the public program paths for exit-planning support, the process page, and a business-valuation calculator. The fit sentence on each row is a potential fit around business value, profitability, systems, management depth, or succession. It is not a sourced statement that the company currently wants that help. Dated events are copied only when a source states them. Nothing here infers distress, burnout, retirement, or an intent to sell.

## Contacts

`Public Company Phone` is a published office or main business number. No number is labeled a mobile line. `Public Business Email` is a published business address, including Cloudflare-decoded addresses printed on the HBA directory. Those addresses were not guessed, and they are not treated as an owner's personal inbox.

## Sources

Iowa DOT prequalified contractors, Mechanical Contractors Association of Iowa, AGC of Iowa, Home Builders Association of Greater Des Moines, Greater Des Moines Partnership category directory, Yellow Pages Des Moines trade categories, and the Iowa Nursery and Landscape Association. Company homepages were fetched only to look for an explicit revenue or employee statement. Paid enrichment APIs were not used.

ABC of Iowa's public directory page did not contain a member list. The NECA Local 347 page was password-protected. PHCC and one roofing association page were blocked. Those sources were skipped.
