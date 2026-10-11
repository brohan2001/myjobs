"""Tests for scripts/triage_review.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.triage_review import (
    OUTCOMES_COLUMNS,
    RETRY_COLUMNS,
    apply_decision,
    main,
    pending_rows,
    write_outputs,
)


def _make_outcome(
    name: str = "Acme Corp",
    website: str = "https://acme.example.com",
    status: str = "review",
    reason: str = "needs review",
    board_url: str = "https://acme.example.com/jobs",
    monitor_type: str = "lever",
    monitor_config: dict | str = "",
    jobs_found: int = 5,
    careers_url: str = "https://acme.example.com/careers",
    hq_city: str = "Bengaluru",
    category: str = "tech",
    source: str = "seed",
    country: str = "IN",
    slug: str = "acme-corp",
) -> dict:
    return {
        "status": status,
        "reason": reason,
        "board_url": board_url,
        "monitor_type": monitor_type,
        "monitor_config": monitor_config,
        "jobs_found": jobs_found,
        "scraper_type": "",
        "name": name,
        "website": website,
        "careers_url": careers_url,
        "hq_city": hq_city,
        "category": category,
        "source": source,
        "country": country,
        "slug": slug,
    }


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


# ---------------------------------------------------------------------------
# Unit tests: pending_rows
# ---------------------------------------------------------------------------


def test_pending_rows_filters_only_review_status():
    outcomes = [
        _make_outcome(name="Accepted Co", website="https://a.example.com", status="accepted"),
        _make_outcome(name="Review Co", website="https://r.example.com", status="review"),
        _make_outcome(name="Rejected Co", website="https://rej.example.com", status="rejected"),
        _make_outcome(name="Duplicate Co", website="https://dup.example.com", status="duplicate"),
    ]
    res = pending_rows(outcomes, triage=[])
    assert len(res) == 1
    assert res[0]["website"] == "https://r.example.com"


def test_pending_rows_skips_decided_websites():
    outcomes = [
        _make_outcome(name="Co 1", website="https://co1.example.com", status="review"),
        _make_outcome(name="Co 2", website="https://co2.example.com", status="review"),
    ]
    triage = [
        {"website": "https://co1.example.com", "decision": "accept", "ts": "2026-01-01T00:00:00Z"},
    ]
    res = pending_rows(outcomes, triage)
    assert len(res) == 1
    assert res[0]["website"] == "https://co2.example.com"


def test_pending_rows_filters_only_reason():
    outcomes = [
        _make_outcome(name="Co 1", website="https://co1.example.com", status="review", reason="timed out after 60s"),
        _make_outcome(name="Co 2", website="https://co2.example.com", status="review", reason="no jobs found"),
        _make_outcome(name="Co 3", website="https://co3.example.com", status="review", reason="timed out after 30s"),
    ]
    res = pending_rows(outcomes, triage=[], only_reason="timed out")
    assert len(res) == 2
    assert [r["website"] for r in res] == ["https://co1.example.com", "https://co3.example.com"]


def test_pending_rows_from_paths(tmp_path: Path):
    outcomes = [
        _make_outcome(name="Co 1", website="https://co1.example.com", status="review"),
        _make_outcome(name="Co 2", website="https://co2.example.com", status="review"),
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)
    _write_jsonl(tmp_path / "triage.jsonl", [{"website": "https://co1.example.com", "decision": "reject"}])

    res = pending_rows(tmp_path)
    assert len(res) == 1
    assert res[0]["website"] == "https://co2.example.com"


# ---------------------------------------------------------------------------
# Unit tests: apply_decision
# ---------------------------------------------------------------------------


def test_apply_decision_records_and_appends_to_file(tmp_path: Path):
    triage_file = tmp_path / "triage.jsonl"
    row = _make_outcome(website="https://alpha.example.com")

    rec = apply_decision(triage_file, row, "a")
    assert rec["website"] == "https://alpha.example.com"
    assert rec["decision"] == "accept"
    assert "ts" in rec
    assert "careers_url" not in rec

    lines = triage_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["website"] == "https://alpha.example.com"
    assert saved["decision"] == "accept"


def test_apply_decision_retry_records_careers_url(tmp_path: Path):
    triage_file = tmp_path / "triage.jsonl"
    row = _make_outcome(website="https://beta.example.com")

    rec = apply_decision(triage_file, row, "u", careers_url="https://beta.example.com/new-jobs")
    assert rec["website"] == "https://beta.example.com"
    assert rec["decision"] == "retry"
    assert rec["careers_url"] == "https://beta.example.com/new-jobs"

    saved = json.loads(triage_file.read_text(encoding="utf-8").strip())
    assert saved["careers_url"] == "https://beta.example.com/new-jobs"


def test_apply_decision_in_memory_list():
    decisions: list[dict] = []
    row = _make_outcome(website="https://gamma.example.com")

    rec = apply_decision(decisions, row, "r")
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "reject"
    assert rec["website"] == "https://gamma.example.com"


# ---------------------------------------------------------------------------
# Unit tests: write_outputs
# ---------------------------------------------------------------------------


def test_write_outputs_creates_all_csvs(tmp_path: Path):
    outcomes = [
        _make_outcome(
            name="Discovery Accepted Co",
            website="https://disc-acc.example.com",
            status="accepted",
            reason="verified",
            monitor_config={"token": "abc"},
        ),
        _make_outcome(name="Review Co 1", website="https://r1.example.com", status="review"),
        _make_outcome(name="Review Co 2", website="https://r2.example.com", status="review"),
        _make_outcome(name="Review Co 3", website="https://r3.example.com", status="review"),
        _make_outcome(name="Review Co 4", website="https://r4.example.com", status="review"),
    ]
    triage = [
        {"website": "https://r1.example.com", "decision": "accept", "ts": "2026-01-01T00:00:00Z"},
        {"website": "https://r2.example.com", "decision": "retry", "careers_url": "https://r2.example.com/jobs-fix", "ts": "2026-01-01T00:00:00Z"},
        {"website": "https://r3.example.com", "decision": "reject", "ts": "2026-01-01T00:00:00Z"},
        {"website": "https://r4.example.com", "decision": "skip", "ts": "2026-01-01T00:00:00Z"},
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)
    _write_jsonl(tmp_path / "triage.jsonl", triage)

    res = write_outputs(tmp_path)

    # accepted.csv: contains discovery-accepted and r1
    acc_fields, acc_rows = _read_csv(tmp_path / "accepted.csv")
    assert len(acc_rows) == 2
    websites_acc = {r["website"] for r in acc_rows}
    assert websites_acc == {"https://disc-acc.example.com", "https://r1.example.com"}
    for r in acc_rows:
        assert r["status"] == "accepted"
    # check monitor_config serialization
    disc_acc = next(r for r in acc_rows if r["website"] == "https://disc-acc.example.com")
    assert json.loads(disc_acc["monitor_config"]) == {"token": "abc"}

    # retry.csv: candidate columns with updated careers_url
    ret_fields, ret_rows = _read_csv(tmp_path / "retry.csv")
    assert ret_fields == RETRY_COLUMNS
    assert len(ret_rows) == 1
    assert ret_rows[0]["website"] == "https://r2.example.com"
    assert ret_rows[0]["careers_url"] == "https://r2.example.com/jobs-fix"

    # rejected.csv: contains r3
    rej_fields, rej_rows = _read_csv(tmp_path / "rejected.csv")
    assert len(rej_rows) == 1
    assert rej_rows[0]["website"] == "https://r3.example.com"
    assert rej_rows[0]["status"] == "rejected"

    # skipped company (r4) should not appear in any CSV
    assert "https://r4.example.com" not in websites_acc
    assert "https://r4.example.com" not in {r["website"] for r in ret_rows}
    assert "https://r4.example.com" not in {r["website"] for r in rej_rows}


def test_write_outputs_overwrites_with_latest_triage_decision(tmp_path: Path):
    outcomes = [
        _make_outcome(name="Switch Co", website="https://switch.example.com", status="review"),
    ]
    triage = [
        {"website": "https://switch.example.com", "decision": "accept", "ts": "2026-01-01T00:00:00Z"},
        {"website": "https://switch.example.com", "decision": "reject", "ts": "2026-01-01T01:00:00Z"},
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)
    _write_jsonl(tmp_path / "triage.jsonl", triage)

    write_outputs(tmp_path)

    _, acc_rows = _read_csv(tmp_path / "accepted.csv")
    _, rej_rows = _read_csv(tmp_path / "rejected.csv")
    assert len(acc_rows) == 0
    assert len(rej_rows) == 1
    assert rej_rows[0]["website"] == "https://switch.example.com"


# ---------------------------------------------------------------------------
# Integration tests: main prompt loop
# ---------------------------------------------------------------------------


def test_main_missing_outcomes(tmp_path: Path, capsys: pytest.CaptureFixture):
    code = main([str(tmp_path)])
    assert code == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err


def test_main_no_pending_rows(tmp_path: Path, capsys: pytest.CaptureFixture):
    _write_jsonl(tmp_path / "outcomes.jsonl", [
        _make_outcome(status="accepted"),
    ])
    code = main([str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert "No pending review rows" in captured.out


def test_main_interactive_accept_and_quit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outcomes = [
        _make_outcome(name="Company A", website="https://a.example.com", status="review", monitor_type="greenhouse"),
        _make_outcome(name="Company B", website="https://b.example.com", status="review", monitor_type="lever"),
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)

    # 1st prompt: accept Company A
    # 2nd prompt: quit
    inputs = iter(["a", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    code = main([str(tmp_path)])
    assert code == 0

    # Triage should have Company A
    triage_file = tmp_path / "triage.jsonl"
    assert triage_file.exists()
    lines = triage_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["website"] == "https://a.example.com"

    # accepted.csv should have Company A
    _, acc_rows = _read_csv(tmp_path / "accepted.csv")
    assert len(acc_rows) == 1
    assert acc_rows[0]["website"] == "https://a.example.com"


def test_main_interactive_retry_and_reject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outcomes = [
        _make_outcome(name="Company R", website="https://r.example.com", status="review"),
        _make_outcome(name="Company Rej", website="https://rej.example.com", status="review"),
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)

    # 1st prompt: retry with URL: 'u https://r.example.com/fix'
    # 2nd prompt: reject: 'r'
    inputs = iter(["u https://r.example.com/fix", "r"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    code = main([str(tmp_path)])
    assert code == 0

    _, ret_rows = _read_csv(tmp_path / "retry.csv")
    assert len(ret_rows) == 1
    assert ret_rows[0]["website"] == "https://r.example.com"
    assert ret_rows[0]["careers_url"] == "https://r.example.com/fix"

    _, rej_rows = _read_csv(tmp_path / "rejected.csv")
    assert len(rej_rows) == 1
    assert rej_rows[0]["website"] == "https://rej.example.com"


def test_main_generic_monitor_warning_sitemap_and_dom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    outcomes = [
        _make_outcome(name="Sitemap Co", website="https://sm.example.com", status="review", monitor_type="sitemap"),
        _make_outcome(name="DOM Co", website="https://dom.example.com", status="review", monitor_type="dom"),
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)

    # For Sitemap Co:
    # 1. 'a' -> triggers warning
    # 2. 'n' -> aborts accept
    # 3. 'r' -> reject Sitemap Co
    # For DOM Co:
    # 4. 'a' -> triggers warning
    # 5. 'y' -> confirms accept
    inputs = iter(["a", "n", "r", "a", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    code = main([str(tmp_path)])
    assert code == 0

    captured = capsys.readouterr()
    assert "generic monitor: check that the board URL lists only jobs" in captured.out
    assert "Accept cancelled." in captured.out

    _, acc_rows = _read_csv(tmp_path / "accepted.csv")
    assert len(acc_rows) == 1
    assert acc_rows[0]["website"] == "https://dom.example.com"

    _, rej_rows = _read_csv(tmp_path / "rejected.csv")
    assert len(rej_rows) == 1
    assert rej_rows[0]["website"] == "https://sm.example.com"


def test_main_open_flag_calls_webbrowser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outcomes = [
        _make_outcome(
            name="Open Co",
            website="https://open.example.com",
            board_url="https://open.example.com/careers",
            status="review",
        ),
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)

    inputs = iter(["q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    with patch("webbrowser.open") as mock_open:
        code = main([str(tmp_path), "--open"])
        assert code == 0
        mock_open.assert_called_once_with("https://open.example.com/careers")


def test_main_only_reason_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outcomes = [
        _make_outcome(name="Co 1", website="https://co1.example.com", status="review", reason="timed out"),
        _make_outcome(name="Co 2", website="https://co2.example.com", status="review", reason="no jobs found"),
    ]
    _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)

    inputs = iter(["r"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    code = main([str(tmp_path), "--only-reason", "timed out"])
    assert code == 0

    # Only Co 1 was triaged
    _, rej_rows = _read_csv(tmp_path / "rejected.csv")
    assert len(rej_rows) == 1
    assert rej_rows[0]["website"] == "https://co1.example.com"

    # Co 2 should still be pending when we check pending_rows
    assert len(pending_rows(tmp_path)) == 1
    assert pending_rows(tmp_path)[0]["website"] == "https://co2.example.com"
