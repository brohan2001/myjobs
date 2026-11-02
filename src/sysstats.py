"""Host and service resource usage for /api/admin/system (D30).

Reads psutil for the machine, ``systemctl --user show`` for the myjobs units and their slice budget, the Docker
containers' cgroups for Postgres and Redis (no Docker socket needed), and sysfs for the iGPU clock. Anything unavailable (say, on a Mac) comes back as null.
"""

from __future__ import annotations

import asyncio
import glob
import os
import time
from pathlib import Path

import psutil

UNITS = ("myjobs.slice", "myjobs-api.service", "myjobs-web.service", "myjobs-worker.service", "myjobs-backup.service")
_PROPS = "Id,ActiveState,SubState,NRestarts,MemoryCurrent,MemoryPeak,MemoryMax,CPUUsageNSec,CPUQuotaPerSecUSec," \
         "ActiveEnterTimestampMonotonic"
_DOCKER_CGROUPS = "/sys/fs/cgroup/system.slice/docker-*.scope"
_SAMPLE_S = 1.0
_CACHE_S = 10.0
_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()


def parse_systemctl_show(text: str) -> dict[str, dict[str, str]]:
    """``systemctl show A B -p ...`` prints one KEY=VALUE block per unit, separated by blank lines."""
    units: dict[str, dict[str, str]] = {}
    for block in text.strip().split("\n\n"):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if props.get("Id"):
            units[props["Id"]] = props
    return units


def _int(value: str | None) -> int | None:
    """systemd numbers; ``[not set]`` and ``infinity`` mean no value."""
    return int(value) if value and value.isdigit() else None


def parse_cpu_quota(value: str | None) -> float | None:
    """``CPUQuotaPerSecUSec`` → percent of one CPU: ``3s`` → 300.0, ``500ms`` → 50.0, ``infinity`` → None."""
    if not value or value == "infinity":
        return None
    if value.endswith("ms"):
        return float(value[:-2]) / 10
    if value.endswith("s"):
        return float(value[:-1]) * 100
    return None


async def _run(*cmd: str) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
    except (OSError, TimeoutError):
        return None
    return out.decode() if proc.returncode == 0 else None


async def _units() -> dict[str, dict[str, str]]:
    out = await _run("systemctl", "--user", "show", *UNITS, "-p", _PROPS)
    return parse_systemctl_show(out) if out else {}


def _gpu() -> dict | None:
    """Intel iGPU clock (i915 sysfs): actual vs max MHz. 0 MHz means idle; nothing in myjobs uses the GPU."""
    for card in sorted(glob.glob("/sys/class/drm/card*/gt_act_freq_mhz")):
        base = Path(card).parent
        try:
            act = int((base / "gt_act_freq_mhz").read_text())
            top = int((base / "gt_RP0_freq_mhz").read_text())
        except (OSError, ValueError):
            continue
        return {"freq_mhz": act, "max_mhz": top, "percent": round(100 * act / top, 1) if top else None}
    return None


def _cpu_temp() -> float | None:
    read = getattr(psutil, "sensors_temperatures", None)
    temps = read() if read else {}
    for chip in ("coretemp", "k10temp", "acpitz"):
        if temps.get(chip):
            return max(t.current for t in temps[chip])
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def parse_cpu_max(text: str | None) -> float | None:
    """cgroup v2 ``cpu.max`` → percent of one CPU: ``100000 100000`` → 100.0, ``max 100000`` → None."""
    quota, _, period = (text or "").partition(" ")
    return round(100 * int(quota) / int(period), 1) if quota.isdigit() and period.isdigit() else None


def _containers() -> dict[str, dict]:
    """Docker containers by process name (postgres, redis-server), from their cgroups."""
    out = {}
    for scope in glob.glob(_DOCKER_CGROUPS):
        base = Path(scope)
        pid = ((_read(base / "cgroup.procs") or "").split() or [""])[0]
        usage = next((line.split()[1] for line in (_read(base / "cpu.stat") or "").splitlines()
                      if line.startswith("usage_usec ")), None)
        out[_read(Path(f"/proc/{pid}/comm")) or base.name[7:19]] = {
            "cpu_usec": int(usage) if usage else None,
            "memory_bytes": _int(_read(base / "memory.current")),
            "memory_max_bytes": _int(_read(base / "memory.max")),
            "cpu_quota_percent": parse_cpu_max(_read(base / "cpu.max")),
        }
    return out


def _container(name: str, now: dict, then: dict | None, elapsed: float) -> dict:
    cpu = now.pop("cpu_usec")
    before = (then or {}).get("cpu_usec")
    cpu_percent = round((cpu - before) / 1e6 / elapsed * 100, 1) if cpu is not None and before is not None else None
    return {"name": name, "cpu_percent": cpu_percent, **now}


def _service(props: dict[str, str], before: dict[str, str] | None, elapsed: float) -> dict:
    cpu_now, cpu_then = _int(props.get("CPUUsageNSec")), _int((before or {}).get("CPUUsageNSec"))
    started = _int(props.get("ActiveEnterTimestampMonotonic"))
    return {
        "unit": props["Id"],
        "state": props.get("ActiveState"),
        "sub_state": props.get("SubState"),
        "restarts": _int(props.get("NRestarts")),
        "uptime_s": round(time.monotonic() - started / 1e6) if started else None,
        "memory_bytes": _int(props.get("MemoryCurrent")),
        "memory_peak_bytes": _int(props.get("MemoryPeak")),
        "memory_max_bytes": _int(props.get("MemoryMax")),
        "cpu_percent": round((cpu_now - cpu_then) / 1e9 / elapsed * 100, 1)
        if cpu_now is not None and cpu_then is not None else None,
        "cpu_quota_percent": parse_cpu_quota(props.get("CPUQuotaPerSecUSec")),
    }


async def _collect() -> dict:
    psutil.cpu_percent(percpu=True)  # primes the per-core counters for the sample below
    before, containers_before, t0 = await _units(), _containers(), time.monotonic()
    await asyncio.sleep(_SAMPLE_S)
    after, containers_after, elapsed = await _units(), _containers(), time.monotonic() - t0
    vm, swap, disk = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage("/")
    return {
        "host": {
            "cpu_count": psutil.cpu_count(),
            "cpu_percent_per_core": psutil.cpu_percent(percpu=True),
            "load_avg": [round(x, 2) for x in os.getloadavg()],
            "cpu_temp_c": _cpu_temp(),
            "memory": {"total": vm.total, "used": vm.total - vm.available, "percent": vm.percent},
            "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
            "disk": {"total": disk.total, "used": disk.used, "percent": disk.percent},
            "gpu": _gpu(),
        },
        "services": [_service(p, before.get(unit), elapsed) for unit, p in after.items()],
        "containers": [_container(name, c, containers_before.get(name), elapsed)
                       for name, c in sorted(containers_after.items())],
    }


async def snapshot() -> dict:
    """Current usage, cached for a few seconds so a refreshing admin page doesn't keep sampling."""
    global _cache
    async with _lock:
        if _cache is None or time.monotonic() - _cache[0] > _CACHE_S:
            _cache = (time.monotonic(), await _collect())
        return _cache[1]
