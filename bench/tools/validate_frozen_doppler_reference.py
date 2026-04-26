#!/usr/bin/env python3
"""Validate a frozen Doppler reference fixture against its manifest schema.

Mitigates "Frozen Doppler reference fixture (rung 5)" from
docs/cerebras-north-star.md (Manifest-shape simfabric proof plan). The
fixture lives at `bench/fixtures/r3-1-31b-doppler-frozen/` (or wherever
`--root` points) and contains:

  - `frozen-reference.manifest.json` (schema:
    `config/doe-frozen-doppler-reference.schema.json`)
  - `transcript.json`
  - `activations/<layer>/<probe-point>.npy`
  - optional `first-token-logits.npy`

This tool walks the manifest, validates it against the schema, then for
every cited artifact:

  1) confirms the file exists at the cited path,
  2) hashes it and compares against the cited sha256,
  3) records byteLength, and (for .npy) elemDtype / elemShape, when the
     manifest cites those fields.

Finally it recomputes `fixtureDigest` from the cited paths + sha256s and
verifies it matches the manifest's claim. Downstream receipts reference
the same digest as `referenceFixtureHash`; the rung-1 receipt-emit guard
(`bench/tools/_receipt_hash_guard.py`) refuses receipts whose
`receiptClass.startswith('manifest_shape')` and `comparisonMode == 'parity'`
omit the field, so the chain is fully bound.

Usage:

  python3 bench/tools/validate_frozen_doppler_reference.py \
    --root bench/fixtures/r3-1-31b-doppler-frozen \
    --out  bench/out/frozen-reference-validation/report.json

Exit codes:
  0 — fixture validates and digest matches
  1 — schema or hash violations recorded
  2 — manifest absent / unreadable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "config" / "doe-frozen-doppler-reference.schema.json"
)
MANIFEST_FILENAME = "frozen-reference.manifest.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Fixture root containing frozen-reference.manifest.json",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the validation report JSON. Defaults to stdout.",
    )
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_artifact(root: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (root / p)


def _validate_artifact(
    label: str,
    spec: dict[str, Any],
    root: Path,
    violations: list[str],
) -> str | None:
    """Validate one hash-linked artifact; return its observed sha256 or None."""
    raw_path = spec.get("path", "")
    cited_hash = spec.get("sha256", "")
    artifact = _resolve_artifact(root, raw_path)
    if not artifact.is_file():
        violations.append(
            f"{label}: cited path={raw_path!r} does not resolve to a file "
            f"under root={root}"
        )
        return None
    observed = _sha256_file(artifact)
    if observed != cited_hash:
        violations.append(
            f"{label}: sha256 drift cited={cited_hash!r} observed={observed!r}"
        )
        return None
    cited_byte_length = spec.get("byteLength")
    if cited_byte_length is not None:
        actual = artifact.stat().st_size
        if actual != cited_byte_length:
            violations.append(
                f"{label}: byteLength drift cited={cited_byte_length} "
                f"observed={actual}"
            )
    return observed


def _stable_artifact_record(
    spec: dict[str, Any],
    observed_sha: str | None,
) -> dict[str, Any]:
    """Project a hash-linked-path spec down to the canonical (path, sha256)
    fields used to compute fixtureDigest. The recorded sha256 is the cited
    value; mismatch is reported separately."""
    return {
        "path": spec.get("path", ""),
        "sha256": observed_sha if observed_sha is not None else spec.get(
            "sha256", ""
        ),
    }


def compute_fixture_digest(manifest: dict[str, Any]) -> str:
    """Compute the canonical fixtureDigest of a manifest body.

    Includes transcript, optional firstTokenLogits, and the activations
    map. Excludes fixtureDigest itself, modelId, and other metadata so
    the digest is stable under cosmetic edits.
    """
    payload: dict[str, Any] = {
        "transcript": {
            "path": manifest["transcript"]["path"],
            "sha256": manifest["transcript"]["sha256"],
        },
        "activations": {
            layer: {
                probe: {
                    "path": spec["path"],
                    "sha256": spec["sha256"],
                }
                for probe, spec in probes.items()
            }
            for layer, probes in manifest["activations"].items()
        },
    }
    first = manifest.get("firstTokenLogits")
    if first is not None:
        payload["firstTokenLogits"] = {
            "path": first["path"],
            "sha256": first["sha256"],
        }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_npy_header(path: Path) -> tuple[str, list[int]] | None:
    """Best-effort parse of a numpy .npy header (v1.0 / v2.0 / v3.0).

    Returns (dtype_str, shape_list) or None if the file is not a recognized
    .npy. Used to validate elemDtype / elemShape claims when the manifest
    cites them; absence is not a violation by itself.
    """
    try:
        with path.open("rb") as handle:
            magic = handle.read(6)
            if magic != b"\x93NUMPY":
                return None
            major = handle.read(1)
            handle.read(1)  # minor
            if major == b"\x01":
                (header_len,) = struct.unpack("<H", handle.read(2))
            elif major == b"\x02" or major == b"\x03":
                (header_len,) = struct.unpack("<I", handle.read(4))
            else:
                return None
            header = handle.read(header_len).decode("latin-1")
    except (OSError, struct.error):
        return None
    # Naive parse — robust enough for the well-formed headers numpy emits.
    descr_marker = "'descr':"
    shape_marker = "'shape':"
    try:
        descr_start = header.index(descr_marker) + len(descr_marker)
        descr_end = header.index(",", descr_start)
        descr = header[descr_start:descr_end].strip().strip("'\"")
        shape_start = header.index("(", header.index(shape_marker)) + 1
        shape_end = header.index(")", shape_start)
        raw_shape = header[shape_start:shape_end]
        shape_list = [
            int(part.strip())
            for part in raw_shape.split(",")
            if part.strip()
        ]
    except ValueError:
        return None
    return descr, shape_list


def _validate_npy_metadata(
    label: str,
    spec: dict[str, Any],
    root: Path,
    violations: list[str],
) -> None:
    cited_dtype = spec.get("elemDtype")
    cited_shape = spec.get("elemShape")
    if cited_dtype is None and cited_shape is None:
        return
    artifact = _resolve_artifact(root, spec.get("path", ""))
    if not artifact.is_file():
        return
    parsed = _read_npy_header(artifact)
    if parsed is None:
        # File exists but isn't a .npy or header didn't parse cleanly;
        # caller already validated existence + sha256.
        return
    dtype_str, shape_list = parsed
    if cited_dtype is not None:
        # Numpy descrs include the byte-order prefix (`<`, `>`, `|`); strip
        # it for the comparison.
        normalized = dtype_str.lstrip("<>|=")
        if normalized != cited_dtype:
            violations.append(
                f"{label}: elemDtype cited={cited_dtype!r} observed={dtype_str!r}"
            )
    if cited_shape is not None and list(cited_shape) != list(shape_list):
        violations.append(
            f"{label}: elemShape cited={cited_shape!r} observed={shape_list!r}"
        )


def validate_fixture(root: Path) -> dict[str, Any]:
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise SystemExit(
            f"validate_frozen_doppler_reference: manifest absent at "
            f"{manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_errors = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in jsonschema.Draft202012Validator(schema).iter_errors(manifest)
    ]

    violations: list[str] = []

    transcript = manifest.get("transcript", {})
    _validate_artifact("transcript", transcript, root, violations)

    first = manifest.get("firstTokenLogits")
    if isinstance(first, dict):
        _validate_artifact("firstTokenLogits", first, root, violations)
        _validate_npy_metadata("firstTokenLogits", first, root, violations)

    activations = manifest.get("activations", {})
    for layer, probes in activations.items():
        if not isinstance(probes, dict):
            continue
        for probe, spec in probes.items():
            label = f"activations[{layer}][{probe}]"
            if not isinstance(spec, dict):
                violations.append(f"{label}: not an object")
                continue
            _validate_artifact(label, spec, root, violations)
            _validate_npy_metadata(label, spec, root, violations)

    cited_digest = manifest.get("fixtureDigest", "")
    digest_violations: list[str] = []
    try:
        recomputed = compute_fixture_digest(manifest)
    except KeyError as err:
        recomputed = ""
        digest_violations.append(
            f"fixtureDigest: cannot recompute (missing field {err})"
        )
    if recomputed and recomputed != cited_digest:
        digest_violations.append(
            f"fixtureDigest drift: cited={cited_digest!r} "
            f"recomputed={recomputed!r}"
        )

    bound = (
        not schema_errors and not violations and not digest_violations
    )
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_validation",
        "fixtureRoot": str(root),
        "manifestPath": str(manifest_path),
        "schemaValid": not schema_errors,
        "schemaErrors": schema_errors,
        "artifactViolations": violations,
        "digestViolations": digest_violations,
        "fixtureDigestCited": cited_digest,
        "fixtureDigestRecomputed": recomputed,
        "bound": bound,
        "verdict": "bound" if bound else "not_bound",
    }


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    try:
        report = validate_fixture(root)
    except SystemExit as err:
        print(str(err), file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0 if report["bound"] else 1


if __name__ == "__main__":
    sys.exit(main())
