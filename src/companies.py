"""Load companies and boards from the CSV config files."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class Company:
    slug: str
    name: str
    website: str
    industry: int
    tier: int
    enabled: bool
    h1b_petitions_recent: Optional[int]


@dataclass
class Board:
    company_slug: str
    board_slug: str
    board_url: str
    monitor_type: str
    monitor_config: dict
    scraper_type: str
    scraper_config: dict

    # Set after loading when we need company-level fields
    company: Optional[Company] = field(default=None, compare=False, repr=False)


def load_companies(enabled_only: bool = True) -> list[Company]:
    """Return Company objects from data/companies.csv.

    When *enabled_only* is True (the default), rows with enabled=false are
    excluded. Pass False to get all rows including disabled companies.
    """
    path = DATA_DIR / "companies.csv"
    out: list[Company] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            is_enabled = row.get("enabled", "true").lower() not in ("false", "0", "no")
            if enabled_only and not is_enabled:
                continue
            h1b_raw = row.get("h1b_petitions_recent", "")
            out.append(Company(
                slug=row["slug"],
                name=row["name"],
                website=row.get("website", ""),
                industry=int(row.get("industry", 1) or 1),
                tier=int(row.get("tier", 2) or 2),
                enabled=is_enabled,
                h1b_petitions_recent=int(h1b_raw) if h1b_raw.strip() else None,
            ))
    return out


def load_boards(enabled_companies_only: bool = True) -> list[Board]:
    """Return Board objects from data/boards.csv, joined with Company data.

    When *enabled_companies_only* is True (the default), boards whose company
    has enabled=false in companies.csv are omitted.
    """
    companies = {c.slug: c for c in load_companies(enabled_only=enabled_companies_only)}

    path = DATA_DIR / "boards.csv"
    out: list[Board] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cslug = row["company_slug"]
            if enabled_companies_only and cslug not in companies:
                continue  # company disabled or not found
            mc_raw = row.get("monitor_config", "") or "{}"
            sc_raw = row.get("scraper_config", "") or "{}"
            try:
                mc = json.loads(mc_raw)
            except json.JSONDecodeError:
                mc = {}
            try:
                sc = json.loads(sc_raw)
            except json.JSONDecodeError:
                sc = {}
            board = Board(
                company_slug=cslug,
                board_slug=row["board_slug"],
                board_url=row["board_url"],
                monitor_type=row["monitor_type"],
                monitor_config=mc,
                scraper_type=row["scraper_type"],
                scraper_config=sc,
                company=companies.get(cslug),
            )
            out.append(board)
    return out


def load_companies_by_slug(enabled_only: bool = True) -> dict[str, Company]:
    """Return {slug: Company} mapping."""
    return {c.slug: c for c in load_companies(enabled_only=enabled_only)}
