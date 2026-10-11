"""In-memory GeoNames index for the feed API.

Loaded once from ``location`` / ``location_name`` (filled by
scripts/load_geonames.py). About 40k rows, so it fits comfortably in memory and
saves a recursive query per request.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from src.logger import get_logger

log = get_logger(__name__)

_LOAD_LOCATIONS = """
SELECT l.id, l.parent_id, l.type::text AS type, l.code, l.population, n.name
FROM location l
LEFT JOIN LATERAL (
    SELECT name FROM location_name
    WHERE location_id = l.id AND locale = 'en'
    ORDER BY is_display DESC, name
    LIMIT 1
) n ON true
"""

_LOAD_MACRO_MEMBERS = "SELECT macro_id, country_id FROM location_macro_member"


@dataclass
class LocationIndex:
    names: dict[int, str] = field(default_factory=dict)
    parents: dict[int, int | None] = field(default_factory=dict)
    types: dict[int, str] = field(default_factory=dict)
    population: dict[int, int] = field(default_factory=dict)
    codes: dict[str, int] = field(default_factory=dict)  # upper-cased code → id
    iso2: dict[int, str] = field(default_factory=dict)  # country id → ISO-3166 alpha-2
    children: dict[int, list[int]] = field(default_factory=dict)
    macro_members: dict[int, list[int]] = field(default_factory=dict)
    _country_of: dict[int, int | None] = field(default_factory=dict)
    _descendants: dict[int, list[int]] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, rows, macro_rows=()) -> LocationIndex:
        idx = cls()
        for r in rows:
            loc_id = r["id"]
            idx.names[loc_id] = r["name"] or ""
            idx.parents[loc_id] = r["parent_id"]
            idx.types[loc_id] = r["type"]
            idx.population[loc_id] = r["population"] or 0
            if r["code"]:
                idx.codes[r["code"].upper()] = loc_id
                if r["type"] == "country":
                    idx.iso2[loc_id] = r["code"].upper()
            if r["parent_id"] is not None:
                idx.children.setdefault(r["parent_id"], []).append(loc_id)
        for m in macro_rows:
            idx.macro_members.setdefault(m["macro_id"], []).append(m["country_id"])
        return idx

    @property
    def loaded(self) -> bool:
        return bool(self.names)

    def country_of(self, loc_id: int) -> int | None:
        if loc_id in self._country_of:
            return self._country_of[loc_id]
        current: int | None = loc_id
        for _ in range(20):
            if current is None:
                break
            if self.types.get(current) == "country":
                break
            current = self.parents.get(current)
        result = current if current is not None and self.types.get(current) == "country" else None
        self._country_of[loc_id] = result
        return result

    def country_code(self, loc_id: int) -> str | None:
        country = self.country_of(loc_id)
        return self.iso2.get(country) if country is not None else None

    def descendants(self, loc_id: int) -> list[int]:
        """``loc_id`` plus everything below it; macros expand to member countries."""
        if loc_id in self._descendants:
            return self._descendants[loc_id]
        out: list[int] = []
        stack = [loc_id, *self.macro_members.get(loc_id, [])]
        seen: set[int] = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            stack.extend(self.children.get(cur, []))
        self._descendants[loc_id] = out
        return out

    def ids_for_code(self, code: str) -> list[int] | None:
        loc_id = self.codes.get(code.strip().upper())
        if loc_id is None:
            return None
        return self.descendants(loc_id)

    def search(self, prefix: str, limit: int = 10) -> list[int]:
        """Countries, macros and cities whose display name starts with ``prefix``."""
        needle = prefix.strip().lower()
        if not needle:
            return []
        order = {"macro": 0, "country": 1, "city": 2}
        hits = [
            loc_id for loc_id, name in self.names.items()
            if self.types.get(loc_id) in order and name.lower().startswith(needle)
        ]
        hits.sort(key=lambda i: (order[self.types[i]], -self.population.get(i, 0), self.names[i]))
        return hits[:limit]

    def label(self, loc_id: int) -> str:
        """Human label: "Bengaluru, Karnataka, India" collapses to "Bengaluru, India"."""
        name = self.names.get(loc_id, "")
        if self.types.get(loc_id) in ("country", "macro"):
            return name
        country = self.country_of(loc_id)
        if country is not None and country != loc_id:
            return f"{name}, {self.names.get(country, '')}"
        return name


async def load_location_index(pool: asyncpg.Pool) -> LocationIndex:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LOAD_LOCATIONS)
        macro_rows = await conn.fetch(_LOAD_MACRO_MEMBERS)
    idx = LocationIndex.from_rows(rows, macro_rows)
    log.info("api.locations.loaded", extra={"locations": len(idx.names), "codes": len(idx.codes)})
    return idx
