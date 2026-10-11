"""Spec for src/core/notice_period.py: the longest notice period a posting accepts, in days.

0 means immediate joiners only. None means the posting doesn't say.
"""

import pytest

from src.core.notice_period import extract_notice_period


@pytest.mark.parametrize("text, days", [
    # Immediate joiners
    ("Looking for immediate joiners.", 0),
    ("Immediate joiner preferred", 0),
    ("Notice period: Immediate", 0),
    ("Candidates who can join immediately will be preferred.", 0),
    ("Only immediate to 15 days joiners", 15),
    ("Immediate - 30 days notice", 30),
    # Explicit day counts
    ("Notice period: 30 days", 30),
    ("Notice Period - 15 Days", 15),
    ("Notice period of max 60 days", 60),
    ("Candidates with a notice period of less than 30 days", 30),
    ("Notice period should be within 45 days.", 45),
    ("Notice period: 0-30 days", 30),
    ("NP: 30 days", 30),
    ("Serving notice period / notice period up to 30 days", 30),
    # Weeks and months
    ("Notice period: 2 weeks", 14),
    ("Notice period up to 1 month", 30),
    ("Notice period: 2 months", 60),
    ("Max 3 months notice period", 90),
    ("Can join within 2 weeks", 14),
    ("Should be able to join within 30 days", 30),
    # The phrase can sit in the middle of other text
    ("Location: Bengaluru. Experience: 3-5 years. Notice period: 30 days. CTC: 12 LPA", 30),
    ("<li><strong>Notice Period:</strong> Immediate to 30 Days</li>", 30),
])
def test_extracts(text, days):
    assert extract_notice_period(text) == days


@pytest.mark.parametrize("text", [
    "",
    "We are hiring a backend engineer in Pune.",
    "Experience: 30 days of onboarding with your buddy.",   # no notice-period context
    "Paid leave of 30 days per year.",
    "Start making an impact immediately.",                  # 'immediately' without joining context
    "Employees must give 90 days notice before resigning, per company policy.",  # no 'notice period' phrase
])
def test_returns_none_without_a_notice_requirement(text):
    assert extract_notice_period(text) is None


def test_takes_the_largest_when_several_are_stated():
    text = "Immediate joiners preferred; notice period up to 30 days is acceptable."
    assert extract_notice_period(text) == 30


def test_ignores_absurd_values():
    assert extract_notice_period("Notice period: 400 days") is None


def test_handles_none_input():
    assert extract_notice_period(None) is None
