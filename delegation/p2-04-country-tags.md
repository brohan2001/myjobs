# p2-04-country-tags
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-04-country-tags` (already checked out)

## Goal
Tag every company in `data/companies.csv` with its headquarters country (ISO-3166 alpha-2) and, for Indian companies, its Indian HQ city. This drives the coverage dashboard and region ranking.

## Files you may touch
- `data/company_tags.csv` (new). Do NOT edit `data/companies.csv` directly; the orchestrator merges your file.

## Contract
- Header exactly: `slug,country,hq_city,company_type,confidence`, with one row per slug in `data/companies.csv` (2,882 rows; read the slugs from that file, plus `name` and `website` to identify the company).
- `country`: ISO2 code of global HQ (US, GB, DE, IN, FR, NL, CA, IL, SG, AU, CH, SE, …). Leave it empty if you don't know. Never guess wildly.
- `hq_city`: only when country is IN. One of Bengaluru, Hyderabad, Pune, Mumbai, Thane, Chennai, Delhi, Gurugram, Noida, Kolkata, Ahmedabad, Kochi, Jaipur, Chandigarh, Other. Otherwise empty.
- `company_type`: one of startup, product, mnc, services, nonprofit, government, or empty.
- `confidence`: high, medium or low.
- The website TLD is a hint, not proof (.io/.ai/.com say nothing). Use your knowledge of the company.
- Work through the whole file in batches; don't stop early. Write rows as you go.

## Acceptance
- `python3 -c "import csv;a={r['slug'] for r in csv.DictReader(open('data/companies.csv'))};b=list(csv.DictReader(open('data/company_tags.csv')));print(len(b), len(a-{r['slug'] for r in b}))"` prints `2882 0` (all slugs covered).
- Every country value is empty or a valid ISO2 code; hq_city is only set when country is IN.
- Commit with message `data: HQ country/city tags for registry companies` and the line `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"rows": N, "by_country_top10": {...}, "india_count": N, "confidence": {"high":N,"medium":N,"low":N}, "unsure": [...]}
