"""Check that jobs jseek.co shows also appear in myjobs (DECISIONS D28).

    python scripts/jseek_parity.py                       # against the local API on :8090
    python scripts/jseek_parity.py --api http://127.0.0.1:8090 --cities bengaluru,pune

jseek.co's public search (robots.txt allows /api/v1) returns up to 5 companies × 3 postings per
query. The script runs a grid of Indian cities × tech occupations, collects every posting it
returns, then looks each one up in our public API by company and title. Misses are grouped:

- out of scope: a non-tech title we drop on purpose (D27);
- company missing: the company isn't in our registry;
- job missing: we track the company but don't have this job (stale or broken board).

Requests to jseek.co go one per second with an honest User-Agent. The full list is written to
``output/parity.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.tech_gate import is_tech_title, tech_occupations  # noqa: E402
from src.shared.http import HONEST_USER_AGENT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JSEEK = "https://jseek.co/api/v1"
SAMPLE = ROOT / "output" / "parity-jseek.json"  # reused by later runs; --refresh fetches a new one
API_PAUSE_S = 0.5  # stays under the API's default 120 requests per minute
CITIES = ["india", "bengaluru", "hyderabad", "pune", "chennai", "gurugram", "noida", "mumbai"]
OCCUPATIONS = [
    "software-engineer", "backend-developer", "frontend-developer", "fullstack-developer", "mobile-developer",
    "devops-engineer", "data-engineer", "data-scientist", "data-analyst", "ml-engineer", "ai-engineer",
    "qa-engineer", "security-engineer", "product-manager", "designer", "embedded-engineer",
]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def collect(cities: list[str], occupations: list[str]) -> list[dict]:
    """Every posting jseek.co returns for the city × occupation grid, deduplicated by id."""
    seen: dict[str, dict] = {}
    with httpx.Client(headers={"User-Agent": HONEST_USER_AGENT}, timeout=45) as client:
        for city in cities:
            for occ in occupations:
                try:
                    resp = client.get(f"{JSEEK}/search", params={"loc": city, "occ": occ, "lang": "en"})
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"  skip {city}/{occ}: {exc}", file=sys.stderr)
                    time.sleep(2)
                    continue
                for company in resp.json().get("companies", []):
                    for p in company.get("topPostings", []):
                        seen.setdefault(p["id"], {"company": company["slug"], "company_name": company["name"],
                                                  "title": p["title"], "location": p.get("location") or "",
                                                  "query": f"{city}/{occ}"})
                time.sleep(1)
    return list(seen.values())


def registry_slugs() -> set[str]:
    with (ROOT / "data" / "companies.csv").open(encoding="utf-8") as f:
        return {row["slug"] for row in csv.DictReader(f)}


def find(api: httpx.Client, posting: dict) -> bool:
    """Is there an active job at this company with the same title (normalised)?"""
    params = {"company": posting["company"], "q": posting["title"][:80], "limit": 50}
    while True:
        resp = api.get("/api/v1/jobs", params=params)
        if resp.status_code != 429:  # our API's per-IP rate limit
            break
        time.sleep(float(resp.headers.get("Retry-After", 5)))
    time.sleep(API_PAUSE_S)
    resp.raise_for_status()
    want = _norm(posting["title"])
    return any(_norm(j["title"]) == want for j in resp.json()["jobs"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://127.0.0.1:8090")
    ap.add_argument("--cities", default=",".join(CITIES))
    ap.add_argument("--occupations", default=",".join(OCCUPATIONS))
    ap.add_argument("--refresh", action="store_true", help="sample jseek.co again instead of reusing the last sample")
    args = ap.parse_args()
    unknown = set(args.occupations.split(",")) - tech_occupations()
    if unknown:
        sys.exit(f"not tech occupations (D27): {', '.join(sorted(unknown))}")

    if args.refresh or not SAMPLE.exists():
        postings = collect(args.cities.split(","), args.occupations.split(","))
        SAMPLE.parent.mkdir(exist_ok=True)
        SAMPLE.write_text(json.dumps(postings))
    else:
        postings = json.loads(SAMPLE.read_text())
    ours = registry_slugs()
    with httpx.Client(base_url=args.api, timeout=30) as api:
        for p in postings:
            if not is_tech_title(p["title"]):
                p["result"] = "out of scope"
            elif p["company"] not in ours:
                p["result"] = "company missing"
            else:
                p["result"] = "found" if find(api, p) else "job missing"

    counts = Counter(p["result"] for p in postings)
    in_scope = len(postings) - counts["out of scope"]
    print(f"jseek.co postings sampled: {len(postings)} ({in_scope} in scope)")
    for result in ("found", "job missing", "company missing", "out of scope"):
        print(f"  {result:16s} {counts[result]:5d}")
    if in_scope:
        print(f"parity: {counts['found'] / in_scope:.1%} of in-scope postings found")
    missing = Counter(p["company"] for p in postings if p["result"] in ("job missing", "company missing"))
    if missing:
        print("companies with the most misses:", ", ".join(f"{c} ({n})" for c, n in missing.most_common(15)))

    out = ROOT / "output" / "parity.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["result", "company", "company_name", "title", "location", "query"])
        w.writeheader()
        w.writerows(sorted(postings, key=lambda p: (p["result"], p["company"])))
    print(f"details: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
