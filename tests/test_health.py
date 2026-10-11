from src.health import Snapshot, evaluate


def _snap(**over) -> Snapshot:
    base = dict(feed_age_minutes=5.0, active_boards=1000, overdue_boards=3, gone_last_day=0,
                by_ats={"greenhouse": (500, 2, 10), "keka": (3, 3, 3)})
    base.update(over)
    return Snapshot(**base)


def test_healthy_snapshot_has_no_alerts():
    assert evaluate(_snap()) == []


def test_each_threshold_fires():
    checks = {a.check for a in evaluate(_snap(
        feed_age_minutes=600, overdue_boards=200, gone_last_day=50,
        by_ats={"workday": (40, 20, 0), "ashby": (100, 0, 60)},
    ))}
    assert checks == {"feed_stale", "worker_behind", "boards_gone", "ats_failing", "ats_empty"}


def test_small_ats_groups_are_ignored():
    assert evaluate(_snap(by_ats={"keka": (3, 3, 3)})) == []


def test_empty_feed_alerts():
    assert [a.check for a in evaluate(_snap(feed_age_minutes=None))] == ["feed_stale"]
