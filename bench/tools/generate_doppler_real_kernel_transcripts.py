#!/usr/bin/env python3
"""Materialize Doppler reference-transcript stubs for the 6 real kernels.

The doe_parity.py "real-kernel" reference path requires
--doppler-transcript pointing at a doppler.reference-transcript/v1 doc
for every kernel keyed under doe.tsir.real.*. The transcript's required
fields are (schema, executionGraphHash, source.hash). Each stub binds
the oracle's identity to:

  (1) executionGraphHash — the program-bundle execution graph the
      transcript was captured under. We use the 31B reference bundle's
      execution.graphHash from
      bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json.
  (2) source.hash — the per-kernel source identity. We use the sha256
      of the WGSL pinned at runtime/zig/tests/tsir/real/<kernel>/<kernel>.wgsl,
      which is what the Doe-side TSIR semantic was lowered against. The
      pinned snapshot moves only when Doppler updates the kernel and
      the Doe side intentionally re-pins.

These transcripts are *structural identity bindings*, not full
execution captures. They satisfy the --doppler-transcript prerequisite
so the canary's real-kernel reference path can record
`reference status = not_implemented (transcript identity recorded;
per-kernel probe not captured)` rather than failing on the missing
input. The actual numerical pass status needs separate
<kernel>.kernel-probe-hash files emitted by Doppler running the kernel
under deterministic inputs and hashing its output. Those are NOT
generated here.

Usage:
  python3 bench/tools/generate_doppler_real_kernel_transcripts.py \\
    [--bundle bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json] \\
    [--out-dir bench/out/r3-1-doppler-real-kernel-transcripts]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = (
    REPO_ROOT
    / "bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT / "bench/out/r3-1-doppler-real-kernel-transcripts"
)
REAL_DIR = REPO_ROOT / "runtime/zig/tests/tsir/real"
TRANSCRIPT_SCHEMA = "doppler.reference-transcript/v1"

KERNELS_AND_WGSL: tuple[tuple[str, str], ...] = (
    ("embed", "embed.wgsl"),
    ("fused_gemv", "fused_gemv.wgsl"),
    ("lm_head_gemv", "lm_head_gemv.wgsl"),
    ("rmsnorm", "rmsnorm.wgsl"),
    ("attention_head256_f16kv", "attention_head256_f16kv.wgsl"),
    ("attention_head512_f16kv", "attention_head512_f16kv.wgsl"),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    args = parse_args()
    if not args.bundle.is_file():
        sys.stderr.write(
            f"generate_doppler_real_kernel_transcripts: program bundle "
            f"not found: {args.bundle}\n"
        )
        return 2
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    execution = bundle.get("execution") or {}
    execution_graph_hash = execution.get("graphHash")
    if not isinstance(execution_graph_hash, str) or not execution_graph_hash.startswith(
        "sha256:"
    ):
        sys.stderr.write(
            f"generate_doppler_real_kernel_transcripts: "
            f"execution.graphHash missing or malformed in {args.bundle}\n"
        )
        return 2
    bundle_id = bundle.get("bundleId")
    model_id = bundle.get("modelId")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, Path, str]] = []
    for kernel, wgsl_name in KERNELS_AND_WGSL:
        wgsl_path = REAL_DIR / kernel / wgsl_name
        if not wgsl_path.is_file():
            sys.stderr.write(
                f"missing pinned WGSL for kernel {kernel!r}: {wgsl_path}\n"
            )
            return 2
        wgsl_sha = sha256_file(wgsl_path)
        wgsl_rel = str(wgsl_path.relative_to(REPO_ROOT))
        transcript = {
            "schema": TRANSCRIPT_SCHEMA,
            "executionGraphHash": execution_graph_hash,
            "source": {
                "hash": f"sha256:{wgsl_sha}",
                "path": wgsl_rel,
                "kind": "tsir-real-pinned-snapshot",
            },
            "modelId": model_id,
            "bundleId": bundle_id,
            "kernel": f"doe.tsir.real.{kernel}",
            "kind": "structural_identity_only",
            "_note": (
                "Structural identity binding only: pins (executionGraphHash, "
                "source.hash) so the doe_parity real-kernel reference path "
                "can record transcript identity. Does NOT capture per-kernel "
                "output hashes — those require Doppler-side execution under "
                "deterministic inputs, emitted as a separate "
                "<kernel>.kernel-probe-hash file (64-char hex, optional) "
                "next to this transcript. Without the probe-hash file the "
                "canary's reference comparison status records "
                "'not_implemented (transcript identity recorded; per-kernel "
                "probe not captured)'."
            ),
        }
        out_path = args.out_dir / f"{kernel}.doppler-transcript.json"
        out_path.write_text(
            json.dumps(transcript, indent=2) + "\n", encoding="utf-8"
        )
        written.append((kernel, out_path, wgsl_sha))

    print(f"wrote {len(written)} transcripts to {args.out_dir}:")
    for kernel, p, sha in written:
        rel = p.relative_to(REPO_ROOT) if p.is_absolute() else p
        print(f"  {kernel}: {rel} (source.hash=sha256:{sha[:16]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
