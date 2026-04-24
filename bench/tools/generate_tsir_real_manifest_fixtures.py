#!/usr/bin/env python3
"""Generate TSIR real-kernel manifest lowering fixture entries.

Real-kernel entries follow the same schema as bootstrap entries
(`doe-tsir-manifest-lowering.schema.json`) but are keyed under the
`doe.tsir.real.<kernel>` ref namespace and source their TSIR
semantic/realization digests from canonical serialization of the
hand-authored fixtures under `runtime/zig/tests/tsir/real/`.

The generator is fail-closed: any zero-sentinel digest raises before
writing an entry, so manifest rows never bind a sentinel identity.

Per-backend `emitterDigest` and `targetDescriptorCorrectnessHash` are
copied from the committed bootstrap fixtures so the two fixture sets
stay coherent — one backend → one emitter build → one target
descriptor, independent of kernel. The copy happens at generation
time; if bootstrap pins change and real fixtures are not regenerated,
the `--check` mode in CI will flag drift.
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

from bench.tools.tsir_manifest_lowering import (
    ManifestLoweringInputs,
    build_manifest_lowering_entry,
    manifest_lowering_entry_digest,
)


SENTINEL_DIGEST = "0" * 64
REAL_FIXTURES_DIR = REPO_ROOT / "runtime" / "zig" / "tests" / "tsir" / "real"
BOOTSTRAP_ENTRIES_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-manifest-entries"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-real-entries"

REAL_KERNEL_REF_PREFIX = "doe.tsir.real."
REAL_COMPILER_VERSION = "doe-tsir-real-2026-04-24"
SUPPORTED_BACKENDS: tuple[str, ...] = ("webgpu-generic", "wse3")

# Exactness policy per real kernel. Keyed to the body op and reduction
# contract in the TSIR semantic JSON — the registry is narrow so the
# generator does not grow a classifier.
#
# Tuple shape: (exactness_class, algorithm_exact_invariants,
#               tolerance_metric, tolerance_epsilon).
# The last two are only meaningful for `tolerance_bounded`; for
# `bit_exact_solo` / `algorithm_exact` they are ("", 0.0) and ignored.
#   embed                    -> gather body, no reduction           -> bit_exact_solo
#   lm_head_gemv             -> fused_gemv body, strict-ordered sum -> algorithm_exact
#   attention_head256_f16kv  -> attention_scores, softmax/exp/tanh  -> tolerance_bounded
#   attention_head512_f16kv  -> attention_scores, softmax/exp/tanh  -> tolerance_bounded
KERNEL_EXACTNESS: dict[
    str, tuple[str, tuple[str, ...], str, float]
] = {
    "embed": ("bit_exact_solo", (), "", 0.0),
    "lm_head_gemv": (
        "algorithm_exact",
        ("reduction_order", "accum_dtype"),
        "",
        0.0,
    ),
    "attention_head256_f16kv": (
        "tolerance_bounded",
        (),
        "per_element_relative_error",
        1e-5,
    ),
    "attention_head512_f16kv": (
        "tolerance_bounded",
        (),
        "per_element_relative_error",
        1e-5,
    ),
}


def _canonical_bytes(doc: Any) -> bytes:
    return json.dumps(
        doc,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_sha256(path: Path) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(_canonical_bytes(doc)).hexdigest()


def _assert_not_sentinel(label: str, digest: str) -> None:
    if digest == SENTINEL_DIGEST:
        raise ValueError(
            f"{label} is the zero sentinel; refusing to bind manifest entry"
        )


def load_bootstrap_backend_pins(backend: str) -> tuple[str, str]:
    """Return (emitterDigest, targetDescriptorCorrectnessHash) for the given
    backend, read from any committed bootstrap fixture for that backend.
    Bootstrap fixtures are coherent across kernels for a given backend, so
    any one is representative."""
    candidates = sorted(BOOTSTRAP_ENTRIES_DIR.glob(f"*.{backend}.json"))
    if not candidates:
        raise FileNotFoundError(
            f"no bootstrap fixture found for backend={backend} in "
            f"{BOOTSTRAP_ENTRIES_DIR}"
        )
    entry = json.loads(candidates[0].read_text(encoding="utf-8"))
    return entry["emitterDigest"], entry["targetDescriptorCorrectnessHash"]


def load_frontend_version(semantic_path: Path) -> str:
    doc = json.loads(semantic_path.read_text(encoding="utf-8"))
    version = doc.get("frontendVersion", "")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{semantic_path}: frontendVersion missing or empty")
    return version


def real_kernel_entry(kernel: str, backend: str) -> dict[str, Any]:
    if kernel not in KERNEL_EXACTNESS:
        raise ValueError(
            f"real kernel {kernel!r} not in KERNEL_EXACTNESS registry; "
            f"add an explicit exactness policy before generating."
        )
    semantic_path = REAL_FIXTURES_DIR / kernel / f"{kernel}.tsir-semantic.json"
    realization_path = (
        REAL_FIXTURES_DIR / kernel / f"{kernel}.tsir-realization.{backend}.json"
    )
    for path in (semantic_path, realization_path):
        if not path.exists():
            raise FileNotFoundError(f"missing real-kernel fixture: {path}")

    tsir_semantic_digest = _canonical_sha256(semantic_path)
    tsir_realization_digest = _canonical_sha256(realization_path)
    emitter_digest, target_descriptor_correctness_hash = load_bootstrap_backend_pins(
        backend
    )
    frontend_version = load_frontend_version(semantic_path)
    exactness_class, invariants, tolerance_metric, tolerance_epsilon = (
        KERNEL_EXACTNESS[kernel]
    )

    _assert_not_sentinel("tsirSemanticDigest", tsir_semantic_digest)
    _assert_not_sentinel("tsirRealizationDigest", tsir_realization_digest)
    _assert_not_sentinel("emitterDigest", emitter_digest)
    _assert_not_sentinel(
        "targetDescriptorCorrectnessHash", target_descriptor_correctness_hash
    )

    return build_manifest_lowering_entry(
        ManifestLoweringInputs(
            kernel_ref=f"{REAL_KERNEL_REF_PREFIX}{kernel}",
            backend=backend,
            target_descriptor_correctness_hash=target_descriptor_correctness_hash,
            frontend_version=frontend_version,
            tsir_semantic_digest=tsir_semantic_digest,
            tsir_realization_digest=tsir_realization_digest,
            emitter_digest=emitter_digest,
            compiler_version=REAL_COMPILER_VERSION,
            exactness_class=exactness_class,
            algorithm_exact_invariants=invariants,
            tolerance_metric=tolerance_metric,
            tolerance_epsilon=tolerance_epsilon,
            rejection_reasons=(),
        )
    )


def _entry_text(entry: dict[str, Any]) -> str:
    return json.dumps(entry, indent=2, sort_keys=True) + "\n"


def generate_entries() -> dict[str, dict[str, Any]]:
    fixtures: dict[str, dict[str, Any]] = {}
    for kernel in sorted(KERNEL_EXACTNESS.keys()):
        for backend in SUPPORTED_BACKENDS:
            entry = real_kernel_entry(kernel, backend)
            name = f"{kernel}.{backend}.json"
            if name in fixtures:
                raise ValueError(f"duplicate TSIR real manifest fixture: {name}")
            fixtures[name] = entry
    expected = len(KERNEL_EXACTNESS) * len(SUPPORTED_BACKENDS)
    if len(fixtures) != expected:
        raise ValueError(
            f"expected {expected} real manifest fixtures, got {len(fixtures)}"
        )
    return fixtures


def write_entries(
    output_dir: Path,
    fixtures: dict[str, dict[str, Any]],
    check: bool,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for name, entry in sorted(fixtures.items()):
        path = output_dir / name
        expected = _entry_text(entry)
        if check:
            if not path.exists():
                failures.append(f"missing fixture: {path}")
                continue
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                failures.append(f"stale fixture: {path}")
            continue
        path.write_text(expected, encoding="utf-8")
        digest = manifest_lowering_entry_digest(entry)
        print(f"{path.relative_to(REPO_ROOT)} manifestLoweringEntryDigest={digest}")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where real-kernel fixture JSON files are written.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed fixtures differ from regenerated entries.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        fixtures = generate_entries()
        return write_entries(args.output_dir, fixtures, args.check)
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
