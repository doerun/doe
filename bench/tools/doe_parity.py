#!/usr/bin/env python3
"""Doe parity harness — manual CLI gate.

Runs a three-way comparison for one kernel:

  1. Reference interpreter (TSIR oracle) — ground truth.
  2. WebGPU emission path (Doe compute).
  3. CSL emission on simfabric (Doe simulator).

Emits `parity.json` receipts under `doe/reports/parity/`. Fails closed
on unrecognized exactness class — new classes require explicit harness
support, never silent tolerance.

Not a CI tool. Runs on demand after every kernel rewrite and before
any promotion.

Exactness classes (match RDRR taxonomy verbatim):

  * `bit_exact_solo`       — hex-identical bytes vs reference.
  * `algorithm_exact`      — hex-identical under declared reduction
                             tree; harness runs reference twice, once
                             in source order and once in declared tree
                             order, both must match the backend.
  * `tolerance_bounded`    — declared metric within declared epsilon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECEIPT_DIR = REPO_ROOT / "reports" / "parity"
SCHEMA_PATH = REPO_ROOT / "config" / "doe-parity-receipt.schema.json"

VALID_EXACTNESS = frozenset({"bit_exact_solo", "algorithm_exact", "tolerance_bounded"})

REJECTION_REASONS = frozenset(
    {
        "tsir_subgroup_unlowerable",
        "tsir_pe_budget_exhausted",
        "tsir_collective_not_representable",
        "tsir_dependence_unanalyzable",
        "tsir_source_not_affine",
        "tsir_target_unfit",
    }
)


@dataclass
class ComparisonOutcome:
    backend: str
    status: str
    backend_hash: str | None = None
    detail: str | None = None


@dataclass
class ParityReceipt:
    schema_version: int
    artifact_kind: str
    kernel: str
    exactness_class: str
    reference_hash: str | None
    inputs_digest: str
    comparisons: list[ComparisonOutcome] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "artifactKind": self.artifact_kind,
            "kernel": self.kernel,
            "exactnessClass": self.exactness_class,
            "referenceHash": self.reference_hash,
            "inputsDigest": self.inputs_digest,
            "comparisons": [
                {
                    "backend": c.backend,
                    "status": c.status,
                    "backendHash": c.backend_hash,
                    "detail": c.detail,
                }
                for c in self.comparisons
            ],
            "rejectionReasons": self.rejection_reasons,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", help="Kernel name, e.g. `rmsnorm`.")
    parser.add_argument(
        "--class",
        dest="exactness",
        required=True,
        choices=sorted(VALID_EXACTNESS),
        help="Declared exactness class for this kernel.",
    )
    parser.add_argument(
        "--inputs",
        required=True,
        type=Path,
        help="Path to a directory or file holding the kernel inputs.",
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        default=DEFAULT_RECEIPT_DIR,
        help="Directory to write the parity receipt.",
    )
    parser.add_argument(
        "--semantic-tsir",
        type=Path,
        help="Optional TSIR semantic JSON. When present with --realization-tsir, "
        "declared rejections are surfaced in the parity receipt.",
    )
    parser.add_argument(
        "--realization-tsir",
        type=Path,
        help="Optional TSIR realization JSON. Must be paired with --semantic-tsir.",
    )
    return parser.parse_args()


def sha256_of_path(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.read_bytes())
        return h.hexdigest()
    if path.is_dir():
        for entry in sorted(path.rglob("*")):
            if not entry.is_file():
                continue
            h.update(entry.relative_to(path).as_posix().encode("utf-8"))
            h.update(b"\0")
            h.update(entry.read_bytes())
        return h.hexdigest()
    raise FileNotFoundError(f"inputs path not found: {path}")


def extract_rejection_reasons(
    semantic_doc: dict[str, Any], realization_doc: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    for doc in (semantic_doc, realization_doc):
        entries = doc.get("rejections") or []
        if not isinstance(entries, list):
            raise ValueError("TSIR rejections must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("TSIR rejection entry must be an object")
            reason = entry.get("reason")
            if reason not in REJECTION_REASONS:
                raise ValueError(f"unrecognized TSIR rejection reason: {reason}")
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def load_rejection_reasons(
    semantic_path: Path | None, realization_path: Path | None
) -> list[str]:
    if bool(semantic_path) != bool(realization_path):
        raise ValueError(
            "--semantic-tsir and --realization-tsir must be supplied together"
        )
    if semantic_path is None or realization_path is None:
        return []
    semantic_doc = json.loads(semantic_path.read_text(encoding="utf-8"))
    realization_doc = json.loads(realization_path.read_text(encoding="utf-8"))
    if not isinstance(semantic_doc, dict) or not isinstance(realization_doc, dict):
        raise ValueError("TSIR JSON must be top-level objects")
    return extract_rejection_reasons(semantic_doc, realization_doc)


def run_reference_interpreter(
    _kernel: str, _inputs_digest: str, rejection_reasons: list[str] | None = None
) -> ComparisonOutcome:
    """Invoke the TSIR reference interpreter.

    Scaffolding: the Zig reference interpreter currently returns
    `NotImplemented` for every kernel. The CLI mirrors that here so the
    fail-closed path is exercised end-to-end from day one.
    """
    if rejection_reasons:
        return ComparisonOutcome(
            backend="reference",
            status="rejected",
            detail="TSIR rejected before execution: " + ", ".join(rejection_reasons),
        )
    return ComparisonOutcome(
        backend="reference",
        status="not_implemented",
        detail="tsir.reference_interpreter returns NotImplemented; scaffolding only",
    )


def run_backend(backend: str) -> ComparisonOutcome:
    """Run a backend emission path and return its hash.

    Scaffolding: both backends (`webgpu`, `csl-simfabric`) are wired as
    subprocess calls in a future session. For now return
    `not_implemented` so the receipt reflects the actual state.
    """
    return ComparisonOutcome(
        backend=backend,
        status="not_implemented",
        detail=f"{backend} backend lane wiring not yet landed",
    )


def compare(
    reference: ComparisonOutcome,
    backend_outcome: ComparisonOutcome,
    exactness: str,
) -> ComparisonOutcome:
    if exactness not in VALID_EXACTNESS:
        raise ValueError(f"unrecognized exactness class: {exactness}")
    if reference.status == "rejected":
        return ComparisonOutcome(
            backend=backend_outcome.backend,
            status="rejected",
            detail=f"{backend_outcome.backend} blocked: reference={reference.status}",
        )
    if reference.status != "ok" or backend_outcome.status != "ok":
        detail = (
            f"{backend_outcome.backend} deferred: "
            f"reference={reference.status}, backend={backend_outcome.status}"
        )
        return ComparisonOutcome(
            backend=backend_outcome.backend, status="deferred", detail=detail
        )
    if exactness in {"bit_exact_solo", "algorithm_exact"}:
        if reference.backend_hash == backend_outcome.backend_hash:
            return ComparisonOutcome(
                backend=backend_outcome.backend,
                status="pass",
                backend_hash=backend_outcome.backend_hash,
            )
        return ComparisonOutcome(
            backend=backend_outcome.backend,
            status="fail",
            backend_hash=backend_outcome.backend_hash,
            detail="hash mismatch",
        )
    # tolerance_bounded: the real comparator lives in the kernel's
    # declared metric/epsilon pair; scaffolding refuses to pass here
    # without those fields, by design.
    return ComparisonOutcome(
        backend=backend_outcome.backend,
        status="fail",
        backend_hash=backend_outcome.backend_hash,
        detail="tolerance_bounded metric+epsilon not yet wired",
    )


def write_receipt(receipt: ParityReceipt, receipt_dir: Path) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    out_path = receipt_dir / f"{receipt.kernel}.parity.json"
    out_path.write_text(
        json.dumps(receipt.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    try:
        args = parse_args()
        if args.exactness not in VALID_EXACTNESS:
            # argparse.choices should prevent this, but the guard is
            # declared per the fail-closed contract on unknown classes.
            print(f"unrecognized exactness class: {args.exactness}", file=sys.stderr)
            return 1

        inputs_digest = sha256_of_path(args.inputs)
        rejection_reasons = load_rejection_reasons(
            args.semantic_tsir, args.realization_tsir
        )
        reference = run_reference_interpreter(
            args.kernel, inputs_digest, rejection_reasons
        )
        webgpu_result = run_backend("webgpu")
        csl_result = run_backend("csl-simfabric")

        comparisons = [
            compare(reference, webgpu_result, args.exactness),
            compare(reference, csl_result, args.exactness),
        ]

        receipt = ParityReceipt(
            schema_version=1,
            artifact_kind="doe_parity_receipt",
            kernel=args.kernel,
            exactness_class=args.exactness,
            reference_hash=reference.backend_hash,
            inputs_digest=inputs_digest,
            comparisons=[reference] + comparisons,
            rejection_reasons=rejection_reasons,
        )
        out_path = write_receipt(receipt, args.receipt_dir)
        try:
            display_path: Path | str = out_path.relative_to(REPO_ROOT)
        except ValueError:
            display_path = out_path
        print(f"PARITY RECEIPT: {display_path}")
        # Scaffolding never claims pass; return 1 so callers cannot mistake
        # "receipt produced" for "kernel is green."
        any_non_pass = any(c.status != "pass" for c in comparisons)
        return 1 if any_non_pass else 0
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
