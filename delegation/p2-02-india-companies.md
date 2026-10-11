# p2-02-india-companies
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-02-india-companies` (already checked out)

## Goal
Produce a candidate list of Indian employers for our job-feed registry. A validation pipeline will later fetch each careers page, detect the ATS and keep only working boards. You only produce candidates; precision matters more than size.

## Files you may touch
- `data/candidates/india_companies.csv` (new)
- `docs/research/INDIA_COMPANY_SOURCES.md` (new)

## Contract
CSV header exactly: `name,website,careers_url,hq_city,category,source`
- `website`: the company's main https URL (homepage, not a job portal).
- `careers_url`: their own careers page if you're confident of it, otherwise empty. NEVER Naukri, LinkedIn, Indeed, foundit, Instahyre, Cutshort or Wellfound.
- `hq_city` is one of: Bengaluru, Hyderabad, Pune, Mumbai, Thane, Chennai, Delhi, Gurugram, Noida, Kolkata, Ahmedabad, Kochi, Jaipur, Chandigarh, Other.
- `category` is one of: unicorn, funded_startup, listed_product, mnc_gcc, mid_product, services.
- `source`: where you know it from (e.g. "Inc42 unicorn list 2025", "NSE IT index", "company GCC announcement").
- Target 400 rows covering all categories: Indian unicorns and soonicorns, notable funded startups (fintech, SaaS, consumer, deep tech), listed product/tech companies, global GCCs (global capability centres) in India (e.g. Walmart Global Tech, Target, Lowe's, JPMorgan, Goldman Sachs, Wells Fargo, Societe Generale, Shell, AB InBev, Mercedes-Benz R&D), and mid-size product firms. Include only a few large IT-services firms (TCS, Infosys, Wipro, HCLTech, Tech Mahindra, LTIMindtree) and mark them `services`.
- No duplicates by website domain. Only companies you're confident are real.

`docs/research/INDIA_COMPANY_SOURCES.md` covers lawful public sources of Indian company lists, with a table: source, URL, what it lists, licence/ToS notes (e.g. whether scraping or reuse is allowed), and usefulness. Cover at least: DPIIT/Startup India, NSE/BSE listings, Inc42/Tracxn/Crunchbase (note their restrictions), NASSCOM GCC reports, YC/Sequoia Surge/Peak XV portfolios, Wikipedia unicorn lists. If you have web access, use it and cite it; if not, say so at the top.

## Acceptance
- `python3 -c "import csv;r=list(csv.DictReader(open('data/candidates/india_companies.csv')));print(len(r))"` prints ≥ 300.
- Every row passes the field rules above.
- Commit with message `data: India company candidates + source survey` and the line `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed": [...], "rows": N, "by_category": {...}, "web_access": true/false, "unsure": [...]}
