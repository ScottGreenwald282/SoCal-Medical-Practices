# Greater Des Moines blue-collar companies for Exit Factor

Research date: 2026-10-01. Elapsed time from the start of this run: 1558.8 seconds (2026-10-01T02:46:19Z to 2026-10-01T03:12:17Z).

This folder is a company list, separate from `exit_factor_250/`. A row is revenue-qualified only when a public source states annual revenue or annual sales of at least $1 million, or a clearly attributed third-party estimate does. Employee counts, fleets, permit volume, and Iowa DOT work classes are operating scale, not revenue. A project value is not annual revenue.

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
