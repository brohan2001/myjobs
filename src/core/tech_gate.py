"""Is a job title tech-adjacent? (DECISIONS D27)

The feed keeps tech jobs only; everything else is dropped before it's fetched or stored. A title is
tech when the occupation taxonomy maps it to a tech occupation. Titles the taxonomy doesn't know
fall back to keywords, leaning towards keeping: losing a real tech job is worse than storing an
extra one.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from src.core.occupation_resolve import match_occupation

TECH_DOMAINS = frozenset({"software-engineering", "data-ai", "infrastructure-security", "product-design"})

# Occupations outside the tech domains that the user counts as tech-adjacent (D27).
TECH_OCCUPATIONS = frozenset({
    # PM, TPM and engineering management
    "technical-program-manager", "project-manager", "engineering-manager", "tech-lead", "scrum-master",
    # Sales and support engineering
    "sales-engineer", "customer-engineer", "support-engineer",
    # Analysts
    "business-analyst",
    # Hardware and data centres
    "electrical-engineer", "mechanical-engineer", "automation-engineer",
    "data-center-technician", "data-center-manager",
})

_OCCUPATIONS_CSV = Path(__file__).resolve().parents[2] / "data" / "occupations.csv"

# Fallback for titles the taxonomy doesn't match. Word-bounded; matched on the lowercased title.
_TECH_WORDS = re.compile(
    r"\b("
    r"software|developer|programmer|engineer(?:ing)?|sde|swe|sdet|mts|devops|devsecops|sre|"
    r"full[- ]?stack|front[- ]?end|back[- ]?end|web|mobile|android|ios|flutter|react|java|python|golang|"
    r"\.net|node(?:\.?js)?|data|analytics|machine learning|ml|mlops|ai|artificial intelligence|llm|nlp|"
    r"computer vision|deep learning|scientist|research(?:er)?|cloud|platform|infrastructure|"
    r"security|cyber|network|database|dba|systems?|it|qa|quality assurance|test(?:ing)?|automation|"
    r"firmware|embedded|hardware|silicon|asic|fpga|vlsi|chip|semiconductor|robotics|"
    r"product|designer|design|ux|ui|architect|technical|technology|tech|digital|blockchain|"
    r"salesforce|sap|erp|crm|servicenow"
    r")\b"
)


@lru_cache(maxsize=1)
def tech_occupations() -> frozenset[str]:
    """Every occupation slug that counts as tech: the tech domains plus ``TECH_OCCUPATIONS``."""
    with _OCCUPATIONS_CSV.open(encoding="utf-8") as f:
        in_domains = {row["slug"] for row in csv.DictReader(f) if row["domain"] in TECH_DOMAINS}
    return frozenset(in_domains | TECH_OCCUPATIONS)


def is_tech_title(title: str | None) -> bool:
    """True if the title is a tech-adjacent job. An empty title is kept (it can't be judged)."""
    if not title or not title.strip():
        return True
    slug = match_occupation(title)
    if slug is not None:
        return slug in tech_occupations()
    return bool(_TECH_WORDS.search(title.lower()))
