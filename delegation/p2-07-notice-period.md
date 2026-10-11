# p2-07-notice-period
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-07-notice-period` (already checked out)

## Goal
Implement `src/core/notice_period.py` exposing `extract_notice_period(text: str | None) -> int | None`: the longest notice
period an Indian job posting accepts, in days. `0` = immediate joiners only; `None` = not stated.

## Files you may touch
- `src/core/notice_period.py` (new). Nothing else. Do NOT edit the tests.

## Contract
`tests/test_notice_period.py` already exists and is the spec. Read it first.
- Input may be plain text or HTML; strip tags first (stdlib `re`/`html` only, no new dependencies).
- Only count a number when it is tied to notice-period context: "notice period", "NP:", "join within", "joiners",
  "can join". A bare "90 days notice" without "period" is not enough.
- Weeks ×7, months ×30. Ranges ("0-30 days", "immediate to 15 days") take the upper bound. Several mentions → the largest.
- Values over 180 days → ignore them (return None if nothing else matched).
- Pure function, no logging, no network. Compile regexes at module level.

## Acceptance
- `python3 -m pytest -q tests/test_notice_period.py` passes.
- `python3 -m pytest -q` passes in full.
- Commit with message `feat(notice): notice-period extractor` (add a line `Co-Authored-By: Gemini 3.8 Flash (agy)`).

## Report back
JSON only: {"files_changed": [...], "tests": "<pytest summary line>", "assumptions": [...], "unsure": [...]}
