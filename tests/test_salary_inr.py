"""Contract for src/core/salary_inr.py: Indian salary formats → SalaryRange.

Amounts are whole rupees. "LPA" / "lakh(s) per annum" / "L" mean ×100,000 per year;
"Cr" / "crore" mean ×10,000,000. Monthly figures keep period="monthly".
"""
from __future__ import annotations

import pytest

from src.core.salary_extract import SalaryRange
from src.core.salary_inr import extract_inr

L = 100_000


@pytest.mark.parametrize(
    "text, expected",
    [
        ("CTC: 10-15 LPA", SalaryRange(10 * L, 15 * L, "INR", "yearly")),
        ("Compensation 10 - 15 LPA based on experience", SalaryRange(10 * L, 15 * L, "INR", "yearly")),
        ("₹12L - ₹18L per annum", SalaryRange(12 * L, 18 * L, "INR", "yearly")),
        ("₹ 12 Lakhs to 18 Lakhs per annum", SalaryRange(12 * L, 18 * L, "INR", "yearly")),
        ("Salary: INR 8,00,000 - 12,00,000 per annum", SalaryRange(800_000, 1_200_000, "INR", "yearly")),
        ("Rs. 6.5 - 9 LPA", SalaryRange(650_000, 900_000, "INR", "yearly")),
        ("up to 25 LPA", SalaryRange(25 * L, None, "INR", "yearly")),
        ("CTC 1.2 Cr", SalaryRange(12_000_000, None, "INR", "yearly")),
        ("Stipend: ₹40,000 per month", SalaryRange(40_000, None, "INR", "monthly")),
        ("₹50,000 - ₹70,000/month", SalaryRange(50_000, 70_000, "INR", "monthly")),
        ("18 lakh per annum fixed + variable", SalaryRange(18 * L, None, "INR", "yearly")),
        ("INR 2400000 annually", SalaryRange(2_400_000, None, "INR", "yearly")),
    ],
)
def test_extracts_inr(text, expected):
    results = extract_inr(text)
    assert results, f"nothing extracted from {text!r}"
    assert results[0] == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Competitive salary",
        "We have 15 offices and 10 L of coffee",  # no currency/salary context
        "Join 500+ engineers in Bengaluru",
        "$120,000 - $150,000 per year",  # USD, not INR
        "Rs. 500 joining voucher",  # too small to be a salary
        "Notice period: 30 days, 2-5 years experience",
    ],
)
def test_ignores_non_inr(text):
    assert extract_inr(text) == []


def test_swapped_range_is_normalised():
    assert extract_inr("15-10 LPA")[0] == SalaryRange(10 * L, 15 * L, "INR", "yearly")


def test_returns_list_of_salary_ranges():
    out = extract_inr("10-15 LPA, or 12-16 LPA for senior")
    assert all(isinstance(r, SalaryRange) for r in out)
    assert len(out) == 2


def test_unified_extractor_picks_up_inr():
    from src.core.salary_extract import extract_salary_unified

    sr = extract_salary_unified("<p>Location: Bengaluru. CTC: 18-24 LPA plus ESOPs.</p>")
    assert sr == SalaryRange(18 * L, 24 * L, "INR", "yearly")


def test_unified_extractor_still_handles_usd():
    from src.core.salary_extract import extract_salary_unified

    sr = extract_salary_unified("<p>The base pay range is $120,000 - $150,000 per year.</p>")
    assert sr is not None and sr.currency == "USD"
