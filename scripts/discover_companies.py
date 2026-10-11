"""Discover and verify career boards for candidate companies.

    python scripts/discover_companies.py data/candidates/india_companies.csv            # dry run
    python scripts/discover_companies.py data/candidates/india_companies.csv --apply    # write registry

Outputs (always): data/candidates/review_queue.csv, data/candidates/discovery_report.json
With --apply: verified boards are appended to data/companies.csv + data/boards.csv
(then run `myjobs sync`, or restart `myjobs worker`, which syncs on start).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.discovery.pipeline import (  # noqa: E402
    existing_index,
    load_candidates,
    outcome_dict,
    registry_rows,
    run,
    unique_slug,
)
from src.logger import get_logger  # noqa: E402

log = get_logger("discover_companies")
DATA = Path(__file__).resolve().parent.parent / "data"
TAG_COLUMNS = ["country", "hq_city", "company_type"]


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--apply", action="store_true", help="append verified boards to the registry CSVs")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--min-jobs", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="only process the first N candidates")
    ap.add_argument("--out-dir", type=Path, default=DATA / "candidates")
    ap.add_argument("--rediscover", action="store_true",
                    help="candidates are existing companies (CSV has a slug column) whose board went away")
    args = ap.parse_args(argv)

    company_fields, companies = _read(DATA / "companies.csv")
    board_fields, boards = _read(DATA / "boards.csv")
    candidates = load_candidates(args.candidates)
    if args.limit:
        candidates = candidates[: args.limit]

    outcomes = asyncio.run(run(candidates, companies, boards, concurrency=args.concurrency, min_jobs=args.min_jobs,
                               rediscover=args.rediscover))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    review = [outcome_dict(o) for o in outcomes if o.status != "accepted"]
    if review:
        _write(args.out_dir / "review_queue.csv", list(review[0].keys()), review)
    summary = Counter(o.status for o in outcomes)
    by_ats = Counter(o.monitor_type for o in outcomes if o.status == "accepted")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": len(candidates),
        "status": dict(summary),
        "accepted_by_ats": dict(by_ats),
        "accepted_jobs": sum(o.jobs_found for o in outcomes if o.status == "accepted"),
        "review_reasons": dict(Counter(re.sub(r"\d+", "N", o.reason.split(":")[0]) for o in outcomes if o.status == "review")),
    }
    (args.out_dir / "discovery_report.json").write_text(json.dumps(report, indent=2))
    log.info("discovery.summary", extra=report)

    if args.apply:
        for col in TAG_COLUMNS:
            if col not in company_fields:
                company_fields.append(col)
        _domains, slugs, _urls = existing_index(companies, boards)
        added = 0
        for o in outcomes:
            if o.status != "accepted":
                continue
            if o.candidate.slug and o.candidate.slug in slugs:
                # Re-discovery: keep the company, add its new board.
                _company, board = registry_rows(o, o.candidate.slug)
                boards.append(board)
                added += 1
                continue
            slug = unique_slug(o.candidate.name, slugs)
            slugs.add(slug)
            company, board = registry_rows(o, slug)
            companies.append(company)
            boards.append(board)
            added += 1
        _write(DATA / "companies.csv", company_fields, companies)
        _write(DATA / "boards.csv", board_fields, boards)
        log.info("discovery.applied", extra={"added": added})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
