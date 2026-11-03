"""A salary beyond the int4 salary columns is dropped, not left to fail the board's insert."""

from src.processing.cpu import _extract_salary_fields


def test_salary_beyond_int4_is_dropped():
    assert _extract_salary_fields("Salary: VND 2,500,000,000 - 3,000,000,000 per year", {}) == (None,) * 5


def test_normal_salary_kept():
    assert _extract_salary_fields("Salary: $120,000 - $150,000 per year", {"USD": 0.9})[:3] == (120000, 150000, "USD")
