from src.priority import NO_INDIA_MINUTES, NO_JOBS_MINUTES, base_interval, check_interval


def test_slow_types_and_browser_boards_are_checked_every_3h():
    assert base_interval("dom", False) == 180
    assert base_interval("workday", False) == 180
    assert base_interval("darwinbox", True) == 180


def test_api_boards_stay_hourly():
    assert base_interval("greenhouse", False) == 60


def test_india_companies_keep_the_base_interval():  # D36
    assert check_interval("india", "greenhouse", False) == 60
    assert check_interval("india", "workday", False) == 180


def test_companies_without_india_jobs_are_checked_less_often():
    assert check_interval("no_india", "greenhouse", False) == NO_INDIA_MINUTES == 720
    assert check_interval("none", "workday", True) == NO_JOBS_MINUTES == 480
