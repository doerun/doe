#!/usr/bin/env python3
"""Build and validate TSIR manifest lowering entries.

The entry shape is the schema-backed object consumed by
`integrityExtensions.lowerings[]`. This helper is deliberately narrow:
it binds already-computed semantic, realization, emitter, and target
correctness digests into one fail-closed manifest entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "config" / "doe-tsir-manifest-lowering.schema.json"

HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
VALID_EXACTNESS_CLASSES = frozenset(
    {"bit_exact_solo", "algorithm_exact", "tolerance_bounded"}
)
VALID_ALGORITHM_EXACT_INVARIANTS = frozenset(
    {
        "reduction_order",
        "tree_shape",
        "accum_dtype",
        "associativity_grouping",
    }
)
VALID_REJECTION_REASONS = frozenset(
    {
        "tsir_subgroup_unlowerable",
        "tsir_pe_budget_exhausted",
        "tsir_collective_not_representable",
        "tsir_dependence_unanalyzable",
        "tsir_source_not_affine",
        "tsir_target_unfit",
    }
)


@dataclass(frozen=True)
class ManifestLoweringInputs:
    kernel_ref: str
    backend: str
    target_descriptor_correctness_hash: str
    frontend_version: str
    tsir_semantic_digest: str
    tsir_realization_digest: str
    emitter_digest: str
    compiler_version: str
    exactness_class: str
    algorithm_exact_invariants: tuple[str, ...] = ()
    tolerance_metric: str = ""
    tolerance_epsilon: int | float = 0
    rejection_reasons: tuple[str, ...] = ()


def _format_schema_path(error: jsonschema.ValidationError) -> str:
    if not error.path:
        return "<root>"
    return ".".join(str(part) for part in error.path)


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_digest(name: str, value: str) -> None:
    if not HEX_DIGEST_RE.fullmatch(value):
        raise ValueError(f"{name} must be 64 lowercase hex characters")


def _require_nonempty(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} must be non-empty")


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")


def _validate_enum_values(
    name: str, values: tuple[str, ...], allowed: frozenset[str]
) -> None:
    for value in values:
        if value not in allowed:
            raise ValueError(f"{name} contains unsupported value: {value}")


def _normalize_epsilon(value: int | float) -> int | float:
    if isinstance(value, bool):
        raise ValueError("tolerance_epsilon must be numeric")
    if not math.isfinite(value):
        raise ValueError("tolerance_epsilon must be finite")
    if isinstance(value, int):
        return value
    if value.is_integer():
        return int(value)
    return value


def build_exactness(
    exactness_class: str,
    algorithm_exact_invariants: tuple[str, ...] = (),
    tolerance_metric: str = "",
    tolerance_epsilon: int | float = 0,
) -> dict[str, Any]:
    if exactness_class not in VALID_EXACTNESS_CLASSES:
        raise ValueError(f"unsupported exactness class: {exactness_class}")
    _require_unique("algorithm_exact_invariants", algorithm_exact_invariants)
    _validate_enum_values(
        "algorithm_exact_invariants",
        algorithm_exact_invariants,
        VALID_ALGORITHM_EXACT_INVARIANTS,
    )
    normalized_epsilon = _normalize_epsilon(tolerance_epsilon)

    if exactness_class == "bit_exact_solo":
        if algorithm_exact_invariants:
            raise ValueError("bit_exact_solo cannot declare algorithm invariants")
        if tolerance_metric or normalized_epsilon != 0:
            raise ValueError("bit_exact_solo cannot declare tolerance fields")
    elif exactness_class == "algorithm_exact":
        if not algorithm_exact_invariants:
            raise ValueError("algorithm_exact requires at least one invariant")
        if tolerance_metric or normalized_epsilon != 0:
            raise ValueError("algorithm_exact cannot declare tolerance fields")
    else:
        if algorithm_exact_invariants:
            raise ValueError("tolerance_bounded cannot declare algorithm invariants")
        if not tolerance_metric:
            raise ValueError("tolerance_bounded requires tolerance_metric")
        if normalized_epsilon <= 0:
            raise ValueError("tolerance_bounded requires positive tolerance_epsilon")

    return {
        "algorithmExactInvariants": list(algorithm_exact_invariants),
        "class": exactness_class,
        "toleranceEpsilon": normalized_epsilon,
        "toleranceMetric": tolerance_metric,
    }


def validate_entry_doc(doc: dict[str, Any]) -> None:
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        path = _format_schema_path(first)
        raise ValueError(
            f"TSIR manifest lowering schema validation failed at "
            f"{path}: {first.message}"
        )


def build_manifest_lowering_entry(
    inputs: ManifestLoweringInputs,
) -> dict[str, Any]:
    _require_nonempty("kernel_ref", inputs.kernel_ref)
    _require_nonempty("backend", inputs.backend)
    _require_nonempty("compiler_version", inputs.compiler_version)
    _validate_digest(
        "target_descriptor_correctness_hash",
        inputs.target_descriptor_correctness_hash,
    )
    _validate_digest("tsir_semantic_digest", inputs.tsir_semantic_digest)
    _validate_digest("tsir_realization_digest", inputs.tsir_realization_digest)
    _validate_digest("emitter_digest", inputs.emitter_digest)
    _require_unique("rejection_reasons", inputs.rejection_reasons)
    _validate_enum_values(
        "rejection_reasons",
        inputs.rejection_reasons,
        VALID_REJECTION_REASONS,
    )

    entry = {
        "backend": inputs.backend,
        "compilerVersion": inputs.compiler_version,
        "emitterDigest": inputs.emitter_digest,
        "exactness": build_exactness(
            inputs.exactness_class,
            inputs.algorithm_exact_invariants,
            inputs.tolerance_metric,
            inputs.tolerance_epsilon,
        ),
        "frontendVersion": inputs.frontend_version,
        "kernelRef": inputs.kernel_ref,
        "rejectionReasons": list(inputs.rejection_reasons),
        "targetDescriptorCorrectnessHash": (
            inputs.target_descriptor_correctness_hash
        ),
        "tsirRealizationDigest": inputs.tsir_realization_digest,
        "tsirSemanticDigest": inputs.tsir_semantic_digest,
    }
    validate_entry_doc(entry)
    return entry


def canonical_entry_bytes(doc: dict[str, Any]) -> bytes:
    validate_entry_doc(doc)
    return json.dumps(
        doc,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def manifest_lowering_entry_digest(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_entry_bytes(doc)).hexdigest()


def load_entry_doc(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"manifest lowering entry must be a JSON object: {path}")
    validate_entry_doc(doc)
    return doc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-entry",
        type=Path,
        help="Validate an existing manifest lowering entry JSON file.",
    )
    parser.add_argument("--kernel-ref", help="Source-program kernel reference.")
    parser.add_argument("--backend", help="Lowering backend tag.")
    parser.add_argument(
        "--target-descriptor-correctness-hash",
        help="64-char target correctness descriptor digest.",
    )
    parser.add_argument("--frontend-version", default="", help="TSIR frontend pin.")
    parser.add_argument(
        "--tsir-semantic-digest",
        help="64-char TSIR semantic digest.",
    )
    parser.add_argument(
        "--tsir-realization-digest",
        help="64-char TSIR realization digest.",
    )
    parser.add_argument("--emitter-digest", help="64-char emitter digest.")
    parser.add_argument("--compiler-version", help="Doe compiler version.")
    parser.add_argument(
        "--exactness-class",
        choices=sorted(VALID_EXACTNESS_CLASSES),
        help="Exactness class for the lowered entry.",
    )
    parser.add_argument(
        "--algorithm-exact-invariant",
        action="append",
        default=[],
        choices=sorted(VALID_ALGORITHM_EXACT_INVARIANTS),
        help="Invariant required by an algorithm_exact lowering.",
    )
    parser.add_argument(
        "--tolerance-metric",
        default="",
        help="Metric name for tolerance_bounded lowerings.",
    )
    parser.add_argument(
        "--tolerance-epsilon",
        default=0.0,
        type=float,
        help="Positive epsilon for tolerance_bounded lowerings.",
    )
    parser.add_argument(
        "--rejection-reason",
        action="append",
        default=[],
        choices=sorted(VALID_REJECTION_REASONS),
        help="Backend refusal reason to bind into the entry.",
    )
    parser.add_argument("--output", type=Path, help="Write entry JSON to this path.")
    parser.add_argument(
        "--print-digest",
        action="store_true",
        help="Print manifestLoweringEntryDigest to stderr.",
    )
    return parser.parse_args()


def _require_build_args(args: argparse.Namespace) -> None:
    required = [
        "kernel_ref",
        "backend",
        "target_descriptor_correctness_hash",
        "tsir_semantic_digest",
        "tsir_realization_digest",
        "emitter_digest",
        "compiler_version",
        "exactness_class",
    ]
    missing = [name for name in required if getattr(args, name) in (None, "")]
    if missing:
        joined = ", ".join("--" + name.replace("_", "-") for name in missing)
        raise ValueError(f"missing required build arguments: {joined}")


def _entry_from_args(args: argparse.Namespace) -> dict[str, Any]:
    _require_build_args(args)
    inputs = ManifestLoweringInputs(
        kernel_ref=args.kernel_ref,
        backend=args.backend,
        target_descriptor_correctness_hash=(
            args.target_descriptor_correctness_hash
        ),
        frontend_version=args.frontend_version,
        tsir_semantic_digest=args.tsir_semantic_digest,
        tsir_realization_digest=args.tsir_realization_digest,
        emitter_digest=args.emitter_digest,
        compiler_version=args.compiler_version,
        exactness_class=args.exactness_class,
        algorithm_exact_invariants=tuple(args.algorithm_exact_invariant),
        tolerance_metric=args.tolerance_metric,
        tolerance_epsilon=args.tolerance_epsilon,
        rejection_reasons=tuple(args.rejection_reason),
    )
    return build_manifest_lowering_entry(inputs)


def _write_entry(doc: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(payload, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def main() -> int:
    try:
        args = parse_args()
        if args.validate_entry is not None:
            entry = load_entry_doc(args.validate_entry)
        else:
            entry = _entry_from_args(args)
            _write_entry(entry, args.output)

        if args.print_digest:
            digest = manifest_lowering_entry_digest(entry)
            print(f"manifestLoweringEntryDigest={digest}", file=sys.stderr)
        return 0
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
