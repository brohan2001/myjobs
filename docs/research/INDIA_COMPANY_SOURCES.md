# Lawful Public Sources of Indian Company Lists

> **Web Access Status:** Web access was enabled and actively utilized for this research. All citations, URLs, statutory references, and Terms of Service (ToS) restrictions reflect live platform policies and regulatory frameworks as of October 2026.

---

## 1. Overview & Regulatory Context

Building a candidate registry of employers in India requires navigating diverse company tiers: early-stage venture-backed startups, unicorns, mid-size product SaaS companies, publicly traded tech enterprises, and global capability centres (GCCs).

Unlike jurisdictions with open corporate registries (such as the UK Companies House open API), Indian company records and business intelligence platforms operate under strict legal and contractual boundaries:

1. **Information Technology Act, 2000 (Section 43 & Section 66):** Penalizes unauthorized extraction, copying, or downloading of data from computer systems without permission of the owner.
2. **Contract Law & Terms of Service (Indian Contract Act, 1872):** Browse-wrap and click-wrap Terms of Service that restrict automated scraping or programmatic indexing are generally enforceable contractual obligations in India.
3. **Database Rights and Copyright:** While factual business listings alone lack copyright in some jurisdictions, original selection, curation, verification, and commentary (as seen in Tracxn, Inc42, and Crunchbase) are protected proprietary intellectual property.
4. **Lawful Approaches:** The compliant pipeline model consists of:
   - Using authorized public directories, investor portfolios, stock exchange index constituent files, and press releases for initial entity discovery (company name + canonical domain).
   - Resolving the company's own official website directly.
   - Detecting the underlying Applicant Tracking System (ATS) on the employer's own careers domain (e.g. Greenhouse, Lever, Ashby, Workday, SmartRecruiters), bypassing third-party job aggregators (Naukri, LinkedIn, Indeed, Instahyre, etc.).

---

## 2. Comparative Source Matrix

The table below summarizes the key public and commercial sources of Indian company data, their accessibility, contractual constraints, and suitability for candidate ingestion:

| Source | URL | What it lists | Licence / ToS Notes (Scraping / Reuse) | Usefulness & Fit for Registry |
| :--- | :--- | :--- | :--- | :--- |
| **DPIIT / Startup India** | [startupindia.gov.in](https://www.startupindia.gov.in/) | 140,000+ government-recognized startups across all sectors and Indian states | **Government Directory.** No public open API for bulk records on API Setu. ToS prohibits bulk automated data extraction. Periodic static extracts are published via RTI by third-party research portals (e.g., Dataful). | **Low-to-Medium.** Authoritative for legal existence, but noisy: majority are early micro-enterprises, non-tech, or lack software engineering hiring. |
| **NSE Indices (NIFTY IT & Digital)** | [niftyindices.com](https://www.niftyindices.com/) | Constituents of NIFTY IT, Nifty India Digital (top 30 digital firms), Nifty Midcap Tech | **Public for personal/informational use.** Constituents downloadable as CSV/PDF monthly. Direct scraping of `nseindia.com` is strictly rate-limited and Cloudflare/Akamai-blocked. Commercial redistribution requires data license. | **High (for listed product/services).** 100% verified entity details, corporate domains, and audited financials for ~40-60 major Indian tech firms. |
| **BSE India (BSE Teck & SME)** | [bseindia.com](https://www.bseindia.com/) | Listed software and tech firms on Bombay Stock Exchange, including BSE Teck and SME tech board | **Public market data.** Informational CSV downloads allowed. Automated crawling prohibited by robots.txt and site terms; commercial redistributors require BSE market feed agreements. | **High (for listed tier).** Reliable for discovering newly listed tech startups (e.g., Zaggle, FirstCry, MapmyIndia, Unicommerce). |
| **Inc42 (Unicorns & Trackers)** | [inc42.com](https://inc42.com/) | Indian Startup Unicorn Tracker (110+ unicorns), Soonicorn 50, Fast42, sectoral startup maps | **Proprietary Editorial Content ("Ideope IPR").** Terms explicitly forbid scrapers, bots, spiders, or automated data mining. Personal non-commercial reading only. | **High (for candidate seed list).** Excellent manual reference for Indian unicorns, soonicorns, and HQ cities (Bengaluru, NCR, Mumbai, etc.). |
| **Tracxn** | [tracxn.com](https://tracxn.com/) | Comprehensive database of 1M+ tech entities, "Minicorns", Soonicorns, Unicorns, and GCCs | **Commercial Subscription.** Strictly prohibited to scrape, robotically index, or download large datasets. Commercial APIs available under enterprise contracts. Violators face account bans and legal notice. | **High quality, but Restricted.** Industry gold standard for funding data, but unusable for direct scraping due to aggressive anti-bot protection and strict ToS. |
| **Crunchbase** | [crunchbase.com](https://crunchbase.com/) | Global startup database with deep India coverage, seed through Series F, acquisitions | **Strict Commercial Paywall.** Terms forbid automated access, bots, or scraping. Protected by Cloudflare. Official access via paid Crunchbase Enterprise API or CSV exports (capped per tier). | **High quality, but Restricted.** Best used via paid API or manual domain cross-referencing rather than automated scraping. |
| **NASSCOM / Zinnov GCC Reports** | [nasscom.in](https://nasscom.in/knowledge-center/publications) | 2,100+ Global Capability Centers (GCCs) in India; city clusters, industry verticals, tech focus | **Copyrighted Industry Reports.** High-level landscape reports downloadable as PDF. Directory databases proprietary. GCC names, entity hubs, and expansion announcements are public via press releases. | **Very High (for GCC tier).** GCCs employ >2.3M professionals with high engineering compensation. Essential for capturing multinational tech hubs. |
| **Y Combinator Startup Directory** | [ycombinator.com/companies](https://www.ycombinator.com/companies) | 170+ funded startups headquartered in or founded for India (e.g., Razorpay, Zepto, Groww, Meesho) | **Public Directory.** Allowed for lawful browsing. Standard robots.txt restrictions against aggressive crawling. | **Very High (for seed & high-growth).** Highly qualified tech employers. Nearly all use standard modern ATS (Greenhouse, Ashby, Lever). |
| **Peak XV Partners (Surge & Portfolio)** | [peakxv.com/companies](https://www.peakxv.com/companies) | 400+ investments across India and SEA; Surge seed cohorts; AI, FinTech, SaaS, Consumer | **Public Portfolio Directory.** Public marketing disclosure. Permitted for lawful manual review and reference; no bulk download endpoint provided. | **Very High.** Premier signal for high-growth Indian startups with legitimate capital, verified domains, and ongoing engineering hiring. |
| **Wikipedia (List of Unicorns)** | [en.wikipedia.org](https://en.wikipedia.org/wiki/List_of_unicorn_startup_companies) | Indicative global list of unicorns, with dedicated sections/tables for Indian tech unicorns | **Creative Commons CC BY-SA 4.0.** Free to reuse, adapt, and share with attribution. Available via Wikipedia Action API and Wikimedia dumps. | **High (legal clarity).** Completely open licence. Valuable for initial bootstrapping, though can lag by a few months on recent rounds or downrounds. |
| **Ministry of Corporate Affairs (MCA21)** | [mca.gov.in](https://www.mca.gov.in/) | Statutory registry of all incorporated Indian companies (LLPs, Private Ltd, Public Ltd) | **Statutory Public Registry.** Automated scraping prohibited. Paid fee-per-record master data query or official bulk access via MCA data agreements. | **Medium.** 100% legal truth for corporate names and CINs, but lacks tech stack, careers URLs, or recruitment context. |
| **Blume Ventures Portfolio** | [blume.vc/portfolio](https://blume.vc/portfolio) | Leading early-stage Indian VC portfolio (deeptech, SaaS, consumer, robotics) | **Public Portfolio Directory.** Permitted for public reference and informational viewing. | **High (early product/deep tech).** Excellent source for specialized hardware, spacetech, and deep tech candidates (e.g. GreyOrange, Spinny, Euler). |

---

## 3. Deep Dive into Key Sources

### 3.1 DPIIT & Startup India
- **Governing Body:** Department for Promotion of Industry and Internal Trade (Ministry of Commerce and Industry, Government of India).
- **URL:** `https://www.startupindia.gov.in/`
- **Data Coverage:** Over 140,000 recognized startups that meet criteria (incorporated < 10 years, turnover < ₹100 crore, working towards innovation/development).
- **Access & Restrictions:** The Startup India Ecosystem Map allows interactive discovery, but does not provide a public bulk query API. Automated crawling violates the portal's Terms of Service. Data platforms such as Dataful compile datasets from parliamentary answers and official Gazette notifications.
- **Suitability for Job Feed Registry:** *Low precision.* While recognition is official, many registered entities are non-technical or dormant. It requires substantial filtering before candidate ingestion.

### 3.2 National Stock Exchange (NSE) & BSE
- **URL:** `https://www.niftyindices.com/` | `https://www.bseindia.com/`
- **Key Indices:**
  - *NIFTY IT Index:* Top 10 listed IT firms (TCS, Infosys, Wipro, HCLTech, Tech Mahindra, LTIMindtree, Persistent, Coforge, Mphasis, Birlasoft).
  - *NIFTY India Digital Index:* Max 30 stocks representing the digital ecosystem (Zomato, Paytm, Nykaa, Policybazaar, Delhivery, Info Edge, IndiaMART, Just Dial, Affle, Nazara, Route Mobile, Tanla).
  - *BSE Teck & BSE SME:* Additional mid-cap and small-cap listed software product and engineering firms.
- **Access & Restrictions:** Monthly index constituent sheets (CSV format) are freely accessible on `niftyindices.com` for personal and non-commercial analysis. Automated high-frequency HTTP requests against `nseindia.com` trigger Cloudflare/WAF IP blocks.
- **Suitability for Job Feed Registry:** *Essential.* These firms have substantial engineering payrolls and stable corporate domains.

### 3.3 Inc42, Tracxn, and Crunchbase
- **Inc42 (`https://inc42.com/`):**
  - Maintains specialized trackers: *Indian Startup Unicorn Tracker*, *30 Startups To Watch*, *Soonicorn 50*.
  - ToS explicitly bans any "robot, spider, scraper, data mining or computer code". Use strictly as a research citation source.
- **Tracxn (`https://tracxn.com/`):**
  - Categorizes companies by "Soonicorn" (valuation $500M+), "Minicorn" ($100M+), and tracks GCC establishments in tier-1/tier-2 Indian cities.
  - Strictly proprietary; aggressive rate limiting and bot detection. Commercial usage requires the Tracxn API.
- **Crunchbase (`https://www.crunchbase.com/`):**
  - High coverage of funding announcements and executive contacts.
  - Automated crawling is disallowed via `robots.txt` and protected by Cloudflare. Programmatic access requires Enterprise REST API credentials.

### 3.4 NASSCOM & Zinnov GCC Landscape Reports
- **URL:** `https://nasscom.in/knowledge-center/publications`
- **Context:** India currently hosts **2,117 Global Capability Centers (GCCs)** across **3,728 units**, employing ~2.36 million people with an estimated economic value of $98.4 billion (FY2026 data).
- **Key Hubs:** Bengaluru accounts for ~29% of units and ~33% of talent, followed by Hyderabad (20%), Pune (14%), Mumbai/Thane (12%), Delhi-NCR (12%), and Chennai (10%).
- **Hiring Value:** GCCs represent some of the highest-paying engineering employers in India (e.g. Walmart Global Tech, Goldman Sachs, Target, Wells Fargo, Societe Generale, Lowe's, Mercedes-Benz R&D, Shell).
- **Access & Restrictions:** Full benchmark reports require NASSCOM membership or purchase. However, company setup announcements, facility inaugurations, and GCC names are routinely published in public press releases.

### 3.5 Venture Capital Portfolios (Peak XV, Surge, Y Combinator, Blume, Accel)
- **Portfolios:**
  - *Peak XV Partners & Surge:* `https://www.peakxv.com/companies` (400+ investments in India/SEA across AI, fintech, consumer, SaaS).
  - *Y Combinator:* `https://www.ycombinator.com/companies?regions=India` (170+ Indian companies).
  - *Blume Ventures:* `https://blume.vc/portfolio` (deep tech, SaaS, robotics).
- **Access & Restrictions:** These directories are published publicly by VC firms to showcase portfolio companies. Citing company names and domains from these marketing pages is legally permissible and carries no database exclusivity claims.
- **Suitability for Job Feed Registry:** *Highest signal.* Startups backed by tier-1 VCs have active capital, competitive hiring pipelines, and standardized ATS career pages.

### 3.6 Wikipedia Unicorn Lists
- **URL:** `https://en.wikipedia.org/wiki/List_of_unicorn_startup_companies`
- **Licence:** Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).
- **Suitability:** Completely unencumbered by restrictive ToS. Allows automated extraction via the Wikipedia API (`action=parse`). Cross-validation is recommended to account for recent market changes or downrounds.

---

## 4. Operational Recommendations for Registry Validation Pipeline

When the validation pipeline processes `data/candidates/india_companies.csv`:

1. **Direct Domain Verification:** Verify `website` responds with HTTP 200/301/302. Reject domains that are parked, expired, or redirect to generic third-party portals.
2. **First-Party Careers Page Resolution:**
   - Follow `careers_url` if provided.
   - If empty, inspect homepage headers, footers, and standard paths (`/careers`, `/jobs`, `/join-us`, `/work-with-us`).
3. **ATS Pattern Detection:** Look for standard ATS integrations:
   - **Greenhouse:** `boards.greenhouse.io/<token>` or embedded Greenhouse iframe/API.
   - **Ashby:** `jobs.ashbyhq.com/<token>`.
   - **Lever:** `jobs.lever.co/<token>`.
   - **Workable:** `apply.workable.com/<token>`.
   - **SmartRecruiters:** `careers.smartrecruiters.com/<token>`.
   - **Workday / Phenom People:** Common among large GCCs and listed firms.
4. **Third-Party Blacklist:** Maintain strict rejection of aggregator links (`naukri.com`, `linkedin.com`, `indeed.com`, `foundit.in`, `instahyre.com`, `cutshort.io`, `wellfound.com`).
5. **Polite Crawling Policies:** Respect robots.txt directives on candidate career pages, use descriptive User-Agent headers, and apply per-domain rate limiting.
