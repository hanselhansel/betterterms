# 0003. Open decisions resolved for v1

Status: accepted. Date: 2026-10-03.

Resolves design spec section 13, items 2 to 5.

- Ledger in cloud sessions: cases are short-lived. Nothing syncs. The README says so.
- Opt-in response data: off, with no destination in v1.
- `ai-api` pack: pricing and contract terms only. Usage optimization (caching, batching, model
  choice) is out of scope.
- Comp data for job offers: user-supplied numbers plus cited public sources (posted ranges,
  public levels data with links). No scraping.

Item 1 (trademark and package names): USPTO knockout search on 2026-10-03 found no live
BETTERTERMS mark; two abandoned class 36 filings. npm and PyPI names unclaimed; claiming them is
pending account access. Items 6 and 7 are checked during the build and recorded separately.
