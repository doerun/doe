#!/usr/bin/env python3
"""Build a Doppler-prefix / CSL-splice receipt.

The receipt binds real Doppler Gemma state to the CSL output expected
at a splice point. It can emit a blocked receipt when the CSL producer
is absent; that is the correct artifact while the runner is still being
wired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)


DEFAULT_MODEL_ID = "gemma-4-31b-it-text-q4k-ehf16-af16"
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "../doppler/models/local/gemma-4-31b-it-text-q4k-ehf16-af16/manifest.json"
).resolve()
DEFAULT_REFERENCE_EXPORT = (
    REPO_ROOT
    / "bench/out/doppler-reference/"
    "gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/"
    "doppler_int4ple_reference_export.json"
)
DEFAULT_FIXTURE_ROOT = REPO_ROOT / "bench/fixtures/r3-1-31b-doppler-frozen-af16"
DEFAULT_OUT = REPO_ROOT / "bench/out/r3-1-31b-af16-doppler-csl-splice/receipt.json"
FIXTURE_MANIFEST = "frozen-reference.manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["single_block_hidden", "last_layer_tail_token"], required=True)
    parser.add_argument("--layer-index", type=int, default=59)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--reference-export", type=Path, default=DEFAULT_REFERENCE_EXPORT)
    parser.add_argument("--frozen-fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--input-probe", default="pre_layer_input")
    parser.add_argument("--expected-probe", default="post_ffn")
    parser.add_argument("--csl-output-tensor", type=Path, default=None)
    parser.add_argument("--csl-output-token-id", type=int, default=None)
    parser.add_argument("--csl-command", default=None)
    parser.add_argument("--atol", type=float, default=2e-2)
    parser.add_argument("--rtol", type=float, default=2e-2)
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the receipt is blocked but schema/hash validation passes.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_link(path: Path, *, root: Path = REPO_ROOT, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    block = {
        "path": rel(path) if root == REPO_ROOT else path.resolve().relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "byteLength": path.stat().st_size,
    }
    if extra:
        block.update(extra)
    return block


def read_npy_header(path: Path) -> tuple[str, list[int]] | None:
    try:
        with path.open("rb") as handle:
            if handle.read(6) != b"\x93NUMPY":
                return None
            major = handle.read(1)
            handle.read(1)
            if major == b"\x01":
                (header_len,) = struct.unpack("<H", handle.read(2))
            elif major in {b"\x02", b"\x03"}:
                (header_len,) = struct.unpack("<I", handle.read(4))
            else:
                return None
            header = handle.read(header_len).decode("latin-1")
    except (OSError, struct.error):
        return None
    try:
        descr_start = header.index("'descr':") + len("'descr':")
        descr_end = header.index(",", descr_start)
        descr = header[descr_start:descr_end].strip().strip("'\"")
        shape_start = header.index("(", header.index("'shape':")) + 1
        shape_end = header.index(")", shape_start)
        shape = [
            int(part.strip())
            for part in header[shape_start:shape_end].split(",")
            if part.strip()
        ]
    except ValueError:
        return None
    dtype = {
        "<f4": "float32",
        "<f2": "float16",
        "<f8": "float64",
        "<u4": "uint32",
    }.get(descr, descr)
    return dtype, shape


def fixture_tensor(
    *,
    fixture_root: Path,
    fixture_manifest: dict[str, Any],
    layer_index: int,
    probe: str,
) -> dict[str, Any] | None:
    layer = (fixture_manifest.get("activations") or {}).get(str(layer_index))
    if not isinstance(layer, dict):
        return None
    spec = layer.get(probe)
    if not isinstance(spec, dict):
        return None
    path = fixture_root / str(spec.get("path") or "")
    if not path.is_file():
        return None
    return {
        "path": rel(path),
        "sha256": sha256_file(path),
        "byteLength": path.stat().st_size,
        "elemDtype": spec.get("elemDtype"),
        "elemShape": spec.get("elemShape"),
    }


def generated_token_ids(reference_export: dict[str, Any]) -> list[int]:
    transcript = reference_export.get("decodeTranscript") or {}
    generated = transcript.get("generatedTokenIds")
    if isinstance(generated, dict):
        preview = generated.get("preview")
        if isinstance(preview, list):
            return [int(item) for item in preview]
    if isinstance(generated, list):
        return [int(item) for item in generated]
    return []


def load_float_tensor(path: Path) -> np.ndarray:
    return np.load(path, allow_pickle=False).astype(np.float32, copy=False).ravel()


def compare_float_tensors(
    *,
    expected_path: Path,
    observed_path: Path,
    atol: float,
    rtol: float,
) -> dict[str, Any]:
    expected = load_float_tensor(expected_path)
    observed = load_float_tensor(observed_path)
    if expected.shape != observed.shape:
        return {
            "match": False,
            "maxAbsDiff": None,
            "maxRelDiff": None,
            "shapeMismatch": {
                "expected": list(expected.shape),
                "observed": list(observed.shape),
            },
        }
    diff = np.abs(observed - expected)
    denom = np.maximum(np.abs(expected), np.float32(1e-9))
    rel = diff / denom
    return {
        "match": bool(np.allclose(observed, expected, atol=atol, rtol=rtol)),
        "maxAbsDiff": float(np.max(diff)) if diff.size else 0.0,
        "maxRelDiff": float(np.max(rel)) if rel.size else 0.0,
        "shapeMismatch": None,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = resolve(args.manifest)
    reference_export_path = resolve(args.reference_export)
    fixture_root = resolve(args.frozen_fixture_root)
    fixture_manifest_path = fixture_root / FIXTURE_MANIFEST

    reference_export = load_json(reference_export_path)
    fixture_manifest = load_json(fixture_manifest_path)
    input_tensor = fixture_tensor(
        fixture_root=fixture_root,
        fixture_manifest=fixture_manifest,
        layer_index=args.layer_index,
        probe=args.input_probe,
    )
    expected_tensor = None
    if args.kind == "single_block_hidden":
        expected_tensor = fixture_tensor(
            fixture_root=fixture_root,
            fixture_manifest=fixture_manifest,
            layer_index=args.layer_index,
            probe=args.expected_probe,
        )

    tokens = generated_token_ids(reference_export)
    expected_token_id = tokens[0] if tokens else None
    csl_output_path = resolve(args.csl_output_tensor) if args.csl_output_tensor else None
    csl_output_tensor = None
    if csl_output_path is not None and csl_output_path.is_file():
        npy = read_npy_header(csl_output_path)
        extra = {}
        if npy is not None:
            extra = {"elemDtype": npy[0], "elemShape": npy[1]}
        csl_output_tensor = hash_link(csl_output_path, extra=extra)

    if args.kind == "single_block_hidden":
        comparison_mode = "hidden_tensor_tolerance"
        expected_sha = expected_tensor["sha256"] if expected_tensor else None
        observed_sha = csl_output_tensor["sha256"] if csl_output_tensor else None
        numeric = {
            "match": None,
            "maxAbsDiff": None,
            "maxRelDiff": None,
            "shapeMismatch": None,
        }
        if input_tensor is None:
            status = "blocked_missing_doppler_input"
            match = None
            blocker = f"fixture_probe_absent:{args.layer_index}:{args.input_probe}"
        elif expected_tensor is None:
            status = "blocked_missing_doppler_expected"
            match = None
            blocker = f"fixture_probe_absent:{args.layer_index}:{args.expected_probe}"
        elif csl_output_tensor is None:
            status = "blocked_missing_csl_output"
            match = None
            blocker = "csl_splice_output_absent"
        else:
            expected_path = fixture_root / str(
                ((fixture_manifest.get("activations") or {})
                 .get(str(args.layer_index)) or {})
                .get(args.expected_probe, {})
                .get("path")
            )
            numeric = compare_float_tensors(
                expected_path=expected_path,
                observed_path=csl_output_path,
                atol=float(args.atol),
                rtol=float(args.rtol),
            )
            match = bool(numeric["match"])
            status = "matched" if match else "mismatch"
            blocker = None if match else "csl_splice_tensor_mismatch"
    else:
        comparison_mode = "token_equal"
        expected_sha = None
        observed_sha = None
        if input_tensor is None:
            status = "blocked_missing_doppler_input"
            match = None
            blocker = f"fixture_probe_absent:{args.layer_index}:{args.input_probe}"
        elif expected_token_id is None:
            status = "blocked_missing_doppler_expected"
            match = None
            blocker = "doppler_reference_token_absent"
        elif args.csl_output_token_id is None:
            status = "blocked_missing_csl_output"
            match = None
            blocker = "csl_splice_token_absent"
        else:
            match = expected_token_id == int(args.csl_output_token_id)
            status = "matched" if match else "mismatch"
            blocker = None if match else "csl_splice_token_mismatch"

    verdict = "bound" if status == "matched" else "blocked"
    csl_output_ready = (
        csl_output_tensor is not None
        if args.kind == "single_block_hidden"
        else args.csl_output_token_id is not None
    )
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doppler_to_csl_splice_receipt",
        "receiptClass": "manifest_shape_doppler_to_csl_splice",
        "comparisonMode": "parity",
        "verdict": verdict,
        "blocker": blocker,
        "modelId": args.model_id,
        "manifestPath": rel(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        "referenceFixtureHash": fixture_manifest["fixtureDigest"],
        "sourceProgram": {
            "authoringSurface": "doppler_execution_v1",
            "manifestSha256": str(reference_export.get("manifestSha256") or ""),
            "executionGraphSha256": str(reference_export.get("executionGraphSha256") or ""),
            "weightSetSha256": str(reference_export.get("weightSetSha256") or ""),
            "inputSetSha256": str(reference_export.get("inputSetSha256") or ""),
            "programBundleId": reference_export.get("programBundleId"),
            "referenceExport": hash_link(reference_export_path),
        },
        "splicePoint": {
            "kind": args.kind,
            "layerIndex": args.layer_index,
            "promptTokenCount": int(
                (reference_export.get("decodeTranscript") or {}).get("promptTokenCount")
                or (reference_export.get("inputSetComponents") or {}).get("tokenCount")
                or 0
            ),
            "inputProbe": args.input_probe,
            "expectedProbe": args.expected_probe if args.kind == "single_block_hidden" else None,
        },
        "dopplerReference": {
            "fixtureManifest": hash_link(fixture_manifest_path),
            "fixtureRoot": rel(fixture_root),
            "inputTensor": input_tensor,
            "expectedTensor": expected_tensor,
            "expectedTokenId": expected_token_id if args.kind == "last_layer_tail_token" else None,
            "generatedTokenIds": tokens,
        },
        "cslRun": {
            "status": "output_ready" if csl_output_ready else "blocked",
            "outputTensor": csl_output_tensor,
            "outputTokenId": args.csl_output_token_id,
            "command": args.csl_command,
        },
        "comparison": {
            "mode": comparison_mode,
            "status": status,
            "match": match,
            "expectedSha256": expected_sha,
            "observedSha256": observed_sha,
            "expectedTokenId": expected_token_id if args.kind == "last_layer_tail_token" else None,
            "observedTokenId": args.csl_output_token_id if args.kind == "last_layer_tail_token" else None,
            "atol": float(args.atol) if args.kind == "single_block_hidden" else None,
            "rtol": float(args.rtol) if args.kind == "single_block_hidden" else None,
            "maxAbsDiff": numeric["maxAbsDiff"] if args.kind == "single_block_hidden" else None,
            "maxRelDiff": numeric["maxRelDiff"] if args.kind == "single_block_hidden" else None,
        },
        "claim": {
            "scope": (
                "Doppler supplies real Gemma 4 31B af16 state at the splice point; "
                "CSL is responsible only for the declared suffix output."
            ),
            "notWhat": (
                "Not a full-graph CSL execution receipt and not hardware evidence. "
                "A blocked receipt names the missing CSL producer rather than "
                "promoting Doppler-only output."
            ),
        },
    }
    return receipt


def validate_schema(receipt: dict[str, Any]) -> None:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return
    schema_path = REPO_ROOT / "config/doppler-to-csl-splice-receipt.schema.json"
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(receipt)


def main() -> int:
    args = parse_args()
    receipt = build_receipt(args)
    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
        validate_schema(receipt)
    except (ReceiptHashSpineError, Exception) as err:
        sys.stderr.write(f"build_doppler_to_csl_splice_receipt: {err}\n")
        return 2
    out = resolve(args.out)
    write_json(out, receipt)
    print(
        f"wrote {rel(out)} "
        f"(verdict={receipt['verdict']}, kind={receipt['splicePoint']['kind']}, "
        f"blocker={receipt['blocker']})"
    )
    if receipt["verdict"] == "bound" or args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
