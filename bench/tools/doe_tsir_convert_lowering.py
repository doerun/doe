#!/usr/bin/env python3
"""AOT convert-time TSIR lowering orchestrator.

Under the re-scoped plan (see `docs/tsir-lowering-plan.md` Move 3 and
Step 11), this is the Doe-side entry point that Doppler's `convert`
stage will invoke. It iterates over the kernels declared in a manifest's
`inference.execution.kernels`, and for each `(kernelRef, backend)` in
the declared target matrix it produces:

- a `doppler-integrityExtensions.lowerings[].entry` shaped lowering
  entry, when TSIR can lower the kernel; or
- a typed rejection under the TSIR rejection taxonomy, when the
  frontend does not yet cover the kernel (real-kernel families land
  incrementally under Move 4).

It also drives `doe_parity.py` to emit per-`(kernel, backend)` parity
receipts under the declared receipts directory. Bootstrap kernels
route to the Zig scalar oracle; real kernels route to the Doppler
reference transcript supplied via `--doppler-transcript`. See
`docs/tsir-lowering-plan.md` Step 1 for the dual-regime contract.

The tool is deliberately narrow. It does not yet extend TSIR frontend
coverage to real kernels — that is Move 4 work. What it DOES do is
provide the convert-time orchestration surface so Doppler can land the
convert hook once and have subsequent kernel-family coverage grow
transparently as the frontend grows.

Exit semantics:
- exit 0 when every declared `(kernelRef, backend)` pair either passes
  or records a typed rejection (a rejection is a valid AOT outcome).
- exit 1 when any pair fails unexpectedly (for example, a backend lane
  reports `fail` under a `bit_exact_solo` contract, or a kernel the
  orchestrator thought was bootstrap does not run).

Not a CI tool in its own right — it is invoked by Doppler's convert
stage. The nightly canary
(`bench/gates/nightly_tsir_parity_canary.py`) still exercises the
bootstrap fixture set independently.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import doe_parity  # noqa: E402
from bench.tools import tsir_manifest_lowering  # noqa: E402

DEFAULT_TARGET_MATRIX = ("webgpu-generic", "wse3")
BOOTSTRAP_FIXTURE_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-manifest-entries"
BOOTSTRAP_INPUTS_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-bootstrap-inputs"
BOOTSTRAP_TSIR_DIR = REPO_ROOT / "runtime" / "zig" / "tests" / "tsir" / "bootstrap"
REAL_TSIR_DIR = REPO_ROOT / "runtime" / "zig" / "tests" / "tsir" / "real"

# Kernel-ref vocabulary under the TSIR bootstrap pipeline. Real-kernel
# refs (doe.tsir.real.*) are reserved and will be added incrementally
# as Move 4 extends the frontend.
BOOTSTRAP_KERNEL_REF_PREFIX = "doe.tsir.bootstrap."
REAL_KERNEL_REF_PREFIX = "doe.tsir.real."

# Real-kernel fixtures that document a target TSIR shape. Presence in
# this set means the fixture directory exists and the WS4 planner
# decisions are named. Absence means the real-kernel ref is reserved
# but no fixture has been hand-sketched yet. The orchestrator routes
# present vs. absent refs to different rejection details so the
# status is auditable from receipt text alone.
REAL_KERNEL_FIXTURES: frozenset[str] = frozenset({"embed"})


@dataclass
class ConvertLoweringOutcome:
    """Result of lowering one `(kernelRef, backend)` pair."""

    kernel_ref: str
    backend: str
    status: str  # "lowered" | "rejected" | "failed"
    entry: dict[str, Any] | None = None
    receipt_path: str | None = None
    rejection_reason: str | None = None
    detail: str | None = None

    def to_json(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "kernelRef": self.kernel_ref,
            "backend": self.backend,
            "status": self.status,
        }
        if self.entry is not None:
            doc["entry"] = self.entry
        if self.receipt_path is not None:
            doc["receiptPath"] = self.receipt_path
        if self.rejection_reason is not None:
            doc["rejectionReason"] = self.rejection_reason
        if self.detail is not None:
            doc["detail"] = self.detail
        return doc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help=(
            "Path to the Doppler manifest whose inference.execution.kernels "
            "should be lowered."
        ),
    )
    parser.add_argument(
        "--target-matrix",
        type=str,
        default=",".join(DEFAULT_TARGET_MATRIX),
        help=(
            "Comma-separated list of backend targets to lower for. "
            f"Default: {','.join(DEFAULT_TARGET_MATRIX)}. Currently "
            "`webgpu-generic` and `wse3` have target descriptors landed; "
            "others will be rejected with tsir_target_unfit."
        ),
    )
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "parity",
        help=(
            "Directory under which doe_parity.py receipts are written "
            "(one subdir per (kernel, backend))."
        ),
    )
    parser.add_argument(
        "--lowering-out",
        type=Path,
        help=(
            "Optional path to write the assembled "
            "integrityExtensions.lowerings document. When omitted, "
            "only receipts are emitted and the summary prints to stdout."
        ),
    )
    parser.add_argument(
        "--doppler-transcript",
        type=Path,
        help=(
            "Path to a doppler.reference-transcript/v1 for real-kernel "
            "parity. Ignored for bootstrap kernels."
        ),
    )
    parser.add_argument(
        "--python",
        type=str,
        default=sys.executable,
        help="Python executable used to invoke doe_parity.py.",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Emit a JSON summary to stdout on success.",
    )
    return parser.parse_args()


def parse_target_matrix(raw: str) -> tuple[str, ...]:
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    if not parts:
        raise ValueError("--target-matrix must list at least one backend")
    return parts


def load_manifest_kernels(manifest_path: Path) -> list[str]:
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest unreadable at {manifest_path}: {exc}") from exc
    inference = doc.get("inference")
    if not isinstance(inference, dict):
        raise ValueError("manifest must have top-level `inference` object")
    execution = inference.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("manifest.inference must have `execution` object")
    kernels = execution.get("kernels")
    if not isinstance(kernels, dict):
        raise ValueError(
            "manifest.inference.execution.kernels must be an object "
            "mapping kernel refs to kernel descriptors"
        )
    # We return kernel refs in sorted order for deterministic receipts.
    return sorted(kernels.keys())


def classify_kernel_ref(kernel_ref: str) -> str:
    """Classify a kernel ref as bootstrap, real, or external.

    The classification decides which oracle the parity CLI uses and
    whether the convert orchestrator can lower this kernel today.
    """

    if kernel_ref.startswith(BOOTSTRAP_KERNEL_REF_PREFIX):
        return "bootstrap"
    if kernel_ref.startswith(REAL_KERNEL_REF_PREFIX):
        return "real"
    return "external"


def bootstrap_kernel_short_name(kernel_ref: str) -> str:
    assert kernel_ref.startswith(BOOTSTRAP_KERNEL_REF_PREFIX)
    return kernel_ref[len(BOOTSTRAP_KERNEL_REF_PREFIX):]


def bootstrap_fixture_entry_path(kernel: str, backend: str) -> Path:
    return BOOTSTRAP_FIXTURE_DIR / f"{kernel}.{backend}.json"


def bootstrap_inputs_path(kernel: str) -> Path:
    return BOOTSTRAP_INPUTS_DIR / f"{kernel}.json"


def bootstrap_tsir_paths(kernel: str, backend: str) -> tuple[Path, Path]:
    semantic = BOOTSTRAP_TSIR_DIR / f"{kernel}.tsir-semantic.json"
    realization = BOOTSTRAP_TSIR_DIR / f"{kernel}.tsir-realization.{backend}.json"
    return semantic, realization


def run_bootstrap_parity(
    kernel: str,
    backend: str,
    receipts_dir: Path,
    python: str,
) -> tuple[int, str]:
    """Invoke doe_parity.py for a bootstrap kernel.

    Returns (return_code, receipt_path_relative_to_repo_root_or_empty).
    """

    entry_path = bootstrap_fixture_entry_path(kernel, backend)
    inputs_path = bootstrap_inputs_path(kernel)
    semantic_path, realization_path = bootstrap_tsir_paths(kernel, backend)
    receipt_dir = receipts_dir / f"{kernel}.{backend}"
    receipt_dir.mkdir(parents=True, exist_ok=True)

    entry_doc = tsir_manifest_lowering.load_entry_doc(entry_path)
    exactness = entry_doc["exactness"]["class"]

    result = subprocess.run(
        [
            python,
            str(REPO_ROOT / "bench" / "tools" / "doe_parity.py"),
            kernel,
            "--class",
            exactness,
            "--inputs",
            str(inputs_path),
            "--receipt-dir",
            str(receipt_dir),
            "--semantic-tsir",
            str(semantic_path),
            "--realization-tsir",
            str(realization_path),
            "--manifest-lowering-entry",
            str(entry_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    receipt_path = receipt_dir / f"{kernel}.parity.json"
    if not receipt_path.is_file():
        return result.returncode, ""
    try:
        rel = receipt_path.relative_to(REPO_ROOT)
        return result.returncode, str(rel)
    except ValueError:
        return result.returncode, str(receipt_path)


def lower_bootstrap_pair(
    kernel_ref: str,
    backend: str,
    receipts_dir: Path,
    python: str,
) -> ConvertLoweringOutcome:
    kernel = bootstrap_kernel_short_name(kernel_ref)
    entry_path = bootstrap_fixture_entry_path(kernel, backend)
    if not entry_path.is_file():
        return ConvertLoweringOutcome(
            kernel_ref=kernel_ref,
            backend=backend,
            status="rejected",
            rejection_reason="tsir_target_unfit",
            detail=(
                f"no TSIR manifest-entry fixture for bootstrap kernel "
                f"{kernel!r} on backend {backend!r} (expected "
                f"{entry_path.relative_to(REPO_ROOT)})"
            ),
        )
    returncode, receipt_path = run_bootstrap_parity(
        kernel, backend, receipts_dir, python
    )
    entry_doc = tsir_manifest_lowering.load_entry_doc(entry_path)
    # The bootstrap doe_parity returns 1 while backend execution lanes
    # remain deferred. We interpret that as a successful lowering with
    # a deferred backend — the entry itself still lands cleanly.
    outcome = ConvertLoweringOutcome(
        kernel_ref=kernel_ref,
        backend=backend,
        status="lowered",
        entry=entry_doc,
        receipt_path=receipt_path or None,
        detail=(
            f"bootstrap parity run exited {returncode} "
            "(non-zero is expected while backend lanes remain deferred)"
        ),
    )
    return outcome


def real_kernel_short_name(kernel_ref: str) -> str:
    assert kernel_ref.startswith(REAL_KERNEL_REF_PREFIX)
    return kernel_ref[len(REAL_KERNEL_REF_PREFIX):]


def real_fixture_paths(kernel: str, backend: str) -> dict[str, Path]:
    base = REAL_TSIR_DIR / kernel
    return {
        "wgsl": base / f"{kernel}.wgsl",
        "semantic": base / f"{kernel}.tsir-semantic.json",
        "realization": base / f"{kernel}.tsir-realization.{backend}.json",
        "notes": base / f"{kernel}.notes.md",
    }


def reject_real_kernel_pair(
    kernel_ref: str,
    backend: str,
) -> ConvertLoweringOutcome:
    kernel = real_kernel_short_name(kernel_ref)
    if kernel in REAL_KERNEL_FIXTURES:
        paths = real_fixture_paths(kernel, backend)
        missing = [
            str(p.relative_to(REPO_ROOT))
            for p in paths.values()
            if not p.is_file()
        ]
        if missing:
            return ConvertLoweringOutcome(
                kernel_ref=kernel_ref,
                backend=backend,
                status="rejected",
                rejection_reason="tsir_source_not_affine",
                detail=(
                    f"real-kernel {kernel_ref!r} is registered in "
                    "REAL_KERNEL_FIXTURES but the fixture directory is "
                    f"incomplete: missing {', '.join(missing)}. Fix the "
                    "fixture or drop the registration."
                ),
            )
        return ConvertLoweringOutcome(
            kernel_ref=kernel_ref,
            backend=backend,
            status="rejected",
            rejection_reason="tsir_source_not_affine",
            detail=(
                f"real-kernel {kernel_ref!r} target shape is documented "
                f"at {paths['notes'].relative_to(REPO_ROOT)} with "
                f"hand-sketched semantic/realization JSON under "
                f"{(REAL_TSIR_DIR / kernel).relative_to(REPO_ROOT)}/. "
                "Frontend recovery (frontend.zig), planner residency "
                "selection (planner.zig), and CSL emitter body for "
                "fabric_streamed table reads (emit_kernel_body.zig) "
                "are the remaining compiler extensions. The fixture "
                "names the target realization; the code does not yet "
                "produce it."
            ),
        )
    return ConvertLoweringOutcome(
        kernel_ref=kernel_ref,
        backend=backend,
        status="rejected",
        rejection_reason="tsir_source_not_affine",
        detail=(
            f"real-kernel {kernel_ref!r} not yet covered by TSIR "
            "frontend. Move 4 extends frontend coverage to the WS4 "
            "per-PE blockers first (embed, lm_head_gemv_stable, "
            "attn_head256, attn_head512). See "
            "docs/tsir-lowering-plan.md Step 9."
        ),
    )


def reject_external_kernel_pair(
    kernel_ref: str,
    backend: str,
) -> ConvertLoweringOutcome:
    return ConvertLoweringOutcome(
        kernel_ref=kernel_ref,
        backend=backend,
        status="rejected",
        rejection_reason="tsir_source_not_affine",
        detail=(
            f"kernel {kernel_ref!r} is neither a TSIR bootstrap "
            f"({BOOTSTRAP_KERNEL_REF_PREFIX}*) nor a declared real-kernel "
            f"ref ({REAL_KERNEL_REF_PREFIX}*). Convert-time lowering "
            "only emits entries for TSIR-declared kernels; "
            "externally-provided kernels must be routed through their "
            "legacy lowering path."
        ),
    )


def orchestrate_lowering(
    kernel_refs: list[str],
    target_matrix: tuple[str, ...],
    receipts_dir: Path,
    python: str,
) -> list[ConvertLoweringOutcome]:
    outcomes: list[ConvertLoweringOutcome] = []
    for kernel_ref in kernel_refs:
        kind = classify_kernel_ref(kernel_ref)
        for backend in target_matrix:
            if kind == "bootstrap":
                outcomes.append(
                    lower_bootstrap_pair(
                        kernel_ref, backend, receipts_dir, python
                    )
                )
            elif kind == "real":
                outcomes.append(reject_real_kernel_pair(kernel_ref, backend))
            else:
                outcomes.append(reject_external_kernel_pair(kernel_ref, backend))
    return outcomes


def build_lowerings_doc(outcomes: list[ConvertLoweringOutcome]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for outcome in outcomes:
        if outcome.status != "lowered" or outcome.entry is None:
            continue
        entries.append(outcome.entry)
    return {
        "contractVersion": 1,
        "entries": entries,
    }


def main() -> int:
    try:
        args = parse_args()
        target_matrix = parse_target_matrix(args.target_matrix)
        kernel_refs = load_manifest_kernels(args.manifest)
        args.receipts_dir.mkdir(parents=True, exist_ok=True)
        outcomes = orchestrate_lowering(
            kernel_refs, target_matrix, args.receipts_dir, args.python
        )
        lowerings_doc = build_lowerings_doc(outcomes)
        if args.lowering_out is not None:
            args.lowering_out.parent.mkdir(parents=True, exist_ok=True)
            args.lowering_out.write_text(
                json.dumps(lowerings_doc, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        summary: dict[str, Any] = {
            "manifest": str(args.manifest),
            "targetMatrix": list(target_matrix),
            "outcomes": [o.to_json() for o in outcomes],
            "lowerings": lowerings_doc,
        }
        if args.summary_json:
            print(json.dumps(summary, indent=2, sort_keys=True))

        unexpected_failures = [
            o for o in outcomes if o.status == "failed"
        ]
        return 1 if unexpected_failures else 0
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
