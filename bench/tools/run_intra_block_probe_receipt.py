#!/usr/bin/env python3
"""Intra-block probe-point receipt (single-block-parity).

Mitigates "Intra-block probes (single-block-parity)" from
docs/cerebras-evidence-ledger-gemma.md (Manifest-shape simfabric proof plan):

  > Add four probe-write hooks at the four TSIR boundary points
  > already encoded in the per-block emit. Probes write `.npy`
  > snapshots into the orchestrator's per-step scratch dir during
  > dispatch; single-block-parity hashes them and compares against the same four
  > points in the frozen fixture (refinement 6).

The boundary-emit-time probes are realized as orchestrator-side
selections: per-kernel manifest-shape (`manifest_kernel_probe_runner.py`) and layout-receipt
(`run_manifest_shape_layout_receipt.py`) already write per-kernel
output `.npy` snapshots into a scratch dir keyed by kernel name. This
tool reads a probe-point map (kernel+output → probe-point name),
selects the four boundary buffers from the scratch dir, hashes them,
and emits a receipt.

When `--frozen-fixture-root` is supplied, the receipt scores each
probe's sha256 against the frozen-Doppler-reference frozen Doppler fixture's
`activations[layerIndex][probePoint]` cited sha256, and the
`comparisonMode` is `parity`. Without the fixture, the receipt is
emitted with `comparisonMode: no_oracle` and `blocker: fixture_absent`.

Usage:

  python3 bench/tools/run_intra_block_probe_receipt.py \\
    --probe-map config/manifest-shape-intra-block-probe-map.json \\
    --dispatch-out-dir bench/out/r3-1-31b-manifest-simfabric-per-kernel \\
    --layer-index 0 \\
    --out bench/out/r3-1-31b-manifest-simfabric-intra-block-probe/L0.json \\
    [--frozen-fixture-root bench/fixtures/r3-1-31b-doppler-frozen]
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

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)


PROBE_POINTS = ("post_rmsnorm", "post_qkv", "post_attn", "post_ffn")
PROBE_MAP_SCHEMA = (
    REPO_ROOT / "config/manifest-shape-intra-block-probe-map.schema.json"
)
FROZEN_REFERENCE_MANIFEST_FILENAME = "frozen-reference.manifest.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--probe-map",
        type=Path,
        required=True,
        help="Path to a probe-map config (schema: "
        "config/manifest-shape-intra-block-probe-map.schema.json).",
    )
    p.add_argument(
        "--dispatch-out-dir",
        type=Path,
        required=True,
        help=(
            "Per-kernel dispatch out dir produced by per-kernel manifest-shape or layout-receipt. "
            "The tool reads scratch/<kernel>/out/<symbol>.npy under "
            "this root."
        ),
    )
    p.add_argument(
        "--layer-index",
        type=int,
        default=0,
        help=(
            "Layer index the probes belong to. Used to key into the "
            "frozen fixture's activations map; recorded on the receipt."
        ),
    )
    p.add_argument(
        "--frozen-fixture-root",
        type=Path,
        default=None,
        help=(
            "Optional root of a validated frozen-Doppler reference "
            "fixture (the directory containing "
            "`frozen-reference.manifest.json`). When supplied, each "
            "probe's sha256 is compared against the fixture's "
            "activations[layerIndex][probePoint] entry; receipt's "
            "comparisonMode flips to `parity`."
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Receipt output path.",
    )
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _try_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_probe_map(path: Path) -> dict[str, Any]:
    """Load and validate the probe map. Falls back to structural checks
    if jsonschema is unavailable."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        _validate_probe_map_structural(raw)
        return raw
    if not PROBE_MAP_SCHEMA.is_file():
        _validate_probe_map_structural(raw)
        return raw
    schema = json.loads(PROBE_MAP_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(raw)
    return raw


def _validate_probe_map_structural(raw: dict[str, Any]) -> None:
    if raw.get("schemaVersion") != 1:
        raise ValueError("probe map schemaVersion must be 1")
    if raw.get("artifactKind") != "doe_intra_block_probe_map":
        raise ValueError(
            "probe map artifactKind must be doe_intra_block_probe_map"
        )
    probe_points = raw.get("probePoints")
    if not isinstance(probe_points, dict):
        raise ValueError("probe map probePoints must be an object")
    for name, body in probe_points.items():
        if name not in PROBE_POINTS:
            raise ValueError(
                f"probe map: unknown probe point {name!r}"
            )
        if not isinstance(body, dict):
            raise ValueError(
                f"probe map: {name} must be an object"
            )
        for required in ("kernel", "outputSymbol"):
            if not isinstance(body.get(required), str) or not body[required]:
                raise ValueError(
                    f"probe map: {name}.{required} must be a non-empty string"
                )


def resolve_probe_npy(
    *,
    dispatch_out_dir: Path,
    kernel: str,
    output_symbol: str,
) -> Path:
    """Return the per-kernel output `.npy` path under the dispatch dir.

    per-kernel manifest-shape / layout-receipt write per-kernel scratch under
    `<dispatch_out_dir>/scratch/<kernel>/out/<symbol>.npy` — that's the
    on-disk location of the output buffer the orchestrator captured.
    """
    return (
        dispatch_out_dir
        / "scratch"
        / kernel
        / "out"
        / f"{output_symbol}.npy"
    )


def load_frozen_fixture_activations(
    root: Path,
    layer_index: int,
) -> tuple[dict[str, dict[str, Any]] | None, str | None, str | None]:
    """Read the frozen-Doppler fixture's activations for one layer.

    Returns (activations, fixture_digest, manifest_path) or (None, ...)
    when the fixture is absent.
    """
    manifest_path = root / FROZEN_REFERENCE_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None, None, None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activations = (manifest.get("activations") or {}).get(str(layer_index))
    fixture_digest = manifest.get("fixtureDigest")
    if not isinstance(activations, dict):
        return None, fixture_digest, _try_relative(manifest_path)
    return activations, fixture_digest, _try_relative(manifest_path)


def build_receipt(
    *,
    probe_map: dict[str, Any],
    probe_map_path: Path,
    probe_map_hash: str,
    dispatch_out_dir: Path,
    layer_index: int,
    frozen_fixture_root: Path | None,
) -> dict[str, Any]:
    probe_points_block = probe_map.get("probePoints") or {}
    probes_records: list[dict[str, Any]] = []
    blockers: list[str] = []

    fixture_activations: dict[str, dict[str, Any]] | None = None
    fixture_digest: str | None = None
    fixture_manifest_path: str | None = None
    if frozen_fixture_root is not None:
        (
            fixture_activations,
            fixture_digest,
            fixture_manifest_path,
        ) = load_frozen_fixture_activations(
            frozen_fixture_root, layer_index
        )
        if fixture_activations is None:
            blockers.append(
                f"fixture_layer_absent: layer {layer_index} not in "
                f"{fixture_manifest_path or frozen_fixture_root}"
            )

    for probe_point in PROBE_POINTS:
        body = probe_points_block.get(probe_point)
        if not isinstance(body, dict):
            probes_records.append(
                {
                    "probePoint": probe_point,
                    "kernel": None,
                    "outputSymbol": None,
                    "tensorPath": None,
                    "tensorBytes": 0,
                    "tensorSha256": "",
                    "fixtureSha256": None,
                    "match": False,
                    "blocker": "probe_map_missing_entry",
                }
            )
            blockers.append(
                f"probe_map_missing_entry: {probe_point}"
            )
            continue
        kernel = body["kernel"]
        symbol = body["outputSymbol"]
        npy_path = resolve_probe_npy(
            dispatch_out_dir=dispatch_out_dir,
            kernel=kernel,
            output_symbol=symbol,
        )
        per_probe_blocker: str | None = None
        if not npy_path.is_file():
            tensor_bytes = 0
            tensor_sha = ""
            per_probe_blocker = "probe_npy_absent"
            blockers.append(
                f"probe_npy_absent: {_try_relative(npy_path)}"
            )
        else:
            tensor_bytes = npy_path.stat().st_size
            tensor_sha = _sha256_file(npy_path)

        fixture_sha: str | None = None
        match = False
        if fixture_activations is not None:
            fixture_entry = fixture_activations.get(probe_point)
            if isinstance(fixture_entry, dict):
                fixture_sha = fixture_entry.get("sha256")
            if (
                tensor_sha
                and fixture_sha
                and tensor_sha == fixture_sha
            ):
                match = True
            elif tensor_sha and fixture_sha:
                blockers.append(
                    f"probe_sha_mismatch: {probe_point} "
                    f"observed={tensor_sha[:16]} "
                    f"fixture={fixture_sha[:16]}"
                )
            elif fixture_sha is None and tensor_sha:
                blockers.append(
                    f"fixture_probe_absent: {probe_point} not in "
                    f"fixture.activations[{layer_index}]"
                )
        probes_records.append(
            {
                "probePoint": probe_point,
                "kernel": kernel,
                "outputSymbol": symbol,
                "tensorPath": _try_relative(npy_path),
                "tensorBytes": tensor_bytes,
                "tensorSha256": tensor_sha,
                "fixtureSha256": fixture_sha,
                "match": match,
                "blocker": per_probe_blocker,
            }
        )

    # Parity mode requires the fixture manifest to have loaded (so
    # `referenceFixtureHash` can be cited and the receipt-hash hash spine
    # guard accepts the receipt). A `--frozen-fixture-root` that
    # points at a missing/unreadable manifest falls back to no_oracle
    # mode with a blocker.
    has_fixture = frozen_fixture_root is not None
    fixture_loaded = has_fixture and fixture_digest is not None
    comparison_mode = "parity" if fixture_loaded else "no_oracle"
    if not has_fixture:
        blockers.append("fixture_absent")
    elif not fixture_loaded:
        blockers.append("fixture_manifest_unreadable")

    if comparison_mode == "parity":
        # Strip non-blocking advisory entries and recompute.
        # Parity requires every probe matched.
        match_count = sum(1 for r in probes_records if r["match"])
        unmatched = len(probes_records) - match_count
        if unmatched > 0:
            verdict = "blocked"
        elif blockers:
            verdict = "blocked"
        else:
            verdict = "bound"
        primary_blocker = blockers[0] if blockers else None
    else:
        # No-oracle mode: bound iff every probe was readable.
        readable = all(r["tensorSha256"] for r in probes_records)
        if readable and len(blockers) == 1 and blockers[0] == "fixture_absent":
            verdict = "blocked"
            primary_blocker = "fixture_absent"
        elif readable:
            verdict = "blocked"
            primary_blocker = blockers[0]
        else:
            verdict = "blocked"
            primary_blocker = next(
                (b for b in blockers if b != "fixture_absent"),
                "fixture_absent",
            )

    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_intra_block_probe_receipt",
        "receiptClass": "manifest_shape_intra_block_probe",
        "comparisonMode": comparison_mode,
        "layerIndex": layer_index,
        "probeMapPath": _try_relative(probe_map_path),
        "probeMapHash": probe_map_hash,
        "dispatchOutDir": _try_relative(dispatch_out_dir),
        "frozenFixtureRoot": (
            _try_relative(frozen_fixture_root)
            if frozen_fixture_root is not None
            else None
        ),
        "frozenFixtureManifestPath": fixture_manifest_path,
        "referenceFixtureHash": (
            fixture_digest if has_fixture else None
        ),
        "probes": probes_records,
        "verdict": verdict,
        "blocker": primary_blocker,
        "blockers": blockers,
        "claim": {
            "scope": (
                "Per-layer hashing of the four canonical TSIR boundary "
                "probe-point activations (post_rmsnorm, post_qkv, "
                "post_attn, post_ffn) selected from the per-kernel "
                "dispatch scratch dir via the probe map. When a frozen "
                "Doppler reference fixture is supplied, each probe's "
                "sha256 is compared against the fixture's cited entry; "
                "the receipt is the per-block parity claim that full-graph-dispatch "
                "stacks on top of."
            ),
            "notWhat": (
                "Not a full-block parity claim — only the four "
                "intra-block probe boundaries are scored. Not a "
                "performance claim. Without a frozen fixture this is a "
                "hash-record receipt, not a parity verdict."
            ),
        },
    }
    return receipt


def main() -> int:
    args = parse_args()
    if not args.probe_map.is_file():
        sys.stderr.write(
            f"run_intra_block_probe_receipt: probe map absent at "
            f"{args.probe_map}\n"
        )
        return 2
    if not args.dispatch_out_dir.is_dir():
        sys.stderr.write(
            f"run_intra_block_probe_receipt: dispatch-out-dir absent at "
            f"{args.dispatch_out_dir}\n"
        )
        return 2

    try:
        probe_map = load_probe_map(args.probe_map)
    except (ValueError, json.JSONDecodeError) as err:
        sys.stderr.write(
            f"run_intra_block_probe_receipt: probe map invalid: {err}\n"
        )
        return 2
    probe_map_hash = _sha256_file(args.probe_map)

    receipt = build_receipt(
        probe_map=probe_map,
        probe_map_path=args.probe_map,
        probe_map_hash=probe_map_hash,
        dispatch_out_dir=args.dispatch_out_dir,
        layer_index=args.layer_index,
        frozen_fixture_root=args.frozen_fixture_root,
    )
    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            f"run_intra_block_probe_receipt: hash spine rejected: {err}\n"
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.out} (verdict={receipt['verdict']}, "
        f"comparisonMode={receipt['comparisonMode']}, "
        f"probes={len(receipt['probes'])})"
    )
    return 0 if receipt["verdict"] == "bound" else 1


if __name__ == "__main__":
    sys.exit(main())
