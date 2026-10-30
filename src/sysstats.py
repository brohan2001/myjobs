"""Host and service resource usage for /api/admin/system (D30).

Reads psutil for the machine, ``systemctl --user show`` for the myjobs units and their slice budget, ``docker stats``
for Postgres and Redis, and sysfs for the iGPU clock. Anything unavailable (say, on a Mac) comes back as null.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import time
from pathlib import Path

import psutil

UNITS = ("myjobs.slice", "myjobs-api.service", "myjobs-web.service", "myjobs-worker.service", "myjobs-backup.service")
_PROPS = "Id,ActiveState,SubState,NRestarts,MemoryCurrent,MemoryPeak,MemoryMax,CPUUsageNSec,CPUQuotaPerSecUSec," \
         "ActiveEnterTimestampMonotonic"
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


def _containers(text: str | None) -> list[dict]:
    rows = []
    for line in (text or "").splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        rows.append({"name": c.get("Name"), "cpu_percent": c.get("CPUPerc"), "memory": c.get("MemUsage"),
                     "memory_percent": c.get("MemPerc")})
    return rows


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
    docker = asyncio.create_task(_run("docker", "stats", "--no-stream", "--format", "{{json .}}"))
    before, t0 = await _units(), time.monotonic()
    await asyncio.sleep(_SAMPLE_S)
    after, elapsed = await _units(), time.monotonic() - t0
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
        "containers": _containers(await docker),
    }


async def snapshot() -> dict:
    """Current usage, cached for a few seconds so a refreshing admin page doesn't keep sampling."""
    global _cache
    async with _lock:
        if _cache is None or time.monotonic() - _cache[0] > _CACHE_S:
            _cache = (time.monotonic(), await _collect())
        return _cache[1]
