#!/usr/bin/env python3
"""
Discover correct Workday site names for boards whose monitor_config has a wrong
"site" value (e.g., the generic placeholder "External").

Probes each company's robots.txt at:
  https://{company}.{wd_instance}.myworkdayjobs.com/robots.txt

and extracts Sitemap entries to find valid site names.

Usage:
  python scripts/fix_workday_sites.py          # dry run — print findings only
  python scripts/fix_workday_sites.py --apply  # update data/boards.csv in place

Run from project root.
"""
from __future__ import annotations

import asyncio
import csv
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

BOARDS_CSV = Path(__file__).parent.parent / "data" / "boards.csv"

# Same regex as src/core/monitors/workday.py
_SITEMAP_RE = re.compile(r"myworkdayjobs\.com/([^/]+)/siteMap", re.IGNORECASE)

# The 8 failing boards identified from scraping_status.json
FAILING_SLUGS = frozenset([
    "cohesity", "snyk", "goldmansachs", "akamai",
    "bnymellon", "fortinet", "intuit", "netapp",
])


async def _probe_robots(company: str, wd_instance: str, client: httpx.AsyncClient) -> list[str]:
    """Return site names found in robots.txt, or [] on failure."""
    url = f"https://{company}.{wd_instance}.myworkdayjobs.com/robots.txt"
    try:
        r = await client.get(url, timeout=15.0, follow_redirects=True)
        if r.status_code != 200:
            print(f"  robots.txt HTTP {r.status_code} for {company}", file=sys.stderr)
            return []
        sites = _SITEMAP_RE.findall(r.text)
        # Dedupe preserving order
        seen: set[str] = set()
        result: list[str] = []
        for s in sites:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result
    except Exception as e:
        print(f"  robots.txt error for {company}: {e}", file=sys.stderr)
        return []


async def main(apply: bool) -> None:
    with open(BOARDS_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())

    # Find the rows to fix
    targets: list[tuple[int, dict, dict]] = []
    for i, row in enumerate(rows):
        if row["company_slug"] in FAILING_SLUGS and row["monitor_type"] == "workday":
            cfg = json.loads(row["monitor_config"] or "{}")
            targets.append((i, row, cfg))

    print(f"Probing {len(targets)} Workday boards via robots.txt...\n")

    changed = 0
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        for idx, row, cfg in targets:
            slug = row["company_slug"]
            company = cfg.get("company", slug)
            wd_instance = cfg.get("wd_instance", "wd1")
            current_site = cfg.get("site", "External")

            sites = await _probe_robots(company, wd_instance, client)

            if not sites:
                print(f"  {slug:<20} No sites in robots.txt — keeping {current_site!r}")
                continue

            new_site = sites[0]
            all_sites_str = ", ".join(sites) if len(sites) > 1 else sites[0]

            if new_site == current_site:
                print(f"  {slug:<20} Unchanged: {current_site!r}  (robots.txt: {all_sites_str})")
                continue

            print(f"  {slug:<20} {current_site!r} → {new_site!r}  (all: {all_sites_str})")
            if apply:
                cfg["site"] = new_site
                rows[idx]["monitor_config"] = json.dumps(cfg)
                changed += 1

    if apply:
        with open(BOARDS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nUpdated {BOARDS_CSV} ({changed} rows changed)")
    else:
        print("\nDry run — run with --apply to write changes to data/boards.csv")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(main(apply=apply))
