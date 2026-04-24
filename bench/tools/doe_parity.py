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
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import tsir_manifest_lowering  # noqa: E402

DEFAULT_RECEIPT_DIR = REPO_ROOT / "reports" / "parity"
SCHEMA_PATH = REPO_ROOT / "config" / "doe-parity-receipt.schema.json"
ZIG_RUNTIME_DIR = REPO_ROOT / "runtime" / "zig"
ZIG_BOOTSTRAP_ORACLE_BIN = (
    ZIG_RUNTIME_DIR / "zig-out" / "bin" / "doe-tsir-bootstrap-oracle"
)

VALID_EXACTNESS = frozenset({"bit_exact_solo", "algorithm_exact", "tolerance_bounded"})
BOOTSTRAP_ORACLE_KERNELS = frozenset({"fused_gemv", "gather", "rms_norm"})
KERNEL_ALIASES = {
    "rmsnorm": "rms_norm",
    "rms-norm": "rms_norm",
    "fused-gemv": "fused_gemv",
}

# Reference-source taxonomy under the re-scope (see docs/tsir-lowering-plan.md
# Step 1 "Real-kernel regime" and Step 8 "Backend lane rules").
REFERENCE_SOURCE_ZIG = "zig-tsir-oracle"
REFERENCE_SOURCE_DOPPLER = "doppler-reference-transcript"
REFERENCE_TRANSCRIPT_SCHEMA_ID = "doppler.reference-transcript/v1"

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

_ZIG_BOOTSTRAP_ORACLE_READY = False


@dataclass
class ComparisonOutcome:
    backend: str
    status: str
    backend_hash: str | None = None
    detail: str | None = None


@dataclass
class ReferenceSource:
    """Names which oracle regime produced the reference hash.

    Bootstrap kernels route to the Zig scalar interpreter
    (`REFERENCE_SOURCE_ZIG`). Real kernels route to a Doppler
    `doppler.reference-transcript/v1` captured via `doppler bundle`
    (`REFERENCE_SOURCE_DOPPLER`). The taxonomy is load-bearing for
    audit: a receipt must name which oracle it was gated against.
    """

    kind: str
    execution_graph_hash: str | None = None
    source_hash: str | None = None
    transcript_path: str | None = None
    detail: str | None = None

    def to_json(self) -> dict[str, Any]:
        if self.kind == REFERENCE_SOURCE_ZIG:
            doc: dict[str, Any] = {"kind": REFERENCE_SOURCE_ZIG}
            if self.detail is not None:
                doc["detail"] = self.detail
            return doc
        if self.kind == REFERENCE_SOURCE_DOPPLER:
            if self.execution_graph_hash is None or self.source_hash is None:
                raise ValueError(
                    "doppler reference source requires executionGraphHash "
                    "and sourceHash."
                )
            doc = {
                "kind": REFERENCE_SOURCE_DOPPLER,
                "executionGraphHash": self.execution_graph_hash,
                "sourceHash": self.source_hash,
            }
            if self.transcript_path is not None:
                doc["transcriptPath"] = self.transcript_path
            if self.detail is not None:
                doc["detail"] = self.detail
            return doc
        raise ValueError(f"unknown reference source kind: {self.kind!r}")


class BootstrapOracleNotImplemented(RuntimeError):
    """Raised when the bootstrap oracle cannot honestly execute a case."""


class DopplerTranscriptInvalid(ValueError):
    """Raised when a supplied Doppler transcript fails validation."""


@dataclass(frozen=True)
class LoweringIdentity:
    tsir_semantic_digest: str
    tsir_realization_digest: str
    emitter_digest: str
    target_descriptor_correctness_hash: str

    def to_json(self) -> dict[str, str]:
        return {
            "emitterDigest": self.emitter_digest,
            "targetDescriptorCorrectnessHash": (
                self.target_descriptor_correctness_hash
            ),
            "tsirRealizationDigest": self.tsir_realization_digest,
            "tsirSemanticDigest": self.tsir_semantic_digest,
        }


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
    lowering_identity: LoweringIdentity | None = None
    reference_source: ReferenceSource | None = None

    def to_json(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
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
        if self.reference_source is not None:
            doc["referenceSource"] = self.reference_source.to_json()
        if self.lowering_identity is not None:
            doc["loweringIdentity"] = self.lowering_identity.to_json()
        return doc


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
    parser.add_argument(
        "--manifest-lowering-entry",
        type=Path,
        help="Optional integrityExtensions.lowerings[] fixture entry. Copies "
        "TSIR lowering identity digests into the receipt without changing "
        "stub execution status.",
    )
    parser.add_argument(
        "--doppler-transcript",
        type=Path,
        help=(
            "Path to a doppler.reference-transcript/v1 JSON captured via "
            "`doppler bundle`. Required for real (non-bootstrap) kernels "
            "under the re-scoped plan. Routes reference to the Doppler "
            "browser WebGPU run instead of the Zig scalar oracle."
        ),
    )
    parser.add_argument(
        "--doppler-kernel-probe-hash",
        type=str,
        help=(
            "Optional 64-char hex digest for a per-kernel probe captured "
            "alongside a Doppler reference transcript. When omitted, the "
            "reference lane records the transcript identity and marks "
            "comparison status as deferred pending per-kernel probe "
            "capture."
        ),
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


def canonical_kernel_name(kernel: str) -> str:
    prefix = "doe.tsir.bootstrap."
    if kernel.startswith(prefix):
        kernel = kernel.removeprefix(prefix)
    return KERNEL_ALIASES.get(kernel, kernel)


def _summarize_process_failure(result: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    if not text:
        return f"exit code {result.returncode}"
    lines = text.splitlines()
    return "\n".join(lines[-12:])


def _ensure_zig_bootstrap_oracle() -> None:
    global _ZIG_BOOTSTRAP_ORACLE_READY
    if _ZIG_BOOTSTRAP_ORACLE_READY and ZIG_BOOTSTRAP_ORACLE_BIN.exists():
        return
    try:
        result = subprocess.run(
            ["zig", "build", "tsir-bootstrap-oracle"],
            cwd=ZIG_RUNTIME_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise BootstrapOracleNotImplemented(
            f"zig bootstrap oracle build failed: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = _summarize_process_failure(result)
        raise BootstrapOracleNotImplemented(
            f"zig bootstrap oracle build failed: {detail}"
        )
    if not ZIG_BOOTSTRAP_ORACLE_BIN.exists():
        raise BootstrapOracleNotImplemented(
            f"zig bootstrap oracle binary missing: {ZIG_BOOTSTRAP_ORACLE_BIN}"
        )
    _ZIG_BOOTSTRAP_ORACLE_READY = True


def _run_zig_bootstrap_oracle(
    kernel: str,
    inputs_path: Path | None,
    semantic_path: Path | None,
    realization_path: Path | None,
) -> str:
    canonical_kernel = canonical_kernel_name(kernel)
    if canonical_kernel not in BOOTSTRAP_ORACLE_KERNELS:
        raise BootstrapOracleNotImplemented(
            f"bootstrap oracle does not support kernel: {kernel}"
        )
    if inputs_path is None:
        raise BootstrapOracleNotImplemented("no bootstrap oracle input path supplied")
    _ensure_zig_bootstrap_oracle()
    command = [
        str(ZIG_BOOTSTRAP_ORACLE_BIN),
        "--kernel",
        canonical_kernel,
        "--inputs",
        str(inputs_path),
    ]
    if semantic_path is not None:
        command.extend(["--semantic-tsir", str(semantic_path)])
    if realization_path is not None:
        command.extend(["--realization-tsir", str(realization_path)])
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise BootstrapOracleNotImplemented(
            f"zig bootstrap oracle execution failed: {exc}"
        ) from exc
    stdout = result.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError as exc:
        detail = _summarize_process_failure(result)
        raise BootstrapOracleNotImplemented(
            f"zig bootstrap oracle emitted invalid JSON: {detail}"
        ) from exc
    if not isinstance(payload, dict):
        raise BootstrapOracleNotImplemented(
            "zig bootstrap oracle emitted non-object JSON"
        )
    if result.returncode != 0:
        detail = payload.get("detail")
        if not isinstance(detail, str) or not detail:
            detail = _summarize_process_failure(result)
        raise BootstrapOracleNotImplemented(detail)
    if payload.get("status") != "pass":
        detail = payload.get("detail")
        if not isinstance(detail, str) or not detail:
            detail = f"zig bootstrap oracle status={payload.get('status')!r}"
        raise BootstrapOracleNotImplemented(detail)
    reference_hash = payload.get("referenceHash")
    if (
        not isinstance(reference_hash, str)
        or len(reference_hash) != 64
        or any(ch not in "0123456789abcdef" for ch in reference_hash)
    ):
        raise BootstrapOracleNotImplemented(
            "zig bootstrap oracle emitted invalid referenceHash"
        )
    return reference_hash


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


def lowering_identity_from_manifest_entry(
    entry_path: Path | None, exactness: str
) -> LoweringIdentity | None:
    if entry_path is None:
        return None
    entry = tsir_manifest_lowering.load_entry_doc(entry_path)
    entry_exactness = entry["exactness"]["class"]
    if entry_exactness != exactness:
        raise ValueError(
            "manifest lowering exactness class does not match CLI --class: "
            f"{entry_exactness} != {exactness}"
        )
    return LoweringIdentity(
        tsir_semantic_digest=entry["tsirSemanticDigest"],
        tsir_realization_digest=entry["tsirRealizationDigest"],
        emitter_digest=entry["emitterDigest"],
        target_descriptor_correctness_hash=(
            entry["targetDescriptorCorrectnessHash"]
        ),
    )


def load_doppler_transcript(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DopplerTranscriptInvalid(
            f"doppler transcript unreadable at {path}: {exc}"
        ) from exc
    if not isinstance(doc, dict):
        raise DopplerTranscriptInvalid(
            "doppler transcript must be a top-level JSON object"
        )
    if doc.get("schema") != REFERENCE_TRANSCRIPT_SCHEMA_ID:
        raise DopplerTranscriptInvalid(
            f"doppler transcript schema must be {REFERENCE_TRANSCRIPT_SCHEMA_ID!r}"
        )
    execution_graph_hash = doc.get("executionGraphHash")
    if not isinstance(execution_graph_hash, str) or not execution_graph_hash.startswith("sha256:"):
        raise DopplerTranscriptInvalid(
            "doppler transcript executionGraphHash must be a sha256: digest"
        )
    source = doc.get("source")
    if not isinstance(source, dict):
        raise DopplerTranscriptInvalid(
            "doppler transcript source must be an object"
        )
    source_hash = source.get("hash")
    if not isinstance(source_hash, str) or not source_hash.startswith("sha256:"):
        raise DopplerTranscriptInvalid(
            "doppler transcript source.hash must be a sha256: digest"
        )
    return doc


def run_doppler_reference(
    kernel: str,
    rejection_reasons: list[str] | None,
    transcript_path: Path,
    probe_hash: str | None,
) -> tuple[ComparisonOutcome, ReferenceSource]:
    """Use a Doppler reference transcript as the oracle for a real kernel.

    The transcript carries end-to-end model identity (tokens, per-step
    logits hashes, KV identity). Per-kernel probe hashes are a separate
    capture concern — the Doppler side must emit a probe that hashes
    the kernel's output under identical inputs. When a probe is not
    supplied, the reference lane records the transcript identity
    (executionGraphHash + source.hash) for audit and marks the
    comparison status `not_implemented` so the receipt does not imply
    coverage the harness does not have.
    """
    doc = load_doppler_transcript(transcript_path)
    reference_source = ReferenceSource(
        kind=REFERENCE_SOURCE_DOPPLER,
        execution_graph_hash=doc["executionGraphHash"],
        source_hash=doc["source"]["hash"],
        transcript_path=str(transcript_path),
    )
    if rejection_reasons:
        return (
            ComparisonOutcome(
                backend="reference",
                status="rejected",
                detail="TSIR rejected before execution: "
                + ", ".join(rejection_reasons),
            ),
            reference_source,
        )
    if probe_hash is None:
        reference_source.detail = (
            "transcript identity recorded; per-kernel probe not captured."
        )
        return (
            ComparisonOutcome(
                backend="reference",
                status="not_implemented",
                detail=(
                    f"doppler transcript reference for {kernel!r}: "
                    "per-kernel probe hash not supplied. Run with "
                    "--doppler-kernel-probe-hash once Doppler-side per-kernel "
                    "capture lands."
                ),
            ),
            reference_source,
        )
    if len(probe_hash) != 64 or any(
        ch not in "0123456789abcdef" for ch in probe_hash.lower()
    ):
        raise DopplerTranscriptInvalid(
            "--doppler-kernel-probe-hash must be a 64-char lowercase hex digest"
        )
    return (
        ComparisonOutcome(
            backend="reference",
            status="pass",
            backend_hash=probe_hash.lower(),
            detail="doppler reference transcript per-kernel probe",
        ),
        reference_source,
    )


def run_reference_interpreter(
    kernel: str,
    _inputs_digest: str,
    rejection_reasons: list[str] | None = None,
    inputs_path: Path | None = None,
    semantic_path: Path | None = None,
    realization_path: Path | None = None,
) -> ComparisonOutcome:
    """Invoke the TSIR reference interpreter.

    This is intentionally narrow: it only executes dedicated bootstrap
    oracle input artifacts for the Phase A `fused_gemv`, `rms_norm`, and
    `gather` families, and the actual reference execution happens in the
    Zig `doe-tsir-bootstrap-oracle` subprocess. Manifest fixtures,
    directories, generic TSIR JSON, and unrecognized shapes still return
    `not_implemented` so receipts do not imply coverage the harness does
    not have.
    """
    if rejection_reasons:
        return ComparisonOutcome(
            backend="reference",
            status="rejected",
            detail="TSIR rejected before execution: " + ", ".join(rejection_reasons),
        )
    try:
        reference_hash = _run_zig_bootstrap_oracle(
            kernel,
            inputs_path,
            semantic_path,
            realization_path,
        )
    except BootstrapOracleNotImplemented as exc:
        return ComparisonOutcome(
            backend="reference",
            status="not_implemented",
            detail=str(exc),
        )
    return ComparisonOutcome(
        backend="reference",
        status="pass",
        backend_hash=reference_hash,
        detail="zig bootstrap TSIR oracle executed",
    )


def run_backend(backend: str) -> ComparisonOutcome:
    """Run a backend emission path and return its hash.

    Scaffolding: both backend lanes are still execution-stub-only. The
    TSIR emitters now have semantic-aware bootstrap bodies, but this CLI
    still needs WebGPU execution and CSL simfabric driver wiring before it
    can compare backend bytes. Until those land, this returns
    `not_implemented` so the receipt reflects the actual state rather than
    an invented answer.
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
    reference_ready = reference.status in {"ok", "pass"}
    backend_ready = backend_outcome.status in {"ok", "pass"}
    if not reference_ready or not backend_ready:
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


def _format_schema_path(error: jsonschema.ValidationError) -> str:
    if not error.path:
        return "<root>"
    return ".".join(str(part) for part in error.path)


def validate_receipt_doc(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        path = _format_schema_path(first)
        raise ValueError(
            f"parity receipt schema validation failed at {path}: {first.message}"
        )


def write_receipt(receipt: ParityReceipt, receipt_dir: Path) -> Path:
    doc = receipt.to_json()
    validate_receipt_doc(doc)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    out_path = receipt_dir / f"{receipt.kernel}.parity.json"
    out_path.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n",
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
        lowering_identity = lowering_identity_from_manifest_entry(
            args.manifest_lowering_entry, args.exactness
        )

        normalized_kernel = KERNEL_ALIASES.get(args.kernel, args.kernel)
        is_bootstrap_kernel = normalized_kernel in BOOTSTRAP_ORACLE_KERNELS
        doppler_transcript = args.doppler_transcript

        if is_bootstrap_kernel and doppler_transcript is not None:
            raise ValueError(
                f"--doppler-transcript is not valid for bootstrap kernel "
                f"{normalized_kernel!r}; bootstrap kernels route to the Zig "
                "scalar oracle by design. See docs/tsir-lowering-plan.md "
                "Step 1."
            )
        if not is_bootstrap_kernel and doppler_transcript is None:
            raise ValueError(
                f"real kernel {normalized_kernel!r} requires "
                "--doppler-transcript under the re-scoped plan (real-kernel "
                "reference is Doppler's browser WebGPU transcript, not the "
                "Zig oracle). See docs/tsir-lowering-plan.md Step 1."
            )

        if doppler_transcript is not None:
            reference, reference_source = run_doppler_reference(
                normalized_kernel,
                rejection_reasons,
                doppler_transcript,
                args.doppler_kernel_probe_hash,
            )
        else:
            reference = run_reference_interpreter(
                normalized_kernel,
                inputs_digest,
                rejection_reasons,
                inputs_path=args.inputs,
                semantic_path=args.semantic_tsir,
                realization_path=args.realization_tsir,
            )
            reference_source = ReferenceSource(kind=REFERENCE_SOURCE_ZIG)

        webgpu_result = run_backend("webgpu")
        csl_result = run_backend("csl-simfabric")

        comparisons = [
            compare(reference, webgpu_result, args.exactness),
            compare(reference, csl_result, args.exactness),
        ]

        receipt = ParityReceipt(
            schema_version=2,
            artifact_kind="doe_parity_receipt",
            kernel=normalized_kernel,
            exactness_class=args.exactness,
            reference_hash=reference.backend_hash,
            inputs_digest=inputs_digest,
            comparisons=[reference] + comparisons,
            rejection_reasons=rejection_reasons,
            lowering_identity=lowering_identity,
            reference_source=reference_source,
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
