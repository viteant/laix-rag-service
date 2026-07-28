"""Lightweight worker runtime metrics without Docker socket access."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path


def _read_cgroup_int(name: str) -> int | None:
    try:
        value = Path("/sys/fs/cgroup", name).read_text().strip()
    except OSError:
        return None
    return None if value == "max" else int(value)


def worker_runtime_snapshot() -> dict[str, int | float | str | None]:
    """Return the worker container's resource usage and host load average."""
    load_1, load_5, load_15 = os.getloadavg()
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "memory_bytes": _read_cgroup_int("memory.current"),
        "memory_limit_bytes": _read_cgroup_int("memory.max"),
        "swap_bytes": _read_cgroup_int("memory.swap.current"),
        "swap_limit_bytes": _read_cgroup_int("memory.swap.max"),
        "load_1": round(load_1, 2),
        "load_5": round(load_5, 2),
        "load_15": round(load_15, 2),
    }
