"""Tech-adjacent title check (D27). Measured on 2026-10-15 against 1,763 titles jseek.co labels by
occupation: 99.1% of tech titles kept, 94.1% of non-tech titles dropped."""

import pytest

from src.core.tech_gate import is_tech_title


@pytest.mark.parametrize("title", [
    "Software Engineer II - Java", "SDE-1", "MTS 2", "Member of Technical Staff", "Staff Software Engineer",
    "Principal Systems Software Engineer", "Java Backend Engineer", "Software Engineer Apprenticeship",
    "Graduate Engineer Trainee", "Data Analyst Intern", "Machine Learning Engineer", "Data Scientist",
    "Site Reliability Engineer", "Embedded Software Engineer", "VLSI Design Engineer", "UI/UX Designer",
    "Associate Product Manager", "Technical Program Manager", "Program Manager", "Engineering Manager",
    "Solutions Architect", "Sales Engineer", "Business Analyst", "Security Engineer", "QA Automation Engineer",
])
def test_tech_titles_are_kept(title):
    assert is_tech_title(title)


@pytest.mark.parametrize("title", [
    "Restaurant General Manager", "Crew Member", "Shift Manager", "Store Associate", "Cashier", "Barista",
    "Registered Nurse", "Pharmacist", "Warehouse Associate", "Delivery Driver", "Teacher", "Electrician",
    "Sales Associate", "Accountant", "HR Business Partner", "Customer Service Representative",
    "Marketing Manager", "Trainee",
])
def test_non_tech_titles_are_dropped(title):
    assert not is_tech_title(title)


@pytest.mark.parametrize("title", [None, "", "   "])
def test_untitled_jobs_are_kept(title):
    assert is_tech_title(title)
