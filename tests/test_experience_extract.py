"""Years-of-experience extraction: real phrasings from Indian boards (2026-11-02 sample) and known false positives."""

import pytest

from src.core.experience_extract import extract_experience


@pytest.mark.parametrize(
    ("html", "want"),
    [
        ("<p>5+ years of experience in Java</p>", (5, None)),
        ("<li>3-5 years of software development experience</li>", (3, 5)),
        ("Minimum 3 year(s) of experience is required", (3, None)),  # Accenture
        ("<b>Experience:</b> 3-5 Years", (3, 5)),  # Wipro
        ("Your Profile Total Experience: 6-9 Years Only", (6, 9)),  # Capgemini
        ("Qualifications: Any Graduation Years of Experience: 3 to 5 years About Accenture", (3, 5)),
        ("Years of Exp: 10 to 15 years", (10, 15)),
        ("Experience: &gt;10 YEARS", (10, None)),
        ("Experience : 2–6 Years", (2, 6)),
        ("3 to 5 years of relevant experience", (3, 5)),
    ],
)
def test_extracts(html, want):
    got = extract_experience(html)
    assert got is not None and (got.min_years, got.max_years) == want


@pytest.mark.parametrize(
    "html",
    [
        "Educational Qualification : 15 years full time education",
        "For over 25 years, Acme has been a leader in payments.",
        "With its strong over 55-year heritage, Capgemini is trusted by its clients",
        "We offer a 2 year warranty on all products.",
        "Experience the culture: 5 days a week in office",
    ],
)
def test_ignores(html):
    assert extract_experience(html) is None
