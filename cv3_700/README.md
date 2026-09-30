# CV3 Financial — net-new investor mortgage broker research

This folder is an evidence file for residential investor-loan brokers who can place 1–4 unit loans with outside lenders. It is not a calling list.

## What is in here

| File | Contents |
| --- | --- |
| `companies_master.csv` | Brokerages and lenders reviewed, with qualified, review, and excluded statuses |
| `people_master.csv` | Every person captured, including review and excluded records |
| `qualified_700.csv` | People who currently meet the qualification rules |
| `review_required.csv` | Real records that are not yet proven |
| `excluded.csv` | Rejected people, with the reason |
| `source_log.csv` | Public pages used |
| `progress.json` | Running counts |
| `scripts/build_dataset.py` | Rebuilds the CSVs from the evidence records |
| `scripts/merge_regional.py` | Checks regional notes against fetched pages and writes only page-backed rows |
| `raw/pages/` | Text extracted from public pages |

## Rules used

A person is qualified only when a fetched public page shows both of these:

- The company offers residential investor financing (DSCR, fix-and-flip, bridge, private money, or a similar business-purpose product).
- The company places loans with outside or wholesale lenders, or is a hybrid that still brokers to outside lenders.

The person must be a current owner or producing originator at that company. New York, North Dakota, and South Dakota are excluded. Direct lenders and the named competitors (Kiavi, RCN Capital, Anchor Loans, Civic Financial Services, and other direct funders found during research) are excluded.

Phones are `DNC_STATUS = NOT_YET_SCREENED`. No Do Not Call check was run. APIs, including DNC, enrichment, search-data, and scraping APIs, were not used. Pages were opened as ordinary public web pages.

Emails are recorded only when they were published. Nothing was invented.

## Prior CV3 workbook

The project brief says a prior workbook of about 1,935 delivered records would be in the project folder. That file is not in this repository. `Existing CV3 Duplicate Check` is `PRIOR_WORKBOOK_NOT_SUPPLIED`. Deduping inside this folder is done. Deduping against the earlier delivery cannot be completed until that workbook is added.

## Count

`progress.json` is the current count. The delivery target is 700 qualified net-new people. This checkout is a verified checkpoint and is short of that target. Research is continuing from public broker pages, state by state. Records are not padded to reach 700.

Rebuild the tables with:

```bash
python3 cv3_700/scripts/build_dataset.py
```
