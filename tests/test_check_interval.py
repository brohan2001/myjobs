from src.sync import _check_interval


def test_slow_types_and_browser_boards_are_checked_every_3h():
    assert _check_interval("dom", False) == "180"
    assert _check_interval("workday", False) == "180"
    assert _check_interval("darwinbox", True) == "180"


def test_api_boards_stay_hourly():
    assert _check_interval("greenhouse", False) == "60"
