#!/usr/bin/env python3
"""Verify per-kernel byte identity between Qwen 64L and 1L compile roots.

Parallel to ``bench/tools/verify_per_kernel_byte_identity.py`` (the
generic two-root comparator) and ``aggregate_qwen_3_6_27b_truncated_decode_compile_attempt.py``
(the 1L compile aggregator). This tool drives the rung-6 precondition for
Qwen 3.6 27B specifically: emit both the manifest-shape (numLayers from
the smoke config) bundle and a 1L truncation, then assert every shared
kernel emits byte-identical layout.csl, pe_program.csl, and
pe_program.metadata.json on both sides.

Pipeline:

  1. Re-emit the manifest-shape Qwen bundle from the smoke config.
  2. Re-emit a 1L Qwen bundle from the same config with numLayers=1.
  3. Diff each per-kernel artifact under ``compile/<kernel>/`` between
     the two bundles.
  4. Write the typed receipt to bench/out/
     r3-2-27b-manifest-shape-1L-identity/receipt.json with hash-bound
     smoke config and per-kernel sha256 records.

Property: per-kernel CSL is a function of layer class, not layer
instance. If the 64L emit and 1L emit disagree on any byte of any
shared kernel, that is a kernel-emit bug — the byte-identity test that
licenses 1L truncation as a stand-in for 64L parity at first-token
boundary probes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)
from bench.tools.verify_per_kernel_byte_identity import (  # noqa: E402
    build_receipt,
)

DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT
    / "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json"
)
DEFAULT_HOST_PLAN_TOOL = (
    REPO_ROOT / "runtime/zig/zig-out/bin/doe-csl-host-plan-tool"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-2-27b-manifest-shape-1L-identity"
    / "receipt.json"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke-config", type=Path, default=DEFAULT_SMOKE_CONFIG)
    p.add_argument(
        "--host-plan-tool",
        type=Path,
        default=DEFAULT_HOST_PLAN_TOOL,
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--manifest-bundle-root",
        type=Path,
        default=None,
        help=(
            "Where to materialize the manifest-shape (numLayers from "
            "the smoke config) bundle. Defaults to a tempdir."
        ),
    )
    p.add_argument(
        "--truncated-bundle-root",
        type=Path,
        default=None,
        help=(
            "Where to materialize the 1L truncation bundle. Defaults "
            "to a tempdir."
        ),
    )
    p.add_argument(
        "--keep-bundles",
        action="store_true",
        help="Keep both bundle dirs after comparison (default: remove).",
    )
    return p.parse_args()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _write_smoke_variant(
    src: Path, dst: Path, *, num_layers: int | None
) -> None:
    cfg = json.loads(src.read_text(encoding="utf-8"))
    if num_layers is not None:
        cfg.setdefault("modelConfig", {})["numLayers"] = num_layers
    dst.write_text(json.dumps(cfg, indent=2) + "\n")


def _emit_bundle(
    host_plan_tool: Path, smoke_path: Path, bundle_root: Path
) -> None:
    bundle_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(host_plan_tool),
        "--input", str(smoke_path),
        "--bundle-root", str(bundle_root),
        "--mode", "steps",
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"host-plan-tool failed for {smoke_path}: rc={res.returncode}\n"
            f"stdout: {res.stdout}\nstderr: {res.stderr}"
        )


def main() -> int:
    args = parse_args()

    cleanup_paths: list[Path] = []
    if args.manifest_bundle_root is None:
        manifest_dir = Path(tempfile.mkdtemp(prefix="qwen-manifest-bundle-"))
        if not args.keep_bundles:
            cleanup_paths.append(manifest_dir)
    else:
        manifest_dir = args.manifest_bundle_root.resolve()
        manifest_dir.mkdir(parents=True, exist_ok=True)

    if args.truncated_bundle_root is None:
        truncated_dir = Path(tempfile.mkdtemp(prefix="qwen-1l-bundle-"))
        if not args.keep_bundles:
            cleanup_paths.append(truncated_dir)
    else:
        truncated_dir = args.truncated_bundle_root.resolve()
        truncated_dir.mkdir(parents=True, exist_ok=True)

    try:
        manifest_smoke = manifest_dir / "qwen-3-6-27b-smoke-manifest.json"
        truncated_smoke = truncated_dir / "qwen-3-6-27b-smoke-1L.json"
        _write_smoke_variant(args.smoke_config, manifest_smoke, num_layers=None)
        _write_smoke_variant(args.smoke_config, truncated_smoke, num_layers=1)

        _emit_bundle(args.host_plan_tool, manifest_smoke, manifest_dir)
        _emit_bundle(args.host_plan_tool, truncated_smoke, truncated_dir)

        manifest_compile = manifest_dir / "compile"
        truncated_compile = truncated_dir / "compile"
        if not manifest_compile.is_dir():
            sys.stderr.write(
                f"manifest bundle missing compile dir: {manifest_compile}\n"
            )
            return 2
        if not truncated_compile.is_dir():
            sys.stderr.write(
                f"truncated bundle missing compile dir: {truncated_compile}\n"
            )
            return 2

        receipt = build_receipt(
            left_root=manifest_compile,
            right_root=truncated_compile,
            label_left="qwen-3-6-27b-64L",
            label_right="qwen-3-6-27b-1L",
        )
        receipt["modelId"] = "qwen-3-6-27b-q4k-ehaf16"
        receipt["modelFamily"] = "qwen3"
        receipt["target"] = "wse3"
        receipt["smokeConfigPath"] = _rel(args.smoke_config)
        receipt["claim"]["scope"] = (
            "Per-kernel byte identity between the manifest-shape Qwen "
            "3.6 27B bundle (numLayers from the smoke config) and a 1L "
            "truncation. Bound iff every shared kernel emits the same "
            "layout.csl, pe_program.csl, and pe_program.metadata.json "
            "bytes on both sides — the property the 1L truncated-decode "
            "compile-attempt receipt relies on so per-target verdicts "
            "from the 1L bundle stand in for 64L verdicts on shared "
            "kernels."
        )
        receipt["claim"]["notWhat"] = (
            "Not a numerical or hardware claim. Does not invoke cslc — "
            "cslc verdicts come from the truncated-decode aggregator. "
            "Compile-dir-missing kernels in either bundle are reported "
            "via leftOnly/rightOnly counts but do not block the verdict."
        )

        try:
            enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
        except ReceiptHashSpineError as err:
            sys.stderr.write(
                "verify_qwen_3_6_27b_per_kernel_byte_identity: "
                f"receipt hash spine rejected emit:\n  {err}\n"
            )
            return 2

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        totals = receipt["totals"]
        print(
            f"wrote {_rel(args.out)} verdict={receipt['verdict']} "
            f"shared={totals['sharedKernelCount']} "
            f"match={totals['matchCount']} "
            f"mismatch={totals['mismatchCount']} "
            f"leftOnly={totals['leftOnlyCount']} "
            f"rightOnly={totals['rightOnlyCount']}"
        )
        return 0 if receipt["verdict"] == "bound" else 1
    finally:
        for path in cleanup_paths:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
