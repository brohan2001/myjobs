import csv
from pathlib import Path

import pytest

from src.company_type import COMPANY_TYPES, normalize_company_type


@pytest.mark.parametrize("raw, expected", [
    ("unicorn", "startup"), ("Funded Startup", "startup"), ("mnc_gcc", "gcc"), ("listed-product", "product"),
    ("MNC", "mnc"), ("", ""), (None, ""), ("spaceship", ""),
])
def test_normalize(raw, expected):
    assert normalize_company_type(raw) == expected


def test_registry_uses_only_known_company_types():
    path = Path(__file__).resolve().parent.parent / "data" / "companies.csv"
    with open(path, newline="", encoding="utf-8") as f:
        bad = {r["company_type"] for r in csv.DictReader(f)} - set(COMPANY_TYPES) - {""}
    assert not bad
