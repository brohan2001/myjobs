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
    Candidate,
    Outcome,
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


def _outcomes_from_accepted(path: Path) -> list[Outcome]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = Candidate(name=r["name"], website=r["website"], careers_url=r.get("careers_url", ""),
                          hq_city=r.get("hq_city", ""), category=r.get("category", ""), source=r.get("source", ""),
                          country=r.get("country", "IN") or "IN", slug=r.get("slug", ""))
            cfg = json.loads(r["monitor_config"]) if r.get("monitor_config") else {}
            out.append(Outcome(c, "accepted", "verified", board_url=r["board_url"], monitor_type=r["monitor_type"],
                               monitor_config=cfg, jobs_found=int(r.get("jobs_found") or 0)))
    return out


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
    ap.add_argument("--apply-accepted", action="store_true",
                    help="treat the input as a previous run's accepted.csv and only apply it (no network)")
    args = ap.parse_args(argv)

    company_fields, companies = _read(DATA / "companies.csv")
    board_fields, boards = _read(DATA / "boards.csv")
    candidates = load_candidates(args.candidates)
    if args.limit:
        candidates = candidates[: args.limit]

    if args.apply_accepted:
        outcomes = _outcomes_from_accepted(args.candidates)
        args.apply = True
    else:
        outcomes = asyncio.run(run(candidates, companies, boards, concurrency=args.concurrency, min_jobs=args.min_jobs,
                                   rediscover=args.rediscover))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    review = [outcome_dict(o) for o in outcomes if o.status != "accepted"]
    if review:
        _write(args.out_dir / "review_queue.csv", list(review[0].keys()), review)
    accepted = [outcome_dict(o) for o in outcomes if o.status == "accepted"]
    if accepted:
        _write(args.out_dir / "accepted.csv", list(accepted[0].keys()), accepted)
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
        board_slugs = {b["board_slug"] for b in boards if b.get("board_slug")}

        def _unique_board(board: dict) -> dict:
            board["board_slug"] = unique_slug(board["board_slug"], board_slugs)
            board_slugs.add(board["board_slug"])
            return board

        added = 0
        for o in outcomes:
            if o.status != "accepted":
                continue
            if o.candidate.slug and o.candidate.slug in slugs:
                # Re-discovery: keep the company, add its new board.
                _company, board = registry_rows(o, o.candidate.slug)
                boards.append(_unique_board(board))
                added += 1
                continue
            slug = unique_slug(o.candidate.name, slugs)
            slugs.add(slug)
            company, board = registry_rows(o, slug)
            companies.append(company)
            boards.append(_unique_board(board))
            added += 1
        _write(DATA / "companies.csv", company_fields, companies)
        _write(DATA / "boards.csv", board_fields, boards)
        log.info("discovery.applied", extra={"added": added})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
