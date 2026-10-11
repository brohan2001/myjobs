# p2-09-review-triage
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-09-review-triage` (already checked out)

## Goal
Write `scripts/triage_review.py`, a resumable terminal tool to triage the discovery review queue. For each company the
operator accepts the board, retries discovery with a corrected careers URL, rejects it, or skips it.

## Context
- Input: a discovery output directory (e.g. `data/candidates/india-pass2/`) containing `outcomes.jsonl`, one JSON object per
  line. Keys: `status, reason, board_url, monitor_type, monitor_config, jobs_found, scraper_type, name, website,
  careers_url, hq_city, category, source, country, slug`. Triage only rows with `status == "review"`.
- Accepted rows are applied later by `python scripts/discover_companies.py <dir>/accepted.csv --apply-accepted`, which reads
  the same columns as `outcomes.jsonl` (CSV, header row, any order).
- Retry rows are fed back with `python scripts/discover_companies.py <dir>/retry.csv --out-dir <dir>/retry`, which reads
  candidate columns: `name, website, careers_url, hq_city, category, source, country`.
- Logging: `from src.logger import get_logger`. User-facing prompts may use `print()`/`input()` (this is an interactive tool).

## Files you may touch (nothing else)
- `scripts/triage_review.py` (new)
- `tests/test_triage_review.py` (new)

## Interface contract
```
python scripts/triage_review.py <dir> [--open] [--only-reason SUBSTRING]
```
- For each pending row, show: name, website, board_url, monitor_type, jobs_found, reason, hq_city, source.
  With `--open`, open `board_url` (or `website`) with `webbrowser.open`.
- Keys: `a` accept, `r` reject, `s` skip, `u <url>` retry with a new careers URL, `q` quit.
- Decisions append immediately to `<dir>/triage.jsonl` (`{"website", "decision", "careers_url"?, "ts"}`), so quitting
  loses nothing. On start, rows already decided in `triage.jsonl` are skipped (match on `website`).
- After every decision (and on quit), rewrite `<dir>/accepted.csv` (status "accepted"), `<dir>/retry.csv` and
  `<dir>/rejected.csv` from `outcomes.jsonl` + `triage.jsonl`. Keep any rows that discovery itself accepted in `accepted.csv`.
- Accepting a `sitemap` or `dom` board prints a warning ("generic monitor: check that the board URL lists only jobs")
  and asks `y/N` before recording it.
- Put the logic in pure functions (`pending_rows`, `apply_decision`, `write_outputs`) with I/O passed in, so tests
  can drive them without a terminal. `main()` handles the prompt loop.

## Acceptance criteria
- [ ] `python3 -m pytest -q tests/test_triage_review.py` passes, using `tmp_path` and no network
- [ ] `python3 -m pytest -q` passes in full
- [ ] No personal data, no secrets; test fixtures use fictional companies (`example.com` domains)
- [ ] Commit with message `feat(scripts): review-queue triage tool` plus a line `Co-Authored-By: Gemini 3.8 Flash (agy)`

## Report back
JSON only: {"files_changed": [...], "tests": "<pytest summary line>", "assumptions": [...], "unsure": [...]}
