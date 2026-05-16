"""Phase 2 — Claude-powered resume bullets and cover letter generation.

Each job gets a tailored output:
  - 6-8 resume bullets optimised for the job's keywords
  - A concise 3-paragraph cover letter (≤200 words)

Prompt caching: the candidate profile + base resume (system prompt) is cached
with cache_control=ephemeral so subsequent jobs that share the same role
reuse the cached prefix and only pay for the per-job user message.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import anthropic
from bs4 import BeautifulSoup

from src.config import ANTHROPIC_API_KEY, RESUME_MAP, SKILL_GROUPS

_PROFILE = """\
Name: the candidate
Email: candidate@example.com
Education: MS Computer Science, [university] (May 2025)
Visa: [redacted]
Published research: IJCNLP-AACL 2025 (constrained LLM text generation, [lab])
Target roles (priority): Backend SWE > Cloud Engineer > Fullstack SWE > Frontend > Mobile > Network Engineer > Data Scientist > ML Engineer"""

_ROLE_LABELS: dict[str, str] = {
    "backend":  "Software Engineer — Backend",
    "frontend": "Software Engineer — Frontend",
    "fullstack": "Software Engineer — Fullstack",
    "mobile":   "Software Engineer — Mobile",
    "cloud":    "Cloud / DevOps / SRE Engineer",
    "network":  "Network Engineer",
    "ds":       "Data Scientist",
    "ml":       "ML / AI Engineer",
    "other":    "Software Engineer",
}

_SYSTEM_TEMPLATE = """\
You are an expert technical resume writer helping the candidate craft targeted job applications.

## Candidate
{profile}

## Base Resume — {role_label}
{resume_text}

## Rules
- Every output must be grounded in the base resume above. Never fabricate skills, roles, or metrics.
- Tailor bullets to mirror the exact keywords and phrasing from the job description.
- Write in direct past-tense action-verb style; quantify impact wherever the resume already provides numbers.
- The cover letter opening must be a specific hook (name the company or product), not a generic intro."""


def _pdf_to_text(pdf_path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        return f"[PDF extraction failed for {pdf_path.name}: {exc}]"


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


def _matched_skills(description: str) -> list[str]:
    desc_lower = description.lower()
    return [
        kw
        for _, (_, keywords) in SKILL_GROUPS.items()
        for kw in keywords
        if kw in desc_lower
    ]


async def _generate_one(
    job: dict,
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
    resume_cache: dict[str, str],
) -> dict[str, Any]:
    role = (job.get("role_category") or "backend").lower()

    if role not in resume_cache:
        pdf_path = RESUME_MAP.get(role, RESUME_MAP["backend"])
        resume_cache[role] = _pdf_to_text(pdf_path)

    system_text = _SYSTEM_TEMPLATE.format(
        profile=_PROFILE,
        role_label=_ROLE_LABELS.get(role, "Software Engineer"),
        resume_text=resume_cache[role],
    )

    description = _strip_html(job.get("description", ""))
    matched = _matched_skills(description)

    user_content = (
        f"Company: {job.get('company_name', '')}\n"
        f"Title: {job.get('title', '')}\n"
        f"Location: {job.get('location') or 'Not specified'}\n"
        f"Visa: {'Confirmed sponsor' if job.get('visa_signal') == 1 else 'Unknown / unconfirmed'}\n"
        f"\n--- Job Description (first 4000 chars) ---\n"
        f"{description[:4000]}\n"
        f"\n--- My matched skills found in this JD ---\n"
        f"{', '.join(matched[:20]) if matched else 'none detected'}\n"
        f"\nReturn ONLY a JSON object with exactly these two keys:\n"
        f'  "resume_bullets": array of 6-8 strings (each an achievement bullet starting with an action verb)\n'
        f'  "cover_letter":   string, 3 paragraphs, ≤200 words total\n'
        f"No markdown fences. No explanation. Valid JSON only."
    )

    async with semaphore:
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "job_id": job.get("id"),
                "title": job.get("title", ""),
                "company_name": job.get("company_name", ""),
            }

    text = response.content[0].text.strip()
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        payload = json.loads(m.group(0) if m else text)
    except (json.JSONDecodeError, AttributeError):
        payload = {"resume_bullets": [], "cover_letter": text}

    usage = response.usage
    return {
        "job_id": job.get("id"),
        "company_name": job.get("company_name", ""),
        "title": job.get("title", ""),
        "url": job.get("url", ""),
        "total_score": job.get("total_score", 0),
        "role_category": role,
        "location": job.get("location", ""),
        "visa_signal": job.get("visa_signal", 0),
        "matched_skills": matched[:20],
        "resume_bullets": payload.get("resume_bullets", []),
        "cover_letter": payload.get("cover_letter", ""),
        "tokens": {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0),
            "cache_write": getattr(usage, "cache_creation_input_tokens", 0),
        },
    }


async def generate_for_shortlist(
    jobs: list[dict],
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Generate application materials for the top-N shortlisted jobs (by score)."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set — add it to .env")

    ranked = sorted(jobs, key=lambda j: j.get("total_score", 0), reverse=True)[:top_n]
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    semaphore = asyncio.Semaphore(3)
    resume_cache: dict[str, str] = {}

    try:
        tasks = [_generate_one(j, client, semaphore, resume_cache) for j in ranked]
        results = await asyncio.gather(*tasks)
    finally:
        await client.close()

    return [r for r in results if r]
