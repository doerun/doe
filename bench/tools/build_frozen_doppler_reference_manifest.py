"""Assemble a frozen Doppler reference fixture manifest from captured .npy files.

Mitigates the frozen-Doppler-reference fixture data gap in
``docs/cerebras-evidence-ledger-gemma.md`` (Manifest-shape simfabric proof plan):
the Doe-side schema + validator
(``config/doe-frozen-doppler-reference.schema.json``,
``bench/tools/validate_frozen_doppler_reference.py``) have shipped,
but the per-layer per-probe-point activation `.npy` files come from a
Doppler reference run.

This tool walks a directory tree produced by Doppler's
`tools/run-program-bundle-reference.js --tsir-fixture-dir <dir>`
flag, which writes::

    <dir>/layer_<layerIdx>/{post_rmsnorm,post_qkv,post_attn,post_ffn}.npy

and emits a `frozen-reference.manifest.json` next to it that conforms
to ``config/doe-frozen-doppler-reference.schema.json``. The manifest
cites every `.npy` file with a `path` + `sha256` + `byteLength` +
`elemDtype` + `elemShape` block, plus the transcript JSON the run
produced. The aggregate `fixtureDigest` is computed exactly the way
the validator recomputes it (canonical-JSON of
``{transcript, activations, firstTokenLogits}``) so the validator
binds.

Usage::

    python3 bench/tools/build_frozen_doppler_reference_manifest.py \
        --fixture-dir bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots \
        --transcript bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/reference-report.json \
        --model-id gemma-4-31b-it-text-q4k-ehf16-af32 \
        --prompt "The color of the sky is"

Writes the manifest to ``<fixture-dir>/frozen-reference.manifest.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Defer the canonical fixtureDigest computation to the validator so the two
# tools cannot drift; the validator is the source of truth for what binds.
from bench.tools.validate_frozen_doppler_reference import (  # noqa: E402
    compute_fixture_digest as _validator_compute_fixture_digest,
)
from bench.tools._lane_dtype_profile import (  # noqa: E402
    LaneDtypeProfileError,
    canonical_dtype_profile,
)

TSIR_PROBE_NAMES = ("post_rmsnorm", "post_qkv", "post_attn", "post_ffn")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read_npy_header(path: Path) -> tuple[str, list[int]]:
    """Parse the .npy v1.0 header to extract dtype + shape."""
    with path.open("rb") as fh:
        magic = fh.read(6)
        if magic != b"\x93NUMPY":
            raise ValueError(f"{path} is not a .npy file (bad magic)")
        ver = fh.read(2)
        if ver[0] != 1:
            raise ValueError(f"{path} unsupported .npy version {ver[0]}.{ver[1]}")
        header_len_bytes = fh.read(2)
        header_len = header_len_bytes[0] | (header_len_bytes[1] << 8)
        header = fh.read(header_len).decode("ascii")
    descr_match = re.search(r"'descr':\s*'([^']+)'", header)
    shape_match = re.search(r"'shape':\s*\(([^)]*)\)", header)
    if not descr_match or not shape_match:
        raise ValueError(f"{path} npy header missing descr/shape")
    descr = descr_match.group(1)
    shape_text = shape_match.group(1).strip()
    shape: list[int] = []
    if shape_text:
        for piece in shape_text.split(","):
            piece = piece.strip()
            if not piece:
                continue
            shape.append(int(piece))
    dtype_map = {"<f4": "float32", "<f2": "float16", "<f8": "float64"}
    elem_dtype = dtype_map.get(descr, descr)
    return elem_dtype, shape


def collect_activations(fixture_dir: Path) -> dict[str, dict[str, Any]]:
    """Walk ``<fixture_dir>/layer_<N>/<probe>.npy`` and build the activations map."""
    activations: dict[str, dict[str, Any]] = {}
    for layer_dir in sorted(fixture_dir.glob("layer_*")):
        if not layer_dir.is_dir():
            continue
        m = re.fullmatch(r"layer_(\d+)", layer_dir.name)
        if not m:
            continue
        layer_idx = m.group(1)
        layer_block: dict[str, Any] = {}
        for probe_name in TSIR_PROBE_NAMES:
            probe_path = layer_dir / f"{probe_name}.npy"
            if not probe_path.is_file():
                continue
            elem_dtype, elem_shape = _read_npy_header(probe_path)
            byte_length = probe_path.stat().st_size
            sha = _sha256_file(probe_path)
            rel = str(probe_path.relative_to(fixture_dir))
            layer_block[probe_name] = {
                "path": rel,
                "sha256": sha,
                "byteLength": byte_length,
                "elemDtype": elem_dtype,
                "elemShape": elem_shape,
            }
        if layer_block:
            activations[layer_idx] = layer_block
    return activations


def build_transcript_block(
    fixture_dir: Path, transcript_path: Path
) -> dict[str, Any]:
    rel = str(transcript_path.relative_to(fixture_dir))
    return {
        "path": rel,
        "sha256": _sha256_file(transcript_path),
        "byteLength": transcript_path.stat().st_size,
    }


def build_first_token_logits_block(
    fixture_dir: Path, logits_path: Path | None
) -> dict[str, Any] | None:
    if logits_path is None or not logits_path.is_file():
        return None
    elem_dtype, elem_shape = _read_npy_header(logits_path)
    rel = str(logits_path.relative_to(fixture_dir))
    return {
        "path": rel,
        "sha256": _sha256_file(logits_path),
        "byteLength": logits_path.stat().st_size,
        "elemDtype": elem_dtype,
        "elemShape": elem_shape,
    }


def compute_fixture_digest(
    transcript: dict[str, Any],
    activations: dict[str, Any],
    first_token_logits: dict[str, Any] | None,
) -> str:
    """Compute the canonical fixtureDigest for the given manifest blocks.

    Forwards to ``validate_frozen_doppler_reference.compute_fixture_digest``
    so the builder and validator cannot drift. The canonical projection is
    (path, sha256) per artifact — extra fields like byteLength / elemDtype /
    elemShape are intentionally excluded so cosmetic edits to the manifest
    do not invalidate the digest.
    """
    manifest_view: dict[str, Any] = {
        "transcript": transcript,
        "activations": activations,
    }
    if first_token_logits is not None:
        manifest_view["firstTokenLogits"] = first_token_logits
    return _validator_compute_fixture_digest(manifest_view)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture-dir", type=Path, required=True)
    p.add_argument("--transcript", type=Path, required=True)
    p.add_argument("--first-token-logits", type=Path, default=None)
    p.add_argument("--model-id", type=str, required=True)
    p.add_argument("--model-revision", type=str, default=None)
    p.add_argument("--rdrr-variant", type=str, default=None)
    p.add_argument("--prompt", type=str, default=None)
    p.add_argument("--decode-steps", type=int, default=None)
    p.add_argument(
        "--source-doppler-manifest",
        type=Path,
        default=None,
        help=(
            "Optional path to the source Doppler manifest.json. When set, "
            "the canonical dtypeProfile is read from "
            "manifest.quantizationInfo (weights/embeddings/lmHead/compute/"
            "variantTag) and embedded in the fixture manifest so the "
            "validator can enforce --lane-key under --require-dtype-profile. "
            "Required for new af16 / non-af32 lanes; legacy af32 fixtures "
            "captured before this contract may omit it."
        ),
    )
    p.add_argument(
        "--frozen-reason",
        type=str,
        default=(
            "Captured via doppler tools/run-program-bundle-reference.js "
            "--tsir-fixture-dir; serves as the frozen-Doppler-reference frozen Doppler "
            "reference for the Doe manifest-shape simfabric proof plan."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    fixture_dir: Path = args.fixture_dir
    transcript_path: Path = args.transcript

    if not fixture_dir.is_dir():
        sys.stderr.write(
            f"build_frozen_doppler_reference_manifest: fixture-dir "
            f"{fixture_dir} is not a directory\n"
        )
        return 2
    if not transcript_path.is_file():
        sys.stderr.write(
            f"build_frozen_doppler_reference_manifest: transcript "
            f"{transcript_path} not found\n"
        )
        return 2

    transcript_block = build_transcript_block(fixture_dir, transcript_path)
    activations = collect_activations(fixture_dir)
    if not activations:
        sys.stderr.write(
            "build_frozen_doppler_reference_manifest: no "
            "layer_<N>/<probe>.npy files found under "
            f"{fixture_dir} -- did the Doppler run actually capture "
            "anything?\n"
        )
        return 2

    first_token_logits_block = build_first_token_logits_block(
        fixture_dir, args.first_token_logits
    )

    fixture_digest = compute_fixture_digest(
        transcript_block, activations, first_token_logits_block
    )

    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_manifest",
        "modelId": args.model_id,
        "fixtureDigest": fixture_digest,
        "transcript": transcript_block,
        "activations": activations,
        "frozenAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frozenReason": args.frozen_reason,
    }
    if args.model_revision:
        manifest["modelRevision"] = args.model_revision
    if args.rdrr_variant:
        manifest["rdrrVariant"] = args.rdrr_variant
    if args.prompt is not None:
        manifest["promptText"] = args.prompt
    if args.decode_steps is not None:
        manifest["decodeSteps"] = int(args.decode_steps)
    if first_token_logits_block is not None:
        manifest["firstTokenLogits"] = first_token_logits_block
    if args.source_doppler_manifest is not None:
        if not args.source_doppler_manifest.is_file():
            sys.stderr.write(
                "build_frozen_doppler_reference_manifest: "
                f"--source-doppler-manifest {args.source_doppler_manifest} "
                "not found\n"
            )
            return 2
        try:
            source_manifest = json.loads(
                args.source_doppler_manifest.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as err:
            sys.stderr.write(
                "build_frozen_doppler_reference_manifest: "
                f"--source-doppler-manifest decode failed: {err}\n"
            )
            return 2
        try:
            manifest["dtypeProfile"] = canonical_dtype_profile(
                source_manifest.get("quantizationInfo")
            )
        except LaneDtypeProfileError as err:
            sys.stderr.write(
                "build_frozen_doppler_reference_manifest: "
                f"source-doppler-manifest dtypeProfile rejected: {err}\n"
            )
            return 2

    manifest_path = fixture_dir / "frozen-reference.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "manifestPath": str(manifest_path),
                "fixtureDigest": fixture_digest,
                "layerCount": len(activations),
                "probeNamesPerLayer": {
                    layer: sorted(block.keys())
                    for layer, block in activations.items()
                },
                "transcriptSha256": transcript_block["sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
