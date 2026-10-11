"""Terminal tool to triage the discovery review queue.

Usage:
    python scripts/triage_review.py <dir> [--open] [--only-reason SUBSTRING]

Keys:
    a: accept
    r: reject
    s: skip
    u <url>: retry with a new careers URL
    q: quit
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.logger import get_logger

log = get_logger("triage_review")

OUTCOMES_COLUMNS = [
    "status",
    "reason",
    "board_url",
    "monitor_type",
    "monitor_config",
    "jobs_found",
    "scraper_type",
    "name",
    "website",
    "careers_url",
    "hq_city",
    "category",
    "source",
    "country",
    "slug",
]

RETRY_COLUMNS = [
    "name",
    "website",
    "careers_url",
    "hq_city",
    "category",
    "source",
    "country",
]


def normalize_decision(d: str) -> str:
    """Normalize user input or string decision to a canonical verb."""
    dl = (d or "").strip().lower()
    if dl in ("a", "accept"):
        return "accept"
    if dl == "accepted":
        return "accepted"
    if dl in ("r", "reject"):
        return "reject"
    if dl == "rejected":
        return "rejected"
    if dl in ("u", "retry"):
        return "retry"
    if dl in ("s", "skip"):
        return "skip"
    return dl


def is_accepted(decision: str) -> bool:
    return (decision or "").strip().lower() in ("a", "accept", "accepted")


def is_rejected(decision: str) -> bool:
    return (decision or "").strip().lower() in ("r", "reject", "rejected")


def is_retry(decision: str) -> bool:
    return (decision or "").strip().lower() in ("u", "retry")


def is_skip(decision: str) -> bool:
    return (decision or "").strip().lower() in ("s", "skip")


def load_jsonl(path: Path | str) -> list[dict]:
    """Load JSON lines from a file, returning an empty list if file is absent."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pending_rows(
    outcomes: Path | str | list[dict],
    triage: Path | str | list[dict] | set[str] | None = None,
    only_reason: str | None = None,
) -> list[dict]:
    """Return rows from outcomes with status == 'review' that are not yet decided in triage.

    Filters by substring in reason if ``only_reason`` is specified.
    """
    if isinstance(outcomes, (str, Path)):
        p = Path(outcomes)
        if p.is_dir():
            if triage is None:
                triage = p / "triage.jsonl"
            p = p / "outcomes.jsonl"
        outcome_list = load_jsonl(p)
    else:
        outcome_list = list(outcomes)

    decided_websites: set[str] = set()
    if triage is not None:
        if isinstance(triage, (str, Path)):
            tp = Path(triage)
            if tp.is_dir():
                tp = tp / "triage.jsonl"
            triage_records = load_jsonl(tp)
            decided_websites = {r["website"] for r in triage_records if "website" in r}
        elif isinstance(triage, set):
            decided_websites = triage
        elif isinstance(triage, list):
            for item in triage:
                if isinstance(item, dict) and "website" in item:
                    decided_websites.add(item["website"])
                elif isinstance(item, str):
                    decided_websites.add(item)

    pending: list[dict] = []
    for r in outcome_list:
        if r.get("status") != "review":
            continue
        website = r.get("website", "")
        if website in decided_websites:
            continue
        if only_reason:
            reason = r.get("reason", "")
            if only_reason not in reason and only_reason.lower() not in reason.lower():
                continue
        pending.append(r)

    return pending


def apply_decision(
    target: Path | str | list[dict] | dict | IO,
    row_or_decision: dict | str,
    decision: str | None = None,
    careers_url: str | None = None,
    *,
    ts: str | None = None,
) -> dict:
    """Record a triage decision for a company.

    Appends {"website": ..., "decision": ..., ["careers_url": ...,] "ts": ...}
    to the target (if file path or list is provided) and returns the decision record.
    """
    if isinstance(target, dict) and ("website" in target or "status" in target or decision is None):
        # Called as apply_decision(row, decision, careers_url=...)
        row = target
        raw_decision = str(row_or_decision)
        c_url = careers_url or decision
        destination = None
    else:
        destination = target
        if isinstance(row_or_decision, dict):
            row = row_or_decision
            raw_decision = decision or ""
            c_url = careers_url
        else:
            row = {"website": str(row_or_decision)}
            raw_decision = decision or ""
            c_url = careers_url

    website = row.get("website", "") if isinstance(row, dict) else str(row)
    norm_dec = normalize_decision(raw_decision)
    timestamp = ts or datetime.now(timezone.utc).isoformat()

    record: dict[str, Any] = {
        "website": website,
        "decision": norm_dec,
        "ts": timestamp,
    }
    if is_retry(norm_dec) and c_url:
        record["careers_url"] = c_url
    elif c_url:
        record["careers_url"] = c_url

    if destination is not None:
        if isinstance(destination, list):
            destination.append(record)
        elif isinstance(destination, (str, Path)):
            dest_path = Path(destination)
            if dest_path.is_dir():
                dest_path = dest_path / "triage.jsonl"
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        elif hasattr(destination, "write"):
            destination.write(json.dumps(record) + "\n")

    log.info("triage.decision", extra={"website": website, "decision": norm_dec})
    return record


def _clean_monitor_config(val: Any) -> str:
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val or "")


def _collect_fieldnames(rows: list[dict], default_cols: list[str]) -> list[str]:
    cols = list(default_cols)
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    return cols


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_outputs(
    out_dir: Path | str,
    outcomes: Path | str | list[dict] | None = None,
    triage: Path | str | list[dict] | None = None,
) -> dict[str, list[dict]]:
    """Rewrite accepted.csv, retry.csv, rejected.csv from outcomes + triage."""
    dir_path = Path(out_dir)

    # 1. Load outcomes
    if outcomes is None:
        outcome_rows = load_jsonl(dir_path / "outcomes.jsonl")
    elif isinstance(outcomes, (str, Path)):
        p = Path(outcomes)
        if p.is_dir():
            p = p / "outcomes.jsonl"
        outcome_rows = load_jsonl(p)
    else:
        outcome_rows = list(outcomes)

    # 2. Load triage
    if triage is None:
        triage_rows = load_jsonl(dir_path / "triage.jsonl")
    elif isinstance(triage, (str, Path)):
        p = Path(triage)
        if p.is_dir():
            p = p / "triage.jsonl"
        triage_rows = load_jsonl(p)
    else:
        triage_rows = list(triage)

    # Build latest triage decision per website
    triage_map: dict[str, dict] = {}
    for t in triage_rows:
        if "website" in t:
            triage_map[t["website"]] = t

    accepted_rows: list[dict] = []
    retry_rows: list[dict] = []
    rejected_rows: list[dict] = []

    seen_websites: set[str] = set()

    # Track outcomes processed
    for row in outcome_rows:
        website = row.get("website", "")
        orig_status = row.get("status", "")
        dec_rec = triage_map.get(website)

        if dec_rec:
            dec = dec_rec.get("decision", "")
            if is_accepted(dec):
                acc_row = dict(row)
                acc_row["status"] = "accepted"
                acc_row["monitor_config"] = _clean_monitor_config(acc_row.get("monitor_config"))
                accepted_rows.append(acc_row)
                seen_websites.add(website)
            elif is_retry(dec):
                new_url = dec_rec.get("careers_url") or row.get("careers_url", "")
                ret_row = {
                    "name": row.get("name", ""),
                    "website": website,
                    "careers_url": new_url,
                    "hq_city": row.get("hq_city", ""),
                    "category": row.get("category", ""),
                    "source": row.get("source", ""),
                    "country": row.get("country", "") or "IN",
                }
                retry_rows.append(ret_row)
                seen_websites.add(website)
            elif is_rejected(dec):
                rej_row = dict(row)
                rej_row["status"] = "rejected"
                rej_row["monitor_config"] = _clean_monitor_config(rej_row.get("monitor_config"))
                rejected_rows.append(rej_row)
                seen_websites.add(website)
            elif is_skip(dec):
                seen_websites.add(website)
        else:
            if orig_status == "accepted":
                acc_row = dict(row)
                acc_row["status"] = "accepted"
                acc_row["monitor_config"] = _clean_monitor_config(acc_row.get("monitor_config"))
                accepted_rows.append(acc_row)
                seen_websites.add(website)

    # In case there were triage records for websites not present in outcomes
    for website, dec_rec in triage_map.items():
        if website in seen_websites:
            continue
        dec = dec_rec.get("decision", "")
        if is_accepted(dec):
            accepted_rows.append({
                "status": "accepted",
                "reason": "triaged",
                "board_url": "",
                "monitor_type": "",
                "monitor_config": "",
                "jobs_found": 0,
                "scraper_type": "",
                "name": "",
                "website": website,
                "careers_url": "",
                "hq_city": "",
                "category": "",
                "source": "",
                "country": "IN",
                "slug": "",
            })
        elif is_retry(dec):
            retry_rows.append({
                "name": "",
                "website": website,
                "careers_url": dec_rec.get("careers_url", ""),
                "hq_city": "",
                "category": "",
                "source": "",
                "country": "IN",
            })
        elif is_rejected(dec):
            rejected_rows.append({
                "status": "rejected",
                "reason": "triaged",
                "board_url": "",
                "monitor_type": "",
                "monitor_config": "",
                "jobs_found": 0,
                "scraper_type": "",
                "name": "",
                "website": website,
                "careers_url": "",
                "hq_city": "",
                "category": "",
                "source": "",
                "country": "IN",
                "slug": "",
            })

    # Write files
    _write_csv(dir_path / "accepted.csv", _collect_fieldnames(accepted_rows, OUTCOMES_COLUMNS), accepted_rows)
    _write_csv(dir_path / "retry.csv", RETRY_COLUMNS, retry_rows)
    _write_csv(dir_path / "rejected.csv", _collect_fieldnames(rejected_rows, OUTCOMES_COLUMNS), rejected_rows)

    log.info(
        "triage.outputs_written",
        extra={
            "dir": str(dir_path),
            "accepted": len(accepted_rows),
            "retry": len(retry_rows),
            "rejected": len(rejected_rows),
        },
    )

    return {
        "accepted": accepted_rows,
        "retry": retry_rows,
        "rejected": rejected_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Triage discovery review queue.",
    )
    parser.add_argument("dir", type=Path, help="Directory containing outcomes.jsonl")
    parser.add_argument("--open", action="store_true", help="Open board_url (or website) in browser")
    parser.add_argument("--only-reason", type=str, default=None, help="Filter pending rows by reason substring")

    args = parser.parse_args(argv)

    out_dir = args.dir
    outcomes_path = out_dir / "outcomes.jsonl"
    triage_path = out_dir / "triage.jsonl"

    if not outcomes_path.exists():
        print(f"Error: {outcomes_path} does not exist", file=sys.stderr)
        return 1

    pending = pending_rows(outcomes_path, triage_path, only_reason=args.only_reason)
    if not pending:
        print("No pending review rows.")
        write_outputs(out_dir)
        return 0

    total = len(pending)
    print(f"Found {total} row(s) to triage in {out_dir}\n")

    for idx, row in enumerate(pending, start=1):
        name = row.get("name", "Unknown")
        website = row.get("website", "")
        board_url = row.get("board_url", "")
        monitor_type = row.get("monitor_type", "")
        jobs_found = row.get("jobs_found", 0)
        reason = row.get("reason", "")
        hq_city = row.get("hq_city", "")
        source = row.get("source", "")

        print(f"[{idx}/{total}] {name} ({hq_city or 'no city'}) [source: {source or 'unknown'}]")
        print(f"  Website:      {website}")
        print(f"  Board URL:    {board_url}")
        print(f"  Monitor:      {monitor_type} (jobs: {jobs_found})")
        print(f"  Reason:       {reason}")

        if args.open:
            url_to_open = board_url or website
            if url_to_open:
                try:
                    webbrowser.open(url_to_open)
                except Exception as e:
                    print(f"  (Failed to open {url_to_open}: {e})")

        while True:
            try:
                choice = input("[a]ccept  [r]eject  [s]kip  [u <url>] retry  [q]uit > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nQuitting...")
                write_outputs(out_dir)
                return 0

            if not choice:
                continue

            if choice == "q":
                print("Quitting.")
                write_outputs(out_dir)
                return 0

            if choice == "a":
                m_type = (monitor_type or "").lower()
                if m_type in ("sitemap", "dom"):
                    print("Warning: generic monitor: check that the board URL lists only jobs")
                    try:
                        ans = input("Confirm accept? [y/N]: ").strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        print("\nCancelled accept and quitting...")
                        write_outputs(out_dir)
                        return 0
                    if ans not in ("y", "yes"):
                        print("Accept cancelled.")
                        continue

                apply_decision(triage_path, row, "accept")
                write_outputs(out_dir)
                break

            if choice == "r":
                apply_decision(triage_path, row, "reject")
                write_outputs(out_dir)
                break

            if choice == "s":
                apply_decision(triage_path, row, "skip")
                write_outputs(out_dir)
                break

            if choice.startswith("u"):
                parts = choice.split(maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    new_url = parts[1].strip()
                else:
                    try:
                        new_url = input("New careers URL: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print("\nCancelled retry and quitting...")
                        write_outputs(out_dir)
                        return 0

                if not new_url:
                    print("URL cannot be empty. Try again.")
                    continue

                apply_decision(triage_path, row, "retry", careers_url=new_url)
                write_outputs(out_dir)
                break

            print("Invalid command. Choose 'a', 'r', 's', 'u <url>', or 'q'.")

    print("\nTriage complete.")
    write_outputs(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
