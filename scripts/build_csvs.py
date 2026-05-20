#!/usr/bin/env python3
"""Build data/companies.csv and data/boards.csv for the jobseek-based pipeline.

Sources:
  - /tmp/jobseek/apps/crawler/data/companies.csv  (4,405 companies)
  - /tmp/jobseek/apps/crawler/data/boards.csv     (5,000 boards)
  - /tmp/jobseek/apps/crawler/data/industries.csv (22 industry codes)
  - data/companies.json                            (our 102 curated companies)

Logic:
  1. Start with our 102 companies — all included regardless of industry.
  2. Add jobseek companies whose industry code is in TECH_INDUSTRY_IDS.
  3. For companies in our 102 that ARE in jobseek: use jobseek's board rows verbatim.
  4. For companies in our 102 NOT in jobseek: synthesize board rows from ats_type config.
  5. For new jobseek companies (not in our 102): use jobseek's board rows verbatim.
  6. Write data/companies.csv and data/boards.csv.

Usage:
    python3 scripts/build_csvs.py              # write CSVs
    python3 scripts/build_csvs.py --dry-run    # print summary only, no writes
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBSEEK_ROOT = Path("/tmp/jobseek/apps/crawler")

OUT_COMPANIES = PROJECT_ROOT / "data" / "companies.csv"
OUT_BOARDS = PROJECT_ROOT / "data" / "boards.csv"

TECH_INDUSTRY_IDS = {
    1,   # Technology
    2,   # Financial Services (fintech)
    6,   # Media & Entertainment (gaming/streaming)
    7,   # Telecommunications
    10,  # Education (edtech)
    15,  # Aerospace & Defense
    16,  # Automotive
    20,  # Robotics
    21,  # Cybersecurity
}

# Our slug → jobseek slug for companies with mismatched identifiers.
# Board rows are taken from jobseek using JOBSEEK_SLUG but written with OUR_SLUG.
SLUG_MAP: dict[str, str] = {
    "cockroachlabs": "cockroach-labs",
    "grafanalabs": "grafana-labs",
    "hubspotjobs": "hubspot",
    "pulumicorporation": "pulumi",
    "scaleai": "scale-ai",
    "temporaltechnologies": "temporal-technologies",
    "workday-co": "workday",
}

INDUSTRY_TEXT_TO_CODE: dict[str, int] = {
    "tech": 1,
    "fintech": 2,
    "enterprise": 1,
    "media": 6,
    "telecom": 7,
    "edtech": 10,
    "aerospace": 15,
    "automotive": 16,
    "robotics": 20,
    "cybersecurity": 21,
}

# ats_types with no jobseek monitor equivalent — logged as unmapped
UNMAPPED_ATS_TYPES = {"rippling", "serp"}


# ── Loaders ───────────────────────────────────────────────────────────────────


def _load_jobseek_companies() -> dict[str, dict]:
    """Return {slug: row} for all jobseek companies."""
    path = JOBSEEK_ROOT / "data" / "companies.csv"
    out: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["slug"]] = row
    return out


def _load_jobseek_boards() -> dict[str, list[dict]]:
    """Return {company_slug: [board_row, ...]} for all jobseek boards."""
    path = JOBSEEK_ROOT / "data" / "boards.csv"
    out: dict[str, list[dict]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["company_slug"], []).append(row)
    return out


def _load_myjobs_companies() -> list[dict]:
    path = PROJECT_ROOT / "data" / "companies.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Board synthesis for myjobs-only companies ─────────────────────────────────


def _wd_instance(host: str) -> str:
    m = re.search(r"\.(wd\d+)\.", host)
    return m.group(1) if m else "wd1"


def _synth_boards(c: dict) -> list[dict]:
    """Return synthesized board rows for a company not in jobseek."""
    slug = c["slug"]
    ats = c.get("ats_type", "")

    if ats == "greenhouse":
        token = c.get("greenhouse_slug", slug)
        return [_board(slug, f"{slug}-greenhouse",
                       f"https://job-boards.greenhouse.io/{token}",
                       "greenhouse", {"token": token}, "skip", {})]

    if ats == "lever":
        token = c.get("lever_slug", slug)
        return [_board(slug, f"{slug}-lever",
                       f"https://jobs.lever.co/{token}",
                       "lever", {"token": token}, "skip", {})]

    if ats == "ashby":
        token = c.get("ashby_slug", slug)
        return [_board(slug, f"{slug}-ashby",
                       f"https://jobs.ashbyhq.com/{token}",
                       "ashby", {"token": token}, "skip", {})]

    if ats == "workday":
        host = c.get("workday_host", "")
        board = c.get("workday_board", "")
        if not host or not board:
            return []
        wi = _wd_instance(host)
        board_url = f"https://{host}/{board}"
        mc = {"company": slug, "wd_instance": wi, "site": board}
        return [_board(slug, f"{slug}-workday", board_url,
                       "workday", mc, "workday", {})]

    if ats == "smartrecruiters":
        sr_id = c.get("sr_id", slug)
        return [_board(slug, f"{slug}-smartrecruiters",
                       f"https://careers.smartrecruiters.com/{sr_id}",
                       "smartrecruiters", {"token": sr_id}, "skip", {})]

    if ats == "workable":
        token = c.get("workable_slug", slug)
        return [_board(slug, f"{slug}-workable",
                       f"https://apply.workable.com/{token}/",
                       "workable", {"token": token}, "skip", {})]

    if ats == "oracle_cloud":
        host = c.get("orc_host", "")
        site = c.get("orc_site", "CX_1")
        if not host:
            return []
        board_url = (
            f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/requisitions"
        )
        mc = {"host": host, "site": site}
        sc = {"host": host, "site": site, "enrich": ["description"]}
        return [_board(slug, f"{slug}-oracle-hcm", board_url,
                       "oracle_hcm", mc, "oracle_hcm", sc)]

    if ats == "avature":
        avature_host = c.get("avature_host", "")
        if avature_host:
            sitemap_url = f"https://{avature_host}/careers/sitemap.xml"
            mc = {"sitemap_url": sitemap_url, "url_filter": "/job"}
            return [_board(slug, f"{slug}-avature-sitemap",
                           f"https://{avature_host}/careers",
                           "sitemap", mc, "json-ld", {})]
        return []

    # rippling, serp, and any unknown type — no jobseek equivalent
    return []


def _board(
    company_slug: str,
    board_slug: str,
    board_url: str,
    monitor_type: str,
    monitor_config: dict,
    scraper_type: str,
    scraper_config: dict,
) -> dict:
    return {
        "company_slug": company_slug,
        "board_slug": board_slug,
        "board_url": board_url,
        "monitor_type": monitor_type,
        "monitor_config": json.dumps(monitor_config),
        "scraper_type": scraper_type,
        "scraper_config": json.dumps(scraper_config) if scraper_config else "",
    }


# ── Main build logic ───────────────────────────────────────────────────────────


def build(dry_run: bool = False) -> None:
    jseek_companies = _load_jobseek_companies()
    jseek_boards = _load_jobseek_boards()
    myjobs = _load_myjobs_companies()

    # Reverse SLUG_MAP so we can look up our slug from a jobseek slug
    reverse_slug_map = {v: k for k, v in SLUG_MAP.items()}

    # ── Pass 1: Build our 102 companies output rows ───────────────────────────

    # Collect all jobseek slugs we've "claimed" for our companies
    # (so we don't double-count them in the new-company pass).
    claimed_jseek_slugs: set[str] = set()

    out_companies: list[dict] = []
    out_boards: list[dict] = []

    unmapped: list[str] = []
    synthesized: list[str] = []

    for c in myjobs:
        our_slug = c["slug"]
        jseek_slug = SLUG_MAP.get(our_slug, our_slug)

        # Company row
        jseek_row = jseek_companies.get(jseek_slug)
        website = jseek_row["website"] if jseek_row else f"https://{c.get('domain','')}"
        industry_code = (
            int(jseek_row["industry"])
            if jseek_row and jseek_row.get("industry", "").isdigit()
            else INDUSTRY_TEXT_TO_CODE.get(c.get("industry", "tech"), 1)
        )
        out_companies.append({
            "slug": our_slug,
            "name": c["name"],
            "website": website,
            "industry": industry_code,
            "tier": c.get("tier", 2),
            "enabled": "false" if not c.get("enabled", True) else "true",
            "h1b_petitions_recent": "",
        })

        # Board rows
        jseek_board_rows = jseek_boards.get(jseek_slug, [])
        if jseek_board_rows:
            claimed_jseek_slugs.add(jseek_slug)
            for br in jseek_board_rows:
                out_boards.append({**br, "company_slug": our_slug})
        else:
            # Try synthesis
            synth = _synth_boards(c)
            if synth:
                synthesized.append(our_slug)
                out_boards.extend(synth)
            elif c.get("ats_type") in UNMAPPED_ATS_TYPES:
                unmapped.append(f"{our_slug} ({c.get('ats_type')})")
            else:
                unmapped.append(f"{our_slug} ({c.get('ats_type')} — no board data)")

    # ── Pass 2: Add US-tech jobseek companies not in our list ────────────────

    our_slugs = {c["slug"] for c in myjobs}
    new_count = 0

    for jslug, jrow in jseek_companies.items():
        # Skip if already claimed by one of our companies
        if jslug in claimed_jseek_slugs:
            continue
        # Skip if this jobseek slug maps to one of our slugs (reverse map)
        if jslug in reverse_slug_map and reverse_slug_map[jslug] in our_slugs:
            continue
        # Skip if not in our tech-industry allowlist
        industry_raw = jrow.get("industry", "")
        try:
            industry_code = int(industry_raw)
        except (ValueError, TypeError):
            continue
        if industry_code not in TECH_INDUSTRY_IDS:
            continue

        boards = jseek_boards.get(jslug, [])
        if not boards:
            continue  # no boards = nothing to scrape

        out_companies.append({
            "slug": jslug,
            "name": jrow["name"],
            "website": jrow.get("website", ""),
            "industry": industry_code,
            "tier": 2,
            "enabled": "true",
            "h1b_petitions_recent": "",
        })
        out_boards.extend(boards)
        new_count += 1

    # ── Summary ───────────────────────────────────────────────────────────────

    total_companies = len(out_companies)
    total_boards = len(out_boards)
    our_count = len(myjobs)
    jseek_covered = our_count - len(synthesized) - len(unmapped)

    print(f"\n{'='*60}")
    print(f"  build_csvs summary {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")
    print(f"  Our 102 companies          : {our_count}")
    print(f"    jobseek board rows used  : {jseek_covered}")
    print(f"    synthesized board rows   : {len(synthesized)}")
    print(f"    unmapped (no boards)     : {len(unmapped)}")
    print(f"  New jobseek companies added: {new_count}")
    print(f"{'─'*60}")
    print(f"  Total companies in output  : {total_companies}")
    print(f"  Total boards in output     : {total_boards}")

    if synthesized:
        print(f"\n  Synthesized ({len(synthesized)}):")
        for s in sorted(synthesized):
            print(f"    {s}")

    if unmapped:
        print(f"\n  Unmapped — no board rows ({len(unmapped)}):")
        for u in sorted(unmapped):
            print(f"    {u}")

    print()

    # ── Write ─────────────────────────────────────────────────────────────────

    if dry_run:
        print("  Dry run — no files written.\n")
        return

    COMPANY_FIELDS = ["slug", "name", "website", "industry", "tier", "enabled", "h1b_petitions_recent"]
    BOARD_FIELDS = ["company_slug", "board_slug", "board_url", "monitor_type", "monitor_config", "scraper_type", "scraper_config"]

    with open(OUT_COMPANIES, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMPANY_FIELDS)
        writer.writeheader()
        writer.writerows(out_companies)

    with open(OUT_BOARDS, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BOARD_FIELDS)
        writer.writeheader()
        writer.writerows(out_boards)

    print(f"  Wrote {OUT_COMPANIES}")
    print(f"  Wrote {OUT_BOARDS}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print summary only, no file writes")
    args = parser.parse_args()
    build(dry_run=args.dry_run)
