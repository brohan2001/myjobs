#!/usr/bin/env python3
"""Load GeoNames data into the ``location*`` tables used by LocationResolver.

Data: https://download.geonames.org/export/dump/ (CC-BY 4.0, attribution to
GeoNames required).  Files: countryInfo.txt, admin1CodesASCII.txt,
cities15000.zip.

Tables filled (see src/migrations/versions/0007_taxonomy_tables.py):
  location(id, parent_id, type, population, languages, lat, lng, code)  (code: migration 0009)
  location_name(location_id, locale, name, is_display)
  location_macro_member(macro_id, country_id)

Notes on what ``src/core/location_resolve.py`` expects:
  * Names are matched lowercased from locales en/de/fr/it/alt/''.  Everything
    is loaded as ``en`` here.
  * ISO2/ISO3 codes and "UK"/"US"/"UAE" are handled by hardcoded maps in the
    resolver, which look up the *country name*.  Registering codes as names
    would be harmful ("IN", "DE", "OR" would collide with real words), so they
    are intentionally NOT added.  Country names must match the resolver's
    spelling, hence COUNTRY_ALIASES below.
  * Parent chain city -> admin1 region -> country; macros have no parent and
    are linked through location_macro_member only.

Usage:
    python3 scripts/load_geonames.py --dry-run
    python3 scripts/load_geonames.py --dsn postgresql://crawler:crawler@localhost:5432/crawler
"""
from __future__ import annotations

import argparse
import asyncio
import io
import ssl
import sys
import unicodedata
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.logger import get_logger  # noqa: E402

log = get_logger(__name__)

BASE_URL = "https://download.geonames.org/export/dump/"
# GeoNames writes Indian place names with transliteration marks ("Rājkot"); people write "Rajkot".
ASCII_DISPLAY_COUNTRIES = frozenset({"IN"})

FILES = ("countryInfo.txt", "admin1CodesASCII.txt", "cities15000.zip")
DEFAULT_CACHE = Path.home() / ".cache" / "myjobs" / "geonames"
LOCALE = "en"
MIN_ALIAS_LEN = 4

MACRO_CODES: dict[str, str] = {
    "EU": "EU",
    "EMEA": "EMEA",
    "APAC": "APAC",
    "LATAM": "LATAM",
    "North America": "NA",
    "Europe": "EUROPE",
    "Asia": "ASIA",
    "Americas": "AMERICAS",
    "MENA": "MENA",
}

# Synthetic ids for macro regions.  GeoNames ids are positive, so negatives
# never collide.  location.id is INTEGER (no CHECK > 0 in the migration).
MACROS: dict[str, int] = {
    "EU": -1,
    "EMEA": -2,
    "APAC": -3,
    "LATAM": -4,
    "North America": -5,
    "Europe": -6,
    "Asia": -7,
    "Americas": -8,
    "MENA": -9,
}

_EU = (
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE"
).split()
_MIDDLE_EAST = "AE BH EG IL IQ IR JO KW LB OM PS QA SA SY TR YE".split()
_MENA = _MIDDLE_EAST + "DZ LY MA TN SD EH MR DJ".split()
_NORTH_AMERICA_CORE = ["US", "CA"]
_NOT_LATAM_NA = {"US", "CA", "BM", "GL", "PM"}

# Names the resolver uses that GeoNames spells differently: (alias, ISO2).
COUNTRY_ALIASES: list[tuple[str, str]] = [
    ("Czechia", "CZ"),
    ("Eswatini", "SZ"),
    ("North Macedonia", "MK"),
    ("Ivory Coast", "CI"),
    ("Cape Verde", "CV"),
    ("Laos", "LA"),
    ("Russia", "RU"),
    ("South Korea", "KR"),
    ("Vietnam", "VN"),
    ("Brunei", "BN"),
    ("Syria", "SY"),
    ("Turkey", "TR"),
    ("Myanmar", "MM"),
    ("Bolivia", "BO"),
    ("Venezuela", "VE"),
    ("Tanzania", "TZ"),
    ("Gambia", "GM"),
    ("Bahamas", "BS"),
    ("Hong Kong", "HK"),
    ("Taiwan", "TW"),
    ("Congo", "CD"),
    ("USA", "US"),
    ("UK", "GB"),
    ("Great Britain", "GB"),
    ("UAE", "AE"),
]

# Region aliases: (alias, ISO2, admin1 code).
REGION_ALIASES: list[tuple[str, str, str]] = [
    ("District of Columbia", "US", "DC"),
]

# City aliases GeoNames may lack: (alias, ISO2, [candidate ascii names, first match wins]).
CITY_ALIASES: list[tuple[str, str, list[str]]] = [
    ("Bangalore", "IN", ["Bengaluru", "Bangalore"]),
    ("Gurgaon", "IN", ["Gurugram", "Gurgaon"]),
    ("Bombay", "IN", ["Mumbai"]),
    ("Madras", "IN", ["Chennai"]),
    ("Calcutta", "IN", ["Kolkata"]),
    ("Navi Mumbai", "IN", ["Navi Mumbai", "Mumbai"]),
    ("Noida", "IN", ["Noida", "New Delhi"]),
    ("Thane", "IN", ["Thane", "Mumbai"]),
    ("Secunderabad", "IN", ["Secunderabad", "Hyderabad"]),
    ("Cochin", "IN", ["Kochi", "Cochin"]),
    ("Kochi", "IN", ["Kochi", "Cochin"]),
    ("Trivandrum", "IN", ["Thiruvananthapuram", "Trivandrum"]),
    ("New York City", "US", ["New York City"]),
]


# ── Parsers (pure) ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Country:
    iso2: str
    iso3: str
    name: str
    population: int
    continent: str
    languages: tuple[str, ...]
    geoname_id: int


@dataclass(frozen=True, slots=True)
class Admin1:
    code: str  # "US.NY"
    name: str
    ascii_name: str
    geoname_id: int

    @property
    def country_iso2(self) -> str:
        return self.code.split(".", 1)[0]


@dataclass(frozen=True, slots=True)
class City:
    geoname_id: int
    name: str
    ascii_name: str
    alternates: tuple[str, ...]
    lat: float
    lng: float
    country_iso2: str
    admin1_code: str
    population: int


@dataclass
class Rows:
    # (id, parent_id, type, population, languages, lat, lng, code)
    locations: list[tuple] = field(default_factory=list)
    # (location_id, locale, name, is_display)
    names: list[tuple] = field(default_factory=list)
    # (macro_id, country_id)
    macro_members: list[tuple] = field(default_factory=list)


def normalise_languages(raw: str) -> tuple[str, ...]:
    """'en-IN,hi,bn' -> ('en', 'hi', 'bn'); drops non-2-letter codes, dedupes."""
    out: list[str] = []
    for part in raw.split(","):
        code = part.strip().split("-", 1)[0].lower()
        if len(code) == 2 and code.isalpha() and code not in out:
            out.append(code)
    return tuple(out)


def parse_country_info(text: str) -> list[Country]:
    out: list[Country] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 17 or not f[16].strip().isdigit():
            continue
        try:
            pop = int(f[7] or 0)
        except ValueError:
            pop = 0
        out.append(
            Country(
                iso2=f[0],
                iso3=f[1],
                name=f[4],
                population=pop,
                continent=f[8],
                languages=normalise_languages(f[15]),
                geoname_id=int(f[16]),
            )
        )
    return out


def parse_admin1(text: str) -> list[Admin1]:
    out: list[Admin1] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 4 or not f[3].strip().isdigit() or "." not in f[0]:
            continue
        out.append(Admin1(code=f[0], name=f[1], ascii_name=f[2], geoname_id=int(f[3])))
    return out


def parse_cities(lines: Iterable[str]) -> list[City]:
    out: list[City] = []
    for line in lines:
        line = line.rstrip("\n")
        f = line.split("\t")
        if len(f) < 15 or not f[0].isdigit():
            continue
        try:
            out.append(
                City(
                    geoname_id=int(f[0]),
                    name=f[1],
                    ascii_name=f[2],
                    alternates=tuple(a for a in f[3].split(",") if a),
                    lat=float(f[4]),
                    lng=float(f[5]),
                    country_iso2=f[8],
                    admin1_code=f[10],
                    population=int(f[14] or 0),
                )
            )
        except ValueError:
            continue
    return out


@lru_cache(maxsize=4096)
def _is_latin_char(c: str) -> bool:
    if c in " -'.":
        return True
    try:
        return c.isalpha() and unicodedata.name(c).startswith("LATIN")
    except ValueError:
        return False


def is_latin_alias(name: str) -> bool:
    """Latin-script name of at least MIN_ALIAS_LEN chars (letters, space, - ' .)."""
    name = name.strip()
    return len(name) >= MIN_ALIAS_LEN and all(_is_latin_char(c) for c in name)


# ── Row building (pure) ──────────────────────────────────────────────


def _macro_membership(countries: list[Country]) -> dict[str, set[str]]:
    iso_by_cont: dict[str, set[str]] = {}
    for c in countries:
        iso_by_cont.setdefault(c.continent, set()).add(c.iso2)
    me = set(_MIDDLE_EAST)
    asia = iso_by_cont.get("AS", set())
    europe = iso_by_cont.get("EU", set())
    africa = iso_by_cont.get("AF", set())
    oceania = iso_by_cont.get("OC", set())
    na = iso_by_cont.get("NA", set())
    sa = iso_by_cont.get("SA", set())
    return {
        "EU": set(_EU),
        "EMEA": europe | africa | me,
        "APAC": (asia | oceania) - me,
        "LATAM": sa | (na - _NOT_LATAM_NA),
        "North America": set(_NORTH_AMERICA_CORE) | {"MX"},
        "Europe": europe,
        "Asia": asia,
        "Americas": na | sa,
        "MENA": set(_MENA),
    }


def build_rows(
    countries: list[Country],
    admin1: list[Admin1],
    cities: list[City],
) -> Rows:
    rows = Rows()
    names: dict[tuple[int, str, str], bool] = {}

    def add_name(loc_id: int, name: str, display: bool = False) -> None:
        name = name.strip()
        if not name:
            return
        key = (loc_id, LOCALE, name)
        names[key] = names.get(key, False) or display

    country_id = {c.iso2: c.geoname_id for c in countries}

    # Countries
    for c in countries:
        rows.locations.append(
            (c.geoname_id, None, "country", c.population, list(c.languages), None, None, c.iso2)
        )
        add_name(c.geoname_id, c.name, True)
    for alias, iso2 in COUNTRY_ALIASES:
        if iso2 in country_id:
            add_name(country_id[iso2], alias)

    # Regions
    region_id: dict[tuple[str, str], int] = {}
    for a in admin1:
        parent = country_id.get(a.country_iso2)
        if parent is None:
            continue
        region_id[(a.country_iso2, a.code.split(".", 1)[1])] = a.geoname_id
        rows.locations.append((a.geoname_id, parent, "region", None, [], None, None, a.code))
        if a.country_iso2 in ASCII_DISPLAY_COUNTRIES:
            add_name(a.geoname_id, a.ascii_name, True)
            add_name(a.geoname_id, a.name)
        else:
            add_name(a.geoname_id, a.name, True)
            add_name(a.geoname_id, a.ascii_name)
    for alias, iso2, code in REGION_ALIASES:
        rid = region_id.get((iso2, code))
        if rid is not None:
            add_name(rid, alias)

    # Cities
    by_ascii: dict[tuple[str, str], City] = {}
    for ct in cities:
        parent = region_id.get((ct.country_iso2, ct.admin1_code)) or country_id.get(
            ct.country_iso2
        )
        if parent is None:
            continue
        rows.locations.append(
            (ct.geoname_id, parent, "city", ct.population, [], ct.lat, ct.lng, None)
        )
        if ct.country_iso2 in ASCII_DISPLAY_COUNTRIES:
            add_name(ct.geoname_id, ct.ascii_name, True)
            add_name(ct.geoname_id, ct.name)
        else:
            add_name(ct.geoname_id, ct.name, True)
            add_name(ct.geoname_id, ct.ascii_name)
        for alt in ct.alternates:
            if is_latin_alias(alt):
                add_name(ct.geoname_id, alt)
        key = (ct.country_iso2, ct.ascii_name.lower())
        if key not in by_ascii or ct.population > by_ascii[key].population:
            by_ascii[key] = ct
    for alias, iso2, targets in CITY_ALIASES:
        for target in targets:
            hit = by_ascii.get((iso2, target.lower()))
            if hit is not None:
                add_name(hit.geoname_id, alias)
                break
        else:
            log.warning("city alias target not found", extra={"alias": alias})

    # Macros
    members = _macro_membership(countries)
    for macro_name, macro_id in MACROS.items():
        rows.locations.append(
            (macro_id, None, "macro", None, [], None, None, MACRO_CODES[macro_name])
        )
        add_name(macro_id, macro_name, True)
        for iso2 in sorted(members.get(macro_name, ())):
            if iso2 in country_id:
                rows.macro_members.append((macro_id, country_id[iso2]))

    rows.names = [(i, loc, n, d) for (i, loc, n), d in names.items()]
    return rows


# ── Download / IO ────────────────────────────────────────────────────


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def download(cache_dir: Path, force: bool = False) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for fname in FILES:
        dest = cache_dir / fname
        if force or not dest.exists() or dest.stat().st_size == 0:
            log.info("downloading %s", fname)
            req = urllib.request.Request(BASE_URL + fname, headers={"User-Agent": "myjobs-geonames-loader"})
            with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as resp:  # noqa: S310
                data = resp.read()
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
        else:
            log.info("using cached %s", dest)
        paths[fname] = dest
    return paths


def load_files(paths: dict[str, Path]) -> Rows:
    countries = parse_country_info(paths["countryInfo.txt"].read_text(encoding="utf-8"))
    admin1 = parse_admin1(paths["admin1CodesASCII.txt"].read_text(encoding="utf-8"))
    with zipfile.ZipFile(paths["cities15000.zip"]) as zf:
        with zf.open("cities15000.txt") as fh:
            cities = parse_cities(io.TextIOWrapper(fh, encoding="utf-8"))
    return build_rows(countries, admin1, cities)


# ── Database ─────────────────────────────────────────────────────────


async def upsert(dsn: str, rows: Rows) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "CREATE TEMP TABLE _loc (id INTEGER, parent_id INTEGER, type TEXT, "
                "population INTEGER, languages TEXT[], lat REAL, lng REAL, code TEXT) ON COMMIT DROP"
            )
            await conn.execute(
                "CREATE TEMP TABLE _name (location_id INTEGER, locale TEXT, name TEXT, "
                "is_display BOOLEAN) ON COMMIT DROP"
            )
            await conn.execute(
                "CREATE TEMP TABLE _macro (macro_id INTEGER, country_id INTEGER) ON COMMIT DROP"
            )
            await conn.copy_records_to_table("_loc", records=rows.locations)
            await conn.copy_records_to_table("_name", records=rows.names)
            await conn.copy_records_to_table("_macro", records=rows.macro_members)

            for kinds in (("macro", "country"), ("region",), ("city",)):
                await conn.execute(
                    """
                    INSERT INTO location (id, parent_id, type, population, languages, lat, lng, code)
                    SELECT id, parent_id, type::location_type, population, languages, lat, lng, code
                    FROM _loc WHERE type = ANY($1::text[])
                    ON CONFLICT (id) DO UPDATE SET
                        parent_id = EXCLUDED.parent_id, type = EXCLUDED.type,
                        population = EXCLUDED.population, languages = EXCLUDED.languages,
                        lat = EXCLUDED.lat, lng = EXCLUDED.lng, code = EXCLUDED.code
                    """,
                    list(kinds),
                )
            await conn.execute(
                """
                INSERT INTO location_name (location_id, locale, name, is_display)
                SELECT location_id, locale, name, is_display FROM _name
                ON CONFLICT (location_id, locale, name) DO UPDATE SET is_display = EXCLUDED.is_display
                """
            )
            await conn.execute(
                "DELETE FROM location_macro_member WHERE macro_id = ANY($1::int[])",
                list(MACROS.values()),
            )
            await conn.execute(
                "INSERT INTO location_macro_member (macro_id, country_id) "
                "SELECT macro_id, country_id FROM _macro ON CONFLICT DO NOTHING"
            )
    finally:
        await conn.close()


def summarise(rows: Rows) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows.locations:
        counts[r[2]] = counts.get(r[2], 0) + 1
    counts["names"] = len(rows.names)
    counts["macro_members"] = len(rows.macro_members)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dsn", default=None, help="Postgres DSN (default: settings.local_database_url)")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--refresh", action="store_true", help="re-download cached files")
    ap.add_argument("--dry-run", action="store_true", help="parse and print counts only")
    args = ap.parse_args(argv)

    rows = load_files(download(args.cache_dir, force=args.refresh))
    counts = summarise(rows)
    log.info("parsed rows: %s", counts)
    if args.dry_run:
        return 0

    dsn = args.dsn
    if dsn is None:
        from src.config import settings

        dsn = settings.local_database_url
    asyncio.run(upsert(dsn, rows))
    log.info("GeoNames loaded (data CC-BY 4.0, https://www.geonames.org)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
