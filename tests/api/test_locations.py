from __future__ import annotations

from src.api.locations import LocationIndex

from .conftest import APAC_ID, BLR_ID, CA_ID, IN_ID, KA_ID, SF_ID, US_ID


def test_loaded(index):
    assert index.loaded
    assert not LocationIndex().loaded


def test_country_of(index):
    assert index.country_of(BLR_ID) == IN_ID
    assert index.country_of(KA_ID) == IN_ID
    assert index.country_of(IN_ID) == IN_ID
    assert index.country_of(SF_ID) == US_ID
    assert index.country_of(APAC_ID) is None
    assert index.country_of(99999) is None


def test_country_code(index):
    assert index.country_code(BLR_ID) == "IN"
    assert index.country_code(SF_ID) == "US"
    assert index.country_code(APAC_ID) is None


def test_descendants_country(index):
    assert set(index.descendants(IN_ID)) == {IN_ID, KA_ID, BLR_ID}
    assert set(index.descendants(CA_ID)) == {CA_ID, SF_ID}
    assert index.descendants(BLR_ID) == [BLR_ID]


def test_descendants_macro_expands_to_members(index):
    assert set(index.descendants(APAC_ID)) == {APAC_ID, IN_ID, KA_ID, BLR_ID}
    assert US_ID not in index.descendants(APAC_ID)


def test_descendants_unknown_is_self(index):
    assert index.descendants(424242) == [424242]


def test_descendants_cached(index):
    assert index.descendants(IN_ID) is index.descendants(IN_ID)


def test_ids_for_code(index):
    assert set(index.ids_for_code("IN")) == {IN_ID, KA_ID, BLR_ID}
    assert set(index.ids_for_code("in")) == {IN_ID, KA_ID, BLR_ID}
    assert set(index.ids_for_code(" us ")) == {US_ID, CA_ID, SF_ID}
    assert set(index.ids_for_code("apac")) == set(index.descendants(APAC_ID))
    assert set(index.ids_for_code("IN.19")) == {KA_ID, BLR_ID}


def test_ids_for_code_unknown(index):
    assert index.ids_for_code("ZZ") is None
    assert index.ids_for_code("") is None


def test_label(index):
    assert index.label(BLR_ID) == "Bengaluru, India"
    assert index.label(KA_ID) == "Karnataka, India"
    assert index.label(IN_ID) == "India"
    assert index.label(APAC_ID) == "Asia Pacific"
    assert index.label(SF_ID) == "San Francisco, United States"
    assert index.label(99999) == ""


def test_search_prefix_and_case(index):
    assert index.search("ben") == [BLR_ID]
    assert index.search("  BEN ") == [BLR_ID]
    assert index.search("") == []
    assert index.search("zzz") == []


def test_search_excludes_regions(index):
    assert index.search("kar") == []
    assert index.search("cal") == []


def test_search_ordering_macro_country_city_population():
    rows = [
        {"id": 1, "parent_id": None, "type": "country", "code": "AA", "population": 5, "name": "Aland"},
        {"id": 2, "parent_id": 1, "type": "city", "code": None, "population": 10, "name": "Alpha Big"},
        {"id": 3, "parent_id": 1, "type": "city", "code": None, "population": 99, "name": "Alpha Huge"},
        {"id": -1, "parent_id": None, "type": "macro", "code": "AM", "population": 0, "name": "Alpine Macro"},
        {"id": 4, "parent_id": None, "type": "country", "code": "AB", "population": 50, "name": "Albania"},
    ]
    idx = LocationIndex.from_rows(rows)
    assert idx.search("al") == [-1, 4, 1, 3, 2]
    assert idx.search("al", limit=2) == [-1, 4]


def test_from_rows_handles_null_name_and_population():
    idx = LocationIndex.from_rows(
        [{"id": 1, "parent_id": None, "type": "country", "code": None, "population": None, "name": None}]
    )
    assert idx.names[1] == ""
    assert idx.population[1] == 0
    assert 1 not in idx.iso2


def test_search_matches_aliases():
    rows = [
        {"id": 1, "parent_id": None, "type": "country", "code": "IN", "population": 1_400_000_000, "name": "India"},
        {"id": 2, "parent_id": 1, "type": "city", "code": None, "population": 8_400_000, "name": "Bengaluru"},
        {"id": 3, "parent_id": None, "type": "country", "code": "BD", "population": 170_000_000, "name": "Bangladesh"},
    ]
    aliases = [{"location_id": 2, "name": "Bangalore"}, {"location_id": 2, "name": "Bengaluru"}]
    idx = LocationIndex.from_rows(rows, (), aliases)
    assert idx.search("bang") == [3, 2]  # countries first, then cities
    assert idx.search("Bangalore") == [2]
    assert idx.aliases[2] == ["bangalore"]  # the display name isn't repeated
