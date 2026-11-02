"""Tests for scripts/load_geonames.py (no network, no DB)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from src.core.location_resolve import LocationResolver

_spec = importlib.util.spec_from_file_location(
    "load_geonames", Path(__file__).resolve().parent.parent / "scripts" / "load_geonames.py"
)
lg = importlib.util.module_from_spec(_spec)
sys.modules["load_geonames"] = lg
_spec.loader.exec_module(lg)


def _cty(iso, iso3, name, pop, cont, langs, gid):
    f = [iso, iso3, "000", "XX", name, "Cap", "1", str(pop), cont, ".x", "XXX", "Cur",
         "1", "", "", langs, str(gid), "", ""]
    return "\t".join(f)


COUNTRY_TXT = "\n".join([
    "# GeoNames country info",
    "#ISO\tISO3\t...",
    _cty("IN", "IND", "India", 1352617328, "AS", "en-IN,hi,bn,te,mr,ta,ur,gu,kn,ml,or,pa,as,bh,sat,ks,ne,sd,kok,doi,mni,sit,sa,fr,lus,inc", 1269750),
    _cty("US", "USA", "United States", 327167434, "NA", "en-US,es-US,haw,fr", 6252001),
    _cty("GB", "GBR", "United Kingdom", 66488991, "EU", "en-GB,cy-GB,gd", 2635167),
    _cty("DE", "DEU", "Germany", 82927922, "EU", "de", 2921044),
    _cty("CZ", "CZE", "Czechia", 10625695, "EU", "cs,sk", 3077311),
    _cty("MX", "MEX", "Mexico", 126190788, "NA", "es-MX", 3996063),
    _cty("BR", "BRA", "Brazil", 209469333, "SA", "pt-BR,es,en", 3469034),
    _cty("JP", "JPN", "Japan", 126529100, "AS", "ja", 1861060),
    _cty("AE", "ARE", "United Arab Emirates", 9630959, "AS", "ar-AE", 290557),
])

ADMIN1_TXT = "\n".join([
    "IN.19\tKarnataka\tKarnataka\t1267701",
    "IN.16\tHaryana\tHaryana\t1270260",
    "IN.16x\tBroken\tBroken\tnotanumber",
    "IN.11\tMaharashtra\tMaharashtra\t1264418",
    "US.NY\tNew York\tNew York\t5128638",
    "US.DC\tWashington, D.C.\tWashington, D.C.\t4138106",
])


def _city(gid, name, ascii_, alts, lat, lng, cc, a1, pop):
    f = [str(gid), name, ascii_, alts, str(lat), str(lng), "P", "PPLA", cc, "", a1,
         "", "", "", str(pop), "", "0", "Asia/Kolkata", "2020-01-01"]
    return "\t".join(f)


CITY_LINES = [
    _city(1277333, "Bengaluru", "Bengaluru", "BLR,Bangalore,Bengalore,Bengaluru,ಬೆಂಗಳೂರು,Bangaluru", 12.97, 77.59, "IN", "19", 8443675),
    _city(1270642, "Gurugram", "Gurugram", "Gurgaon,Gurugram,गुरुग्राम,Guru", 28.46, 77.03, "IN", "16", 876824),
    _city(1275339, "Mumbai", "Mumbai", "Bombay,Mumbai,Bambai", 19.07, 72.88, "IN", "11", 12691836),
    _city(5128581, "New York City", "New York City", "NYC,New York", 40.71, -74.0, "US", "NY", 8804190),
    _city(2643743, "London", "London", "Londres,London", 51.5, -0.12, "GB", "ENG", 8961989),
]


@pytest.fixture(scope="module")
def parsed():
    return (
        lg.parse_country_info(COUNTRY_TXT),
        lg.parse_admin1(ADMIN1_TXT),
        lg.parse_cities(CITY_LINES + ["garbage line"]),
    )


@pytest.fixture(scope="module")
def rows(parsed):
    return lg.build_rows(*parsed)


def _loc(rows, gid):
    return next(r for r in rows.locations if r[0] == gid)


def _names(rows, gid):
    return {n: d for (i, _l, n, d) in rows.names if i == gid}


def test_parse_counts(parsed):
    countries, admin1, cities = parsed
    assert len(countries) == 9
    assert len(admin1) == 5  # broken row dropped
    assert len(cities) == 5


def test_languages_normalised(parsed):
    india = next(c for c in parsed[0] if c.iso2 == "IN")
    assert india.languages[:3] == ("en", "hi", "bn")
    assert all(len(x) == 2 for x in india.languages)
    us = next(c for c in parsed[0] if c.iso2 == "US")
    assert us.languages == ("en", "es", "fr")  # 'haw' dropped


def test_parent_chains_and_codes(rows):
    assert _loc(rows, 1277333)[1:3] == (1267701, "city")  # Bengaluru -> Karnataka
    assert _loc(rows, 1267701)[1:3] == (1269750, "region")  # Karnataka -> India
    assert _loc(rows, 1269750)[1] is None
    assert _loc(rows, 2643743)[1] == 2635167  # unknown admin1 -> country
    assert _loc(rows, 1269750)[7] == "IN"
    assert _loc(rows, 1267701)[7] == "IN.19"
    assert _loc(rows, 1277333)[7] is None
    assert _loc(rows, lg.MACROS["EU"])[7] == "EU"
    assert _loc(rows, lg.MACROS["North America"])[7] == "NA"
    assert _loc(rows, 1277333)[5:7] == (12.97, 77.59)


def test_display_names(rows):
    assert _names(rows, 1277333)["Bengaluru"] is True
    assert _names(rows, 1269750)["India"] is True
    assert _names(rows, 4138106)["Washington, D.C."] is True
    assert sum(1 for d in _names(rows, 1277333).values() if d) == 1


def test_city_aliases(rows):
    n = _names(rows, 1277333)
    assert "Bangalore" in n and n["Bangalore"] is False
    assert "BLR" not in n  # < 4 chars
    assert not any(ord(c) > 0x250 for k in n for c in k)  # non-Latin filtered
    assert "Gurgaon" in _names(rows, 1270642)
    assert "Bombay" in _names(rows, 1275339)


def test_explicit_aliases(rows):
    assert "Bangalore" in _names(rows, 1277333)
    assert "District of Columbia" in _names(rows, 4138106)
    assert "UK" in _names(rows, 2635167)
    assert "Czechia" in _names(rows, 3077311)
    # no Kolkata/Chennai in the sample, so these must be silently skipped
    all_names = {n for (_i, _l, n, _d) in rows.names}
    assert "Calcutta" not in all_names and "Madras" not in all_names


def test_iso_codes_not_registered_as_names(rows):
    all_names = {n for (_i, _l, n, _d) in rows.names}
    assert "IN" not in all_names and "IND" not in all_names


def test_macros(rows):
    def members(name):
        mid = lg.MACROS[name]
        return {c for m, c in rows.macro_members if m == mid}

    assert all(m < 0 for m in lg.MACROS.values())
    assert members("EU") == {2921044, 3077311}  # DE, CZ
    assert 1269750 in members("APAC") and 1269750 in members("Asia")
    assert 290557 not in members("APAC") and 290557 in members("EMEA")
    assert 2635167 in members("Europe") and 2635167 not in members("EU")
    assert members("North America") == {6252001, 3996063}
    assert 3469034 in members("LATAM") and 3996063 in members("LATAM")
    assert 6252001 not in members("LATAM")


def test_resolver_integration(rows):
    r = LocationResolver()
    r._init_db(":memory:")
    cur = r._db.cursor()
    cur.executemany(
        "INSERT INTO entry (id, parent_id, loc_type, population, languages) VALUES (?,?,?,?,?)",
        [(i, p, t, pop or 0, ",".join(langs)) for (i, p, t, pop, langs, *_rest) in rows.locations],
    )
    pairs = set()
    for (i, _l, n, _d) in rows.names:
        for v in r._name_variants(n.lower()):
            pairs.add((v, i))
    cur.executemany("INSERT INTO name_index (name, location_id) VALUES (?,?)", sorted(pairs))
    disp = {}
    for (i, _l, n, d) in rows.names:
        if d or i not in disp:
            disp[i] = n
    cur.executemany("INSERT INTO display_name (location_id, name) VALUES (?,?)", disp.items())
    r._db.commit()

    got = r.resolve(["Bangalore, India"])
    assert [x.location_id for x in got] == [1277333]
    assert [x.location_id for x in r.resolve(["Gurgaon"])] == [1270642]
    assert [x.location_id for x in r.resolve(["Mumbai, IN"])] == [1275339]
    assert r.display_name(1277333) == "Bengaluru"
