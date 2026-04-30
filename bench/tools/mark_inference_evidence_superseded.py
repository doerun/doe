#!/usr/bin/env python3
"""Stamp an inference-evidence supersession sidecar next to a receipt.

Use when a bounded-inference-smoke receipt's bound HostPlan + per-kernel
summary fail the inference evidence gate. The original receipt stays in tree
unchanged so its hash spine remains intact and so it can serve as a negative
fixture; the sidecar records gate rejection reasons and notes that the
receipt's content remains valid as compile-target front-door evidence only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._inference_evidence_gate import (  # noqa: E402
    evaluate_inference_evidence_gate,
)

ARTIFACT_KIND = "doe_inference_evidence_supersession"
SCHEMA_VERSION = 1
SIDECAR_NAME = "inference-evidence-supersession.json"
SUPERSEDED_AS = "inference_evidence"
REMAINS_VALID_AS = "compile_target_front_door_evidence"

DEFAULT_RECEIPT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json"
)
DEFAULT_HOST_PLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/host-plan.json"
)
DEFAULT_PER_KERNEL_SUMMARY = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/summary.json"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {_rel(path)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--host-plan", type=Path, default=DEFAULT_HOST_PLAN)
    parser.add_argument(
        "--per-kernel-summary",
        type=Path,
        default=DEFAULT_PER_KERNEL_SUMMARY,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Sidecar output path; defaults to "
            f"<receipt-dir>/{SIDECAR_NAME}."
        ),
    )
    return parser.parse_args()


def build_supersession(
    *,
    receipt: Path,
    host_plan: Path,
    per_kernel_summary: Path,
) -> dict[str, Any]:
    _require_file(receipt, "receipt")
    _require_file(host_plan, "host-plan")
    _require_file(per_kernel_summary, "per-kernel summary")

    host_plan_data = json.loads(host_plan.read_text(encoding="utf-8"))
    per_kernel_data = json.loads(
        per_kernel_summary.read_text(encoding="utf-8")
    )
    result = evaluate_inference_evidence_gate(
        host_plan=host_plan_data,
        per_kernel_summary=per_kernel_data,
    )
    if result.eligible:
        raise RuntimeError(
            "inference evidence gate accepted the bound HostPlan and "
            "per-kernel summary; nothing to supersede."
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "artifactKind": ARTIFACT_KIND,
        "subjectReceiptPath": _rel(receipt),
        "subjectReceiptSha256": _sha256_file(receipt),
        "subjectHostPlanPath": _rel(host_plan),
        "subjectHostPlanSha256": _sha256_file(host_plan),
        "subjectPerKernelSummaryPath": _rel(per_kernel_summary),
        "subjectPerKernelSummarySha256": _sha256_file(per_kernel_summary),
        "supersededAs": SUPERSEDED_AS,
        "remainsValidAs": REMAINS_VALID_AS,
        "rejectionReasons": [reason.to_dict() for reason in result.reasons],
    }


def main() -> int:
    args = parse_args()
    try:
        payload = build_supersession(
            receipt=args.receipt,
            host_plan=args.host_plan,
            per_kernel_summary=args.per_kernel_summary,
        )
    except (FileNotFoundError, RuntimeError) as err:
        sys.stderr.write(f"mark_inference_evidence_superseded: {err}\n")
        return 2
    sidecar = args.out if args.out is not None else (
        args.receipt.parent / SIDECAR_NAME
    )
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {_rel(sidecar)} reasons={len(payload['rejectionReasons'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
