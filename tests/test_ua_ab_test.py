"""Unit tests for scripts/ua_ab_test.py.

Must not touch the network: tests sampling, classification, and report generation only.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.ua_ab_test import (
    build_summary,
    classify,
    extract_host,
    generate_markdown_report,
    sample_boards,
)
from src.core.monitors import monitor_needs_browser
from src.shared.robots import API_MONITORS


def test_classify_same_exact():
    chrome = {"jobs": 42, "error": None}
    honest = {"jobs": 42, "error": None}
    assert classify(chrome, honest) == "same"


def test_classify_same_both_zero():
    chrome = {"jobs": 0, "error": None}
    honest = {"jobs": 0, "error": None}
    assert classify(chrome, honest) == "same"


def test_classify_same_within_two():
    # Difference of 1 or 2 jobs is "same" even if relative percentage is large
    assert classify({"jobs": 5, "error": None}, {"jobs": 3, "error": None}) == "same"
    assert classify({"jobs": 5, "error": None}, {"jobs": 7, "error": None}) == "same"
    assert classify({"jobs": 10, "error": None}, {"jobs": 8, "error": None}) == "same"
    assert classify({"jobs": 10, "error": None}, {"jobs": 12, "error": None}) == "same"


def test_classify_same_within_ten_percent():
    # 90 to 110 on 100 jobs
    assert classify({"jobs": 100, "error": None}, {"jobs": 90, "error": None}) == "same"
    assert classify({"jobs": 100, "error": None}, {"jobs": 95, "error": None}) == "same"
    assert classify({"jobs": 100, "error": None}, {"jobs": 105, "error": None}) == "same"
    assert classify({"jobs": 100, "error": None}, {"jobs": 110, "error": None}) == "same"


def test_classify_honest_blocked():
    # Chrome ok with >= 1 job; honest errors or 0 jobs
    assert (
        classify(
            {"jobs": 10, "error": None},
            {"jobs": None, "error": "HTTPStatusError: 403 Forbidden"},
        )
        == "honest_blocked"
    )
    assert classify({"jobs": 10, "error": None}, {"jobs": 0, "error": None}) == "honest_blocked"
    assert classify({"jobs": 1, "error": None}, {"jobs": 0, "error": None}) == "honest_blocked"


def test_classify_honest_fewer():
    # Both ok, honest < 90% of chrome, and difference > 2
    assert classify({"jobs": 100, "error": None}, {"jobs": 80, "error": None}) == "honest_fewer"
    assert classify({"jobs": 100, "error": None}, {"jobs": 89, "error": None}) == "honest_fewer"
    assert classify({"jobs": 10, "error": None}, {"jobs": 7, "error": None}) == "honest_fewer"


def test_classify_chrome_blocked():
    # Honest ok with >= 1 job; chrome errors or 0 jobs
    assert (
        classify(
            {"jobs": None, "error": "TimeoutError: timed out after 60s"},
            {"jobs": 10, "error": None},
        )
        == "chrome_blocked"
    )
    assert classify({"jobs": 0, "error": None}, {"jobs": 10, "error": None}) == "chrome_blocked"
    assert classify({"jobs": 0, "error": None}, {"jobs": 1, "error": None}) == "chrome_blocked"


def test_classify_both_failed():
    # Both had errors
    assert (
        classify(
            {"jobs": None, "error": "HTTPStatusError: 500 Internal Error"},
            {"jobs": None, "error": "HTTPStatusError: 500 Internal Error"},
        )
        == "both_failed"
    )
    # One had error and the other got 0 jobs (neither got any jobs)
    assert (
        classify(
            {"jobs": 0, "error": None},
            {"jobs": None, "error": "HTTPStatusError: 500 Internal Error"},
        )
        == "both_failed"
    )
    assert (
        classify(
            {"jobs": None, "error": "ConnectError: connection refused"},
            {"jobs": 0, "error": None},
        )
        == "both_failed"
    )


def test_classify_honest_more():
    # Both ok, honest > 110% of chrome, and difference > 2
    assert classify({"jobs": 100, "error": None}, {"jobs": 115, "error": None}) == "honest_more"
    assert classify({"jobs": 10, "error": None}, {"jobs": 13, "error": None}) == "honest_more"
    assert classify({"jobs": 5, "error": None}, {"jobs": 8, "error": None}) == "honest_more"


def test_sample_boards_deterministic():
    rows = [
        {
            "company_slug": f"company-{i}",
            "board_slug": f"board-{i}",
            "board_url": f"https://company-{i}.com/jobs",
            "monitor_type": "greenhouse" if i % 2 == 0 else "dom",
            "monitor_config": '{"token": "test"}' if i % 2 == 0 else "{}",
        }
        for i in range(50)
    ]

    sample1 = sample_boards(rows, n=20, seed=7)
    sample2 = sample_boards(rows, n=20, seed=7)
    sample3 = sample_boards(rows, n=20, seed=42)

    assert [r["board_slug"] for r in sample1] == [r["board_slug"] for r in sample2]
    assert [r["board_slug"] for r in sample1] != [r["board_slug"] for r in sample3]


def test_sample_boards_company_uniqueness():
    # 10 companies, each with 3 boards
    rows = []
    for comp_idx in range(10):
        for board_idx in range(3):
            rows.append(
                {
                    "company_slug": f"comp-{comp_idx}",
                    "board_slug": f"board-{comp_idx}-{board_idx}",
                    "board_url": f"https://comp-{comp_idx}.com/careers/{board_idx}",
                    "monitor_type": "greenhouse" if board_idx % 2 == 0 else "dom",
                    "monitor_config": "{}",
                }
            )

    sampled = sample_boards(rows, n=8, seed=7)
    assert len(sampled) == 8
    companies = [r["company_slug"] for r in sampled]
    assert len(companies) == len(set(companies)), "Each board must belong to a unique company"


def test_sample_boards_skips_browser_boards():
    rows = [
        # Browser board: accenture
        {
            "company_slug": "accenture-comp",
            "board_slug": "accenture-board",
            "board_url": "https://accenture.com",
            "monitor_type": "accenture",
            "monitor_config": "{}",
        },
        # Browser board: api_sniffer without api_url
        {
            "company_slug": "sniffer-comp",
            "board_slug": "sniffer-board",
            "board_url": "https://sniffer.com",
            "monitor_type": "api_sniffer",
            "monitor_config": "{}",
        },
        # Browser board: dom with render: true
        {
            "company_slug": "rendered-comp",
            "board_slug": "rendered-board",
            "board_url": "https://rendered.com",
            "monitor_type": "dom",
            "monitor_config": '{"render": true}',
        },
        # Valid non-browser API
        {
            "company_slug": "gh-comp",
            "board_slug": "gh-board",
            "board_url": "https://gh.com",
            "monitor_type": "greenhouse",
            "monitor_config": "{}",
        },
        # Valid non-browser site
        {
            "company_slug": "site-comp",
            "board_slug": "site-board",
            "board_url": "https://site.com",
            "monitor_type": "dom",
            "monitor_config": "{}",
        },
    ]

    sampled = sample_boards(rows, n=10, seed=7)
    types = {r["monitor_type"] for r in sampled}
    assert "accenture" not in types
    assert "api_sniffer" not in types
    assert not any(
        monitor_needs_browser(
            r["monitor_type"],
            json.loads(r["monitor_config"]) if r.get("monitor_config") else {},
        )
        for r in sampled
    )
    assert len(sampled) == 2


def test_sample_boards_half_api_half_site():
    rows = []
    # 20 API boards
    for i in range(20):
        rows.append(
            {
                "company_slug": f"api-comp-{i}",
                "board_slug": f"api-board-{i}",
                "board_url": f"https://api-{i}.com",
                "monitor_type": "greenhouse",
                "monitor_config": "{}",
            }
        )
    # 20 Site boards
    for i in range(20):
        rows.append(
            {
                "company_slug": f"site-comp-{i}",
                "board_slug": f"site-board-{i}",
                "board_url": f"https://site-{i}.com",
                "monitor_type": "dom",
                "monitor_config": "{}",
            }
        )

    sampled = sample_boards(rows, n=10, seed=7)
    assert len(sampled) == 10
    apis = [r for r in sampled if r["monitor_type"] in API_MONITORS]
    sites = [r for r in sampled if r["monitor_type"] not in API_MONITORS]
    assert len(apis) == 5
    assert len(sites) == 5


def test_sample_boards_imbalanced_fill():
    rows = []
    # Only 2 site boards
    for i in range(2):
        rows.append(
            {
                "company_slug": f"site-comp-{i}",
                "board_slug": f"site-board-{i}",
                "board_url": f"https://site-{i}.com",
                "monitor_type": "dom",
                "monitor_config": "{}",
            }
        )
    # 20 API boards
    for i in range(20):
        rows.append(
            {
                "company_slug": f"api-comp-{i}",
                "board_slug": f"api-board-{i}",
                "board_url": f"https://api-{i}.com",
                "monitor_type": "greenhouse",
                "monitor_config": "{}",
            }
        )

    sampled = sample_boards(rows, n=10, seed=7)
    assert len(sampled) == 10
    sites = [r for r in sampled if r["monitor_type"] not in API_MONITORS]
    apis = [r for r in sampled if r["monitor_type"] in API_MONITORS]
    assert len(sites) == 2
    assert len(apis) == 8


def test_sample_boards_empty_and_zero():
    assert sample_boards([], n=10, seed=7) == []
    rows = [{"company_slug": "c1", "board_slug": "b1", "monitor_type": "greenhouse"}]
    assert sample_boards(rows, n=0, seed=7) == []
    assert sample_boards(rows, n=-5, seed=7) == []


def test_sample_boards_real_data():
    boards_csv = Path(__file__).resolve().parent.parent / "data" / "boards.csv"
    assert boards_csv.is_file(), "data/boards.csv must exist"

    with open(boards_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sampled = sample_boards(rows, n=200, seed=7)
    assert len(sampled) == 200

    companies = [r["company_slug"] for r in sampled]
    assert len(companies) == len(set(companies)), "Each board must belong to a unique company"

    apis = [r for r in sampled if r["monitor_type"] in API_MONITORS]
    sites = [r for r in sampled if r["monitor_type"] not in API_MONITORS]
    assert len(apis) == 100
    assert len(sites) == 100

    for r in sampled:
        assert not monitor_needs_browser(
            r["monitor_type"],
            json.loads(r["monitor_config"]) if r.get("monitor_config") else {},
        )


def test_extract_host():
    assert extract_host("https://job-boards.greenhouse.io/anthropic", "greenhouse") == "ats:greenhouse"
    assert extract_host("https://jobs.ashbyhq.com/openai", "ashby") == "ats:ashby"
    assert extract_host("https://example.com/careers/jobs", "dom") == "example.com"
    assert extract_host("http://sub.domain.co.uk:8080/path", "sitemap") == "sub.domain.co.uk"


def test_build_summary_and_markdown():
    records = [
        {
            "board_slug": "b1",
            "monitor_type": "greenhouse",
            "kind": "api",
            "chrome": {"jobs": 20, "error": None},
            "honest": {"jobs": 20, "error": None},
            "classification": "same",
        },
        {
            "board_slug": "b2",
            "monitor_type": "dom",
            "kind": "site",
            "chrome": {"jobs": 15, "error": None},
            "honest": {"jobs": None, "error": "HTTPStatusError: 403 Forbidden"},
            "classification": "honest_blocked",
        },
        {
            "board_slug": "b3",
            "monitor_type": "dom",
            "kind": "site",
            "chrome": {"jobs": 100, "error": None},
            "honest": {"jobs": 80, "error": None},
            "classification": "honest_fewer",
        },
    ]

    summary = build_summary(records)
    assert summary["total"] == 3
    assert summary["api_total"] == 1
    assert summary["site_total"] == 2
    assert summary["counts"]["same"] == 1
    assert summary["counts"]["honest_blocked"] == 1
    assert summary["counts"]["honest_fewer"] == 1
    assert len(summary["honest_blocked"]) == 1
    assert summary["honest_blocked"][0]["board_slug"] == "b2"

    md = generate_markdown_report(records, summary, "2026-10-12")
    assert "# User-Agent A/B Test Report (2026-10-12)" in md
    assert "honest_blocked" in md
    assert "b2" in md


def test_generate_markdown_report_no_blocked():
    records = [
        {
            "board_slug": "b1",
            "monitor_type": "greenhouse",
            "kind": "api",
            "chrome": {"jobs": 20, "error": None},
            "honest": {"jobs": 20, "error": None},
            "classification": "same",
        }
    ]
    summary = build_summary(records)
    md = generate_markdown_report(records, summary, "2026-10-12")
    assert "No boards were classified as honest_blocked." in md


def test_print_summary_table(capsys):
    from scripts.ua_ab_test import print_summary_table

    records = [
        {
            "board_slug": "b1",
            "monitor_type": "greenhouse",
            "kind": "api",
            "chrome": {"jobs": 20, "error": None},
            "honest": {"jobs": 20, "error": None},
            "classification": "same",
        }
    ]
    summary = build_summary(records)
    print_summary_table(summary)
    captured = capsys.readouterr()
    assert "User-Agent A/B Test Summary" in captured.out
    assert "same" in captured.out
    assert "Honest blocked boards: 0" in captured.out


def test_sample_boards_company_with_both_api_and_site():
    # Company "dual-corp" has both an API board and a site board.
    # At most ONE of them may be selected.
    rows = [
        {
            "company_slug": "dual-corp",
            "board_slug": "dual-api",
            "board_url": "https://api.dual.com",
            "monitor_type": "greenhouse",
            "monitor_config": "{}",
        },
        {
            "company_slug": "dual-corp",
            "board_slug": "dual-site",
            "board_url": "https://dual.com/careers",
            "monitor_type": "dom",
            "monitor_config": "{}",
        },
        {
            "company_slug": "other-corp",
            "board_slug": "other-api",
            "board_url": "https://api.other.com",
            "monitor_type": "greenhouse",
            "monitor_config": "{}",
        },
    ]
    sampled = sample_boards(rows, n=3, seed=7)
    comps = [r["company_slug"] for r in sampled]
    assert len(comps) == len(set(comps))
    assert comps.count("dual-corp") == 1

