# p2-08-ua-ab-test
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-08-ua-ab-test` (already checked out)

## Goal
Write `scripts/ua_ab_test.py`, which measures whether an honest, identifying User-Agent costs coverage compared with
the current Chrome UA (DECISIONS D14). It runs each sampled board's monitor twice, once per UA, and compares the results.

## Context
- Boards: `data/boards.csv` (`company_slug, board_slug, board_url, monitor_type, monitor_config, scraper_type, scraper_config`).
- Monitor entry point: `from src.core.monitor import monitor_one`; call `await monitor_one(board_url, monitor_type, config, client)`,
  where `config = json.loads(monitor_config or "{}")`. It returns an object with `.urls` (a set of job URLs).
- HTTP client: `from src.shared.http import create_http_client` (keeps the SSRF guard; do NOT build a raw httpx client).
  Override the UA with `client.headers["User-Agent"] = ...` after creating it.
- Skip browser boards: `from src.core.monitors import monitor_needs_browser`; skip when `monitor_needs_browser(monitor_type, config)`.
- `API_MONITORS` in `src/shared/robots.py` lists ATS API monitor types; everything else reads company sites.
- Logging: `from src.logger import get_logger`; never `print()` except for the final summary table.

## Files you may touch (nothing else)
- `scripts/ua_ab_test.py` (new)
- `tests/test_ua_ab_test.py` (new; must not touch the network: test the sampling and comparison functions only)

## Interface contract
```
python scripts/ua_ab_test.py [--sample 200] [--seed 7] [--concurrency 6] [--out docs/research/ua_ab]
```
- Honest UA: `myjobs-bot/0.1 (+https://github.com/brohan2001/myjobs)`.
- Sampling (`sample_boards(rows, n, seed) -> list[dict]`): deterministic; about half API monitors, half site-reading
  monitors; at most one board per company; skip browser boards.
- Per board, run the Chrome UA first, then the honest UA, with a 60 s timeout each. Record `{board_slug, monitor_type, kind: "api"|"site",
  chrome: {jobs, error}, honest: {jobs, error}}`. `error` is `"<ExceptionType>: <msg[:120]>"` or null.
- Classification (`classify(chrome, honest) -> str`): `"same"` (both ok, job counts within 10% or ±2), `"honest_blocked"`
  (chrome ok with ≥1 job; honest errors or 0 jobs), `"honest_fewer"` (both ok, honest < 90% of chrome),
  `"chrome_blocked"`, `"both_failed"`, `"honest_more"`.
- At most `--concurrency` boards in flight, and never two requests to the same host at once.
- Output: `<out>/<YYYY-MM-DD>.json` (all records plus a summary) and `<out>/<YYYY-MM-DD>.md`: counts per classification,
  split by api/site, plus a list of `honest_blocked` boards. Print the summary table at the end.

## Acceptance criteria
- [ ] `python3 -m pytest -q tests/test_ua_ab_test.py` passes, with no network access in tests
- [ ] `python3 -m pytest -q` passes in full
- [ ] Do NOT run the script against the network; the orchestrator runs it.
- [ ] No personal data, no secrets
- [ ] Commit with message `feat(scripts): honest-UA A/B test (D14)` plus a line `Co-Authored-By: Gemini 3.8 Flash (agy)`

## Report back
JSON only: {"files_changed": [...], "tests": "<pytest summary line>", "assumptions": [...], "unsure": [...]}
