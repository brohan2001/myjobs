#!/usr/bin/env python3
"""Phase 1 smoke test for vendored jobseek monitors.

Exercises three end-to-end paths:
  1. Greenhouse rich monitor (Anthropic) — pure HTTP, no browser, no proxy.
  2. DOM monitor with render:true (BlackRock early-careers) — Playwright path.
  3. Workday monitor (NVIDIA) — proxy path. Skipped when PROXY_PROVIDER is unset.

Board configs are taken verbatim from jobseek's boards.csv.

Usage:
    python3 scripts/probe_jobseek_monitors.py
    PROXY_PROVIDER=webshare WEBSHARE_PROXY_URL=http://... python3 scripts/probe_jobseek_monitors.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow running as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.shared.http import create_http_client
from src.shared.logging import setup_logging
from src.core.monitor import monitor_one_stream


GREENHOUSE_ANTHROPIC = {
    "board_url": "https://job-boards.greenhouse.io/anthropic",
    "monitor_type": "greenhouse",
    "monitor_config": {"token": "anthropic"},
}

LENOVO_CAREERS = {
    "board_url": "https://jobs.lenovo.com/en_US/careers/SearchJobs",
    "monitor_type": "dom",
    "monitor_config": {
        "render": True,
        "wait": "networkidle",
        "url_filter": "/careers/JobDetail/",
        "pagination": {
            "param_name": "jobOffset",
            "start": 0,
            "increment": 10,
            "max_pages": 1,  # cap at 1 page for smoke test speed
            "browser": True,
        },
    },
}

NVIDIA_WORKDAY = {
    "board_url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
    "monitor_type": "workday",
    "monitor_config": {
        "company": "nvidia",
        "wd_instance": "wd5",
        "site": "NVIDIAExternalCareerSite",
    },
}


async def probe_greenhouse(http):
    print("\n=== 1. Greenhouse rich monitor (Anthropic) — HTTP ===")
    count = 0
    async for result in monitor_one_stream(
        GREENHOUSE_ANTHROPIC["board_url"],
        GREENHOUSE_ANTHROPIC["monitor_type"],
        GREENHOUSE_ANTHROPIC["monitor_config"],
        http,
    ):
        for url, dj in (result.jobs_by_url or {}).items():
            print(f"  [{dj.title}] {url}")
            count += 1
            if count >= 5:
                break
        if count >= 5:
            break
    print(f"  Total shown: {count} (≥1 required to pass)")
    return count >= 1


async def probe_playwright(http):
    print("\n=== 2. DOM render monitor (Lenovo careers) — Playwright ===")
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            count = 0
            async for result in monitor_one_stream(
                LENOVO_CAREERS["board_url"],
                LENOVO_CAREERS["monitor_type"],
                LENOVO_CAREERS["monitor_config"],
                http,
                pw=pw,
            ):
                for url in sorted(result.urls or []):
                    print(f"  {url}")
                    count += 1
                    if count >= 5:
                        break
                if count >= 5:
                    break
        print(f"  Total shown: {count}")
        return count >= 1
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False


async def probe_proxy(http):
    provider = os.environ.get("PROXY_PROVIDER", "")
    if not provider:
        print("\n=== 3. Workday proxy monitor (NVIDIA) — SKIPPED ===")
        print("  Set PROXY_PROVIDER=webshare + WEBSHARE_PROXY_URL=... in .env to enable.")
        return None  # None = skipped, not failed

    print(f"\n=== 3. Workday proxy monitor (NVIDIA) — provider={provider} ===")
    try:
        count = 0
        async for result in monitor_one_stream(
            NVIDIA_WORKDAY["board_url"],
            NVIDIA_WORKDAY["monitor_type"],
            NVIDIA_WORKDAY["monitor_config"],
            http,
        ):
            for url, dj in (result.jobs_by_url or {}).items():
                title = dj.title or "(no title)"
                print(f"  [{title}] {url}")
                count += 1
                if count >= 5:
                    break
            if count >= 5:
                break
        print(f"  Total shown: {count}")
        return count >= 1
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False


async def main():
    setup_logging()
    http = create_http_client()

    results = {}
    try:
        results["greenhouse"] = await probe_greenhouse(http)
        results["playwright"] = await probe_playwright(http)
        results["proxy"] = await probe_proxy(http)
    finally:
        await http.aclose()

    print("\n=== Summary ===")
    for name, ok in results.items():
        if ok is None:
            status = "SKIPPED"
        elif ok:
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  {name}: {status}")

    failed = [k for k, v in results.items() if v is False]
    if failed:
        print(f"\nFailed paths: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("\nAll tested paths passed.")


if __name__ == "__main__":
    asyncio.run(main())
