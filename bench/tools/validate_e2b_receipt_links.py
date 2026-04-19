#!/usr/bin/env python3
"""Receipt link-integrity check for the E2B model runtime receipt.

Reads bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json and walks
every (path, sha256) pair recorded in it. For each link, asserts:

  - the path resolves to a file on disk
  - the on-disk sha256 matches the sha256 the receipt recorded

Reports per-link status (PASS / FAIL with reason). Exits 0 only if every
link resolves with matching sha. The parity-contract gate can call this
independently of any regen — it doesn't run the kernel, doesn't re-sha
the live source, and doesn't depend on cs_python; it just confirms the
receipt's machine-readable evidence is internally consistent.

Link locations walked:
  artifactHashes.<key>.{path, sha256}                      (6+ entries)
  streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence:
      kernelSourcePath          + kernelSourceSha256
      referenceDoc.path         + referenceDoc.sha256
      syntheticTrace.path       + syntheticTrace.sha256
      crossRuntimeParityCheck.path + ...sha256
      tracePath                 + traceSha256              (if present)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--receipt",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    return p.parse_args()


def collect_links(receipt: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return [(label, path, recorded_sha)] for every (path, sha) pair
    in the receipt. Skips entries where either field is missing — those
    are useful but not link-checkable here."""
    links: list[tuple[str, str, str]] = []

    # artifactHashes block: {executionManifest, hostPlan, ...}
    for key, val in (receipt.get("artifactHashes") or {}).items():
        path = (val or {}).get("path")
        sha = (val or {}).get("sha256")
        if path and sha:
            links.append((f"artifactHashes.{key}", path, sha))

    # layerBlockKernelEvidence sub-block.
    lbk = (
        receipt.get("streamingExecutorPrimitivesEvidence", {})
        .get("layerBlockKernelEvidence", {})
    )

    # kernelSource: top-level path + sha
    ks_path = lbk.get("kernelSourcePath")
    ks_sha = lbk.get("kernelSourceSha256")
    if ks_path and ks_sha:
        links.append(("layerBlockKernelEvidence.kernelSource", ks_path, ks_sha))

    # tracePath + traceSha256 (when the runner actually ran)
    t_path = lbk.get("tracePath")
    t_sha = lbk.get("traceSha256")
    if t_path and t_sha:
        links.append(("layerBlockKernelEvidence.runnerTrace", t_path, t_sha))

    # Sub-blocks that follow the same {path, exists, sha256} shape.
    for sub_key in ("referenceDoc", "syntheticTrace", "crossRuntimeParityCheck"):
        sub = lbk.get(sub_key) or {}
        path = sub.get("path")
        sha = sub.get("sha256")
        if path and sha:
            links.append(
                (f"layerBlockKernelEvidence.{sub_key}", path, sha)
            )

    return links


def main() -> int:
    args = parse_args()
    receipt_path = resolve(args.receipt)
    if not receipt_path.is_file():
        print(f"ERROR: receipt not found at {receipt_path}", file=sys.stderr)
        return 2
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    print(f"E2B receipt link-integrity check")
    print(f"  receipt: {receipt_path.relative_to(REPO_ROOT)}")
    print()

    links = collect_links(receipt)
    if not links:
        print("FAIL — receipt has no (path, sha256) pairs to check")
        return 1

    failures: list[str] = []
    print(f"  walking {len(links)} link(s):")
    for label, path_str, recorded_sha in links:
        abs_path = resolve(path_str)
        if not abs_path.is_file():
            failures.append(f"{label}: path missing  ({path_str})")
            print(f"    FAIL  {label:60} (path missing)")
            continue
        actual_sha = sha256_file(abs_path)
        if actual_sha != recorded_sha:
            failures.append(
                f"{label}: sha mismatch  recorded={recorded_sha[:16]}... "
                f"actual={actual_sha[:16]}..."
            )
            print(
                f"    FAIL  {label:60}  "
                f"sha {recorded_sha[:16]} != {actual_sha[:16]}"
            )
            continue
        print(f"    PASS  {label:60}  {recorded_sha[:16]}...")

    print()
    if failures:
        print(f"FAIL — {len(failures)} link(s) inconsistent:")
        for f in failures:
            print(f"  {f}")
        return 1

    print(f"PASS — every link resolves with matching sha ({len(links)}/{len(links)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
