#!/usr/bin/env python3
"""Fingerprint guard for the Cluster B 3 1B HostPlan fixture pair.

Mitigates "Cluster B fixture regen drift" from
docs/cerebras-north-star.md (Local risk mitigations). The two fixture
files

  bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/host-plan.json
  bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/doppler-program-bundle.json

are derived from upstream Doppler regen workflows. When upstream
changes drift the fixture without a corresponding regen on the Doe
side, parity gates that consume these files silently bind to stale
references. This guard pins their sha256 in a baseline file and refuses
silent drift.

Two operating modes mirror `bench/tools/prepack_hash_drift_guard.py`:

  * --update-baseline:
      Recompute current hashes and write them to
      `bench/fingerprints/cluster-b-fingerprints.json`. Exits 0.

  * Default (baseline present):
      Recompute current hashes, compare to baseline. Exit 0 when both
      files match the baseline. Exit 1 with a structured report when
      either file's sha256 differs, a baseline path is absent on disk,
      or a new fixture path is added without a baseline entry.

Intended to run as a nightly check (cron or scheduled CI). The guard
prints a JSON report on stdout so reviewers can pipe it into the
nightly run dashboard.

Usage:
  python3 bench/tools/cluster_b_fixture_drift_guard.py
  python3 bench/tools/cluster_b_fixture_drift_guard.py --update-baseline
  python3 bench/tools/cluster_b_fixture_drift_guard.py \\
      --baseline bench/fingerprints/cluster-b-fingerprints.json \\
      --report bench/out/cluster-b-drift-report.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = (
    REPO_ROOT / "bench" / "fingerprints" / "cluster-b-fingerprints.json"
)

CLUSTER_B_FIXTURE_PATHS: tuple[str, ...] = (
    "bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/host-plan.json",
    "bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/doppler-program-bundle.json",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to the fingerprint baseline JSON file.",
    )
    p.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current hashes to --baseline and exit 0.",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to write the drift-report JSON in addition to stdout.",
    )
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_current(
    paths: tuple[str, ...] = CLUSTER_B_FIXTURE_PATHS,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Hash the current Cluster B fixtures and return a baseline-shaped dict."""
    entries: dict[str, str] = {}
    missing: list[str] = []
    for rel in paths:
        absolute = repo_root / rel
        if not absolute.is_file():
            missing.append(rel)
            continue
        entries[rel] = _sha256_file(absolute)
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_cluster_b_fixture_fingerprints",
        "computedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "paths": entries,
        "missing": missing,
    }


def _baseline_paths(baseline: dict[str, Any]) -> dict[str, str]:
    paths = baseline.get("paths") or {}
    if not isinstance(paths, dict):
        return {}
    return {str(k): str(v) for k, v in paths.items()}


def compare(
    baseline: dict[str, Any],
    observed: dict[str, Any],
) -> dict[str, Any]:
    """Compare a baseline + an observed fingerprint dict; return a report."""
    baseline_paths = _baseline_paths(baseline)
    observed_paths = _baseline_paths(observed)

    drifted: list[dict[str, str]] = []
    new_paths: list[str] = []
    removed_paths: list[str] = []

    for path, observed_sha in observed_paths.items():
        if path not in baseline_paths:
            new_paths.append(path)
            continue
        if baseline_paths[path] != observed_sha:
            drifted.append(
                {
                    "path": path,
                    "baselineSha256": baseline_paths[path],
                    "observedSha256": observed_sha,
                }
            )
    for path in baseline_paths:
        if path not in observed_paths:
            removed_paths.append(path)

    missing = list(observed.get("missing") or [])

    bound = (
        not drifted
        and not new_paths
        and not removed_paths
        and not missing
    )
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_cluster_b_fixture_drift_report",
        "evaluatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "baselineComputedAt": baseline.get("computedAt"),
        "baselinePathCount": len(baseline_paths),
        "observedPathCount": len(observed_paths),
        "drifted": drifted,
        "newPaths": new_paths,
        "removedPaths": removed_paths,
        "missing": missing,
        "bound": bound,
        "verdict": "bound" if bound else "drift_detected",
    }


def main() -> int:
    args = parse_args()
    baseline_path = args.baseline.resolve()
    observed = fingerprint_current()

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sys.stdout.write(
            json.dumps(observed, indent=2, sort_keys=True) + "\n"
        )
        return 0

    if not baseline_path.is_file():
        sys.stderr.write(
            "cluster_b_fixture_drift_guard: baseline absent at "
            f"{baseline_path}; run with --update-baseline first.\n"
        )
        return 2

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    report = compare(baseline, observed)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    sys.stdout.write(text)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    return 0 if report["bound"] else 1


if __name__ == "__main__":
    sys.exit(main())
