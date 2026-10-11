"""Company-type taxonomy for registry tags (``company.extras->>'company_type'``), see REVAMP_PLAN 2A.5."""

from __future__ import annotations

COMPANY_TYPES = ("startup", "product", "mnc", "gcc", "services", "nonprofit", "government")

_ALIASES = {
    "unicorn": "startup",
    "soonicorn": "startup",
    "funded_startup": "startup",
    "mid_product": "product",
    "listed_product": "product",
    "mnc_gcc": "gcc",
    "it_services": "services",
    "consulting": "services",
    "ngo": "nonprofit",
}


def normalize_company_type(value: str | None) -> str:
    """Free-form category → one of COMPANY_TYPES, or "" when unknown."""
    v = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    v = _ALIASES.get(v, v)
    return v if v in COMPANY_TYPES else ""
