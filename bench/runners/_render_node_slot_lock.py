"""Cooperative slot lock around `/dev/dri/renderD128`.

Mitigates "Heavy WebGPU and heavy CSL jobs contend for the same RADV
render node" from docs/cerebras-model-ledgers.md (Local risk mitigations).

Heavy CSL runs do not touch the render node, but Doe-WebGPU capture
runs and AMD Vulkan benchmarks do. When two heavy users overlap on the
same `/dev/dri/renderD128`, dispatch latencies become non-deterministic
and timing receipts fail apples-to-apples checks.

This module provides an `flock(2)`-based exclusive lock keyed on a
path under `bench/out/scratch/locks/render-node-D128.lock`. It is a
cooperative gate: callers must opt-in. Anything that does NOT take the
lock will still race; the lock is a coordination point for runners
that do.

Usage:

    from bench.runners._render_node_slot_lock import render_node_lock

    with render_node_lock(name="amd-vulkan-claim"):
        # heavy WebGPU / Vulkan work that touches /dev/dri/renderD128
        ...

    # explicit timeout (seconds) — raises TimeoutError on contention:
    with render_node_lock(name="csl-paint-flow", timeout=600):
        ...

The lock file is created (gitignored under bench/out/scratch/) but
does not record state — `flock` semantics handle ownership. Holding
the lock writes a small JSON beside it so a stuck holder can be
diagnosed (`pid`, `name`, `acquiredUtc`).
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_DIR = REPO_ROOT / "bench" / "out" / "scratch" / "locks"
RENDER_NODE_LOCK = LOCK_DIR / "render-node-D128.lock"
RENDER_NODE_HOLDER = LOCK_DIR / "render-node-D128.holder.json"
DEFAULT_POLL_INTERVAL_SECONDS = 0.5


@contextlib.contextmanager
def render_node_lock(
    *,
    name: str,
    timeout: float | None = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> Iterator[Path]:
    """Acquire an exclusive lock on the RADV render node slot.

    `name` is a short label for diagnostics (e.g. ``"csl-paint-flow"``).
    `timeout` of None blocks indefinitely; a numeric value raises
    ``TimeoutError`` after that many wall-clock seconds.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(RENDER_NODE_LOCK, os.O_CREAT | os.O_RDWR, 0o644)
    deadline = None if timeout is None else time.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                if deadline is not None and time.time() >= deadline:
                    raise TimeoutError(
                        f"render_node_lock: timed out after {timeout}s waiting "
                        f"for {RENDER_NODE_LOCK} (currently held; see "
                        f"{RENDER_NODE_HOLDER} for the holder)"
                    ) from exc
                time.sleep(poll_interval_seconds)

        holder = {
            "pid": os.getpid(),
            "name": name,
            "acquiredUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            RENDER_NODE_HOLDER.write_text(
                json.dumps(holder, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass

        try:
            yield RENDER_NODE_LOCK
        finally:
            try:
                RENDER_NODE_HOLDER.unlink(missing_ok=True)
            except OSError:
                pass
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
