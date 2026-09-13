"""Bounded Linux host observations outside measured application processes."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


def host_observation() -> dict[str, Any]:
    """Retain sources and unavailable reads; never claim machine isolation."""
    paths = [Path('/proc/loadavg'), Path('/proc/pressure/cpu'),
             Path('/proc/pressure/memory'), Path('/proc/pressure/io')]
    paths.extend(sorted(Path('/sys/devices/system/cpu').glob(
        'cpu[0-9]*/cpufreq/scaling_governor')))
    paths.extend(sorted(Path('/sys/class/hwmon').glob('hwmon*/temp*_input')))
    sources = []
    for path in paths:
        try:
            value, error = path.read_text(encoding='utf-8'), None
        except OSError as exc:
            value, error = None, str(exc)
        sources.append({'path': str(path), 'value': value, 'error': error})
    return {'schemaVersion': 1, 'kind': 'compute-program-host-observation',
            'monotonicNs': time.monotonic_ns(), 'unixTimeNs': time.time_ns(),
            'cpuAffinity': sorted(os.sched_getaffinity(0)),
            'scope': 'cohort-boundary-shared-host', 'sources': sources}
