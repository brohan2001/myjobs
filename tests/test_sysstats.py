from __future__ import annotations

from src.sysstats import _service, parse_cpu_quota, parse_systemctl_show

SHOW = """Id=myjobs.slice
ActiveState=active
MemoryCurrent=4000000000
MemoryMax=5368709120
CPUUsageNSec=1000000000
CPUQuotaPerSecUSec=3s

Id=myjobs-web.service
ActiveState=active
NRestarts=2
MemoryCurrent=[not set]
MemoryMax=infinity
CPUUsageNSec=2500000000
CPUQuotaPerSecUSec=infinity
"""


def test_parse_systemctl_show():
    units = parse_systemctl_show(SHOW)
    assert list(units) == ["myjobs.slice", "myjobs-web.service"]
    assert units["myjobs-web.service"]["NRestarts"] == "2"


def test_parse_cpu_quota():
    assert parse_cpu_quota("3s") == 300.0
    assert parse_cpu_quota("500ms") == 50.0
    assert parse_cpu_quota("infinity") is None
    assert parse_cpu_quota(None) is None


def test_service_cpu_percent_from_two_samples():
    units = parse_systemctl_show(SHOW)
    before = {**units["myjobs-web.service"], "CPUUsageNSec": "500000000"}
    s = _service(units["myjobs-web.service"], before, elapsed=1.0)
    assert s["cpu_percent"] == 200.0  # 2 s of CPU in 1 s = two cores
    assert s["memory_bytes"] is None and s["memory_max_bytes"] is None and s["restarts"] == 2
    slice_ = _service(units["myjobs.slice"], None, elapsed=1.0)
    assert slice_["cpu_quota_percent"] == 300.0 and slice_["memory_max_bytes"] == 5368709120
    assert slice_["cpu_percent"] is None
