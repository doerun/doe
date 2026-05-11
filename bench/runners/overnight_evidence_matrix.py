#!/usr/bin/env python3
"""Bounded-concurrency orchestrator for overnight evidence sweeps.

Runs a parameterizable matrix of cells (each cell = one subprocess invocation)
under per-lane concurrency caps. Designed for the kind of overnight 31B
evidence sweep described in `docs/cerebras-model-ledgers.md` R2-5a + R3-1, but
the matrix shape stays generic so this orchestrator outlives any single sweep.

Lanes:
  - webgpu_heavy  (default cap 1: WebGPU jobs are unified-memory bound)
  - csl_heavy     (default cap 2: simfabric jobs CPU-saturating)
  - light         (default cap 8: compile/preflight/gate/hash jobs)

Failure isolation: each cell is its own subprocess; an exit-non-zero or
exception inside one cell never propagates to siblings or the dispatcher.
The orchestrator's own exit code is 0 only if every cell either succeeded
or was skipped on resume.

Resume: re-invoke with `--resume <batch-dir>`. Cells whose `done.json`
records `exitCode=0` (and whose declared `expectSuccessReceiptPath` resolves)
are skipped; all others re-run from scratch in fresh subprocesses.

Matrix file format (JSON):
  {
    "cells": [
      {
        "id": "31b-l1-decode0-size1024",
        "lane": "csl_heavy",
        "cmd": ["cs_python", "bench/runners/.../runner.py", "--num-layers=1", ...],
        "cwd": "/home/x/deco/doe",                  # optional
        "env": {"DOE_FOO": "bar"},                 # optional
        "dependsOn": ["producer-cell"],            # optional, same-lane/order gate
        "timeoutSeconds": 7200,                    # optional, per-cell
        "expectSuccessReceiptPath": "bench/out/...", # optional gate file
        "expectJson": [                            # optional receipt checks
          {"path": "status", "equals": "output_ready"}
        ]
      },
      ...
    ]
  }
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LANES = ("webgpu_heavy", "csl_heavy", "light")
SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--matrix", required=True, help="Cell matrix JSON path.")
    p.add_argument(
        "--out",
        default="",
        help="Batch output directory. Defaults to bench/out/overnight/<utc>.",
    )
    p.add_argument("--max-webgpu-heavy", type=int, default=1)
    p.add_argument("--max-csl-heavy", type=int, default=2)
    p.add_argument("--max-light", type=int, default=8)
    p.add_argument(
        "--resume",
        default="",
        help="Resume an existing batch directory; skip cells already succeeded.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List the cells that would run and exit 0 without executing.",
    )
    return p.parse_args()


def now_utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_matrix(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cells = data.get("cells")
    if not isinstance(cells, list):
        raise ValueError(f"matrix at {path} has no 'cells' list")
    return cells


def cell_dir(batch_dir: Path, cell_id: str) -> Path:
    return batch_dir / "cells" / cell_id


def read_done_payload(batch_dir: Path, cell_id: str) -> dict[str, Any] | None:
    done_path = cell_dir(batch_dir, cell_id) / "done.json"
    if not done_path.is_file():
        return None
    try:
        payload = json.loads(done_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def path_value(payload: Any, path_spec: Any) -> Any:
    if isinstance(path_spec, str):
        parts = [part for part in path_spec.split(".") if part]
    elif isinstance(path_spec, list):
        parts = [str(part) for part in path_spec]
    else:
        raise ValueError("expectJson.path must be a dot path string or list")
    current = payload
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(part)
        current = current[part]
    return current


def receipt_expectations(cell: dict[str, Any], result: dict[str, Any]) -> list[str]:
    expect_path = cell.get("expectSuccessReceiptPath")
    checks = cell.get("expectJson") or []
    if not checks:
        return []
    if not expect_path:
        return ["expectJson requires expectSuccessReceiptPath"]
    try:
        payload = json.loads(Path(expect_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"could not read JSON receipt {expect_path}: {exc}"]

    failures: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            failures.append(f"invalid expectJson check: {check!r}")
            continue
        if "equals" not in check:
            failures.append(f"expectJson check lacks equals: {check!r}")
            continue
        try:
            actual = path_value(payload, check.get("path"))
        except (KeyError, ValueError) as exc:
            failures.append(f"{check.get('path')}: missing ({exc})")
            continue
        expected = check["equals"]
        if actual != expected:
            failures.append(f"{check.get('path')}: expected {expected!r}, got {actual!r}")
    if failures:
        result["expectedJsonFailures"] = failures
    return failures


def already_succeeded(cell: dict[str, Any], batch_dir: Path) -> bool:
    payload = read_done_payload(batch_dir, cell["id"])
    if payload is None:
        return False
    if payload.get("exitCode") != 0 or payload.get("status") != "succeeded":
        return False
    expect = cell.get("expectSuccessReceiptPath")
    if expect and not Path(expect).is_file():
        return False
    if expect and receipt_expectations(cell, {}) != []:
        return False
    return True


def run_cell(cell: dict[str, Any], batch_dir: Path) -> dict[str, Any]:
    """Run one cell as an isolated subprocess. Never raises."""
    started = time.time()
    cd = cell_dir(batch_dir, cell["id"])
    cd.mkdir(parents=True, exist_ok=True)
    stdout_path = cd / "stdout.log"
    stderr_path = cd / "stderr.log"
    done_path = cd / "done.json"

    cmd = list(cell.get("cmd") or [])
    env = os.environ.copy()
    extra_env = cell.get("env") or {}
    if isinstance(extra_env, dict):
        env.update({str(k): str(v) for k, v in extra_env.items()})
    cwd = cell.get("cwd")
    cwd_path = str(cwd) if isinstance(cwd, str) and cwd else None
    timeout = cell.get("timeoutSeconds")

    result: dict[str, Any] = {
        "cellId": cell["id"],
        "lane": cell["lane"],
        "cmd": cmd,
        "startedAtUnix": started,
    }
    dependencies = cell.get("dependsOn") or []
    if isinstance(dependencies, list) and dependencies:
        unmet: list[str] = []
        for dep in dependencies:
            dep_id = str(dep)
            dep_done = read_done_payload(batch_dir, dep_id)
            if dep_done is None:
                unmet.append(f"{dep_id}:missing_done")
            elif dep_done.get("status") != "succeeded" or dep_done.get("exitCode") != 0:
                unmet.append(f"{dep_id}:{dep_done.get('status', 'unknown')}")
        if unmet:
            result["exitCode"] = None
            result["status"] = "blocked"
            result["blockedBy"] = unmet
            result["elapsedSeconds"] = time.time() - started
            result["completedAtUnix"] = time.time()
            result["stdoutPath"] = str(stdout_path)
            result["stderrPath"] = str(stderr_path)
            if cwd_path:
                result["cwd"] = cwd_path
            done_path.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return result

    try:
        with stdout_path.open("w", encoding="utf-8") as out_f, \
             stderr_path.open("w", encoding="utf-8") as err_f:
            proc = subprocess.run(
                cmd,
                stdout=out_f,
                stderr=err_f,
                env=env,
                cwd=cwd_path,
                timeout=timeout if isinstance(timeout, (int, float)) else None,
                check=False,
            )
        result["exitCode"] = int(proc.returncode)
        result["status"] = "succeeded" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        result["exitCode"] = None
        result["status"] = "timeout"
        result["timeoutSeconds"] = timeout
    except (OSError, ValueError) as exc:
        result["exitCode"] = None
        result["status"] = "exception"
        result["error"] = str(exc)

    result["elapsedSeconds"] = time.time() - started
    result["completedAtUnix"] = time.time()
    result["stdoutPath"] = str(stdout_path)
    result["stderrPath"] = str(stderr_path)
    if cwd_path:
        result["cwd"] = cwd_path

    expect = cell.get("expectSuccessReceiptPath")
    if expect:
        result["expectSuccessReceiptPath"] = expect
        result["expectedReceiptExists"] = Path(expect).is_file()
        # If the cell exited 0 but the declared receipt is missing, downgrade.
        if result["status"] == "succeeded" and not result["expectedReceiptExists"]:
            result["status"] = "missing_receipt"
        if result["status"] == "succeeded" and receipt_expectations(cell, result):
            result["status"] = "receipt_mismatch"

    done_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix)
    cells = load_matrix(matrix_path)

    if args.resume:
        batch_dir = Path(args.resume)
        if not batch_dir.is_dir():
            print(f"FAIL: --resume directory does not exist: {batch_dir}", file=sys.stderr)
            return 1
    elif args.out:
        batch_dir = Path(args.out)
    else:
        batch_dir = Path("bench/out/overnight") / now_utc_compact()
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot the matrix at the batch root so resume runs see the same input.
    snapshot_path = batch_dir / "matrix.json"
    if not snapshot_path.is_file():
        snapshot_path.write_text(
            json.dumps({"cells": cells}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    pending: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for cell in cells:
        for required in ("id", "lane", "cmd"):
            if required not in cell:
                print(f"FAIL: cell missing required field {required!r}: {cell}", file=sys.stderr)
                return 2
        if cell["lane"] not in LANES:
            print(
                f"FAIL: cell {cell['id']!r} has invalid lane "
                f"{cell['lane']!r}; must be one of {LANES}",
                file=sys.stderr,
            )
            return 2
        if already_succeeded(cell, batch_dir):
            skipped.append(cell)
        else:
            pending.append(cell)

    print(
        f"matrix: {len(cells)} cells; skipping {len(skipped)} already succeeded; "
        f"running {len(pending)}"
    )

    if args.dry_run:
        for cell in pending:
            print(f"  [{cell['lane']:>14}] {cell['id']}")
        return 0

    by_lane: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    for cell in pending:
        by_lane[cell["lane"]].append(cell)

    started_at = time.time()
    results: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, args.max_webgpu_heavy)
    ) as wg_pool, concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, args.max_csl_heavy)
    ) as cs_pool, concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, args.max_light)
    ) as light_pool:
        futures: list[concurrent.futures.Future] = []
        for cell in by_lane["webgpu_heavy"]:
            futures.append(wg_pool.submit(run_cell, cell, batch_dir))
        for cell in by_lane["csl_heavy"]:
            futures.append(cs_pool.submit(run_cell, cell, batch_dir))
        for cell in by_lane["light"]:
            futures.append(light_pool.submit(run_cell, cell, batch_dir))

        for fut in concurrent.futures.as_completed(futures):
            cell_result = fut.result()  # run_cell never raises
            results.append(cell_result)
            print(
                f"  [{cell_result['status']:>15}] {cell_result['cellId']} "
                f"({cell_result['elapsedSeconds']:.1f}s)"
            )

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    summary = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactKind": "overnight_evidence_matrix_summary",
        "batchDir": str(batch_dir),
        "matrixPath": str(matrix_path),
        "startedAtUnix": started_at,
        "completedAtUnix": time.time(),
        "elapsedSeconds": time.time() - started_at,
        "cellCount": len(cells),
        "skippedCellIds": [c["id"] for c in skipped],
        "byStatus": by_status,
        "results": results,
    }
    summary_path = batch_dir / "batch.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"\nbatch summary: {by_status}")
    print(f"  {summary_path}")

    failed = sum(
        by_status.get(s, 0)
        for s in ("failed", "timeout", "exception", "missing_receipt", "receipt_mismatch", "blocked")
    )
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
