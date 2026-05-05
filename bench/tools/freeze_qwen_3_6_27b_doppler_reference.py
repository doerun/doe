#!/usr/bin/env python3
"""Freeze a captured Qwen 3.6 27B Doppler reference fixture into Doe.

Walks the per-layer probe directory produced by Doppler's
``tools/run-program-bundle-reference.js --tsir-fixture-dir`` and
materializes a `frozen-reference.manifest.json` conforming to
``config/doe-frozen-doppler-reference.schema.json``. Hash-links every
.npy artifact, records the transcript JSON, and computes the
fixtureDigest the receipt-hash receipt-emit guard chains to.

Pipeline:

  1. Read the source probe directory (expected layout:
     ``<src>/layer_<N>/<probe>.npy`` plus the bundle JSON).
  2. Copy probe files for the requested layer set + probe set into
     the destination fixture root.
  3. Hash each copied artifact, build the activations map.
  4. Compute fixtureDigest via canonical JSON serialization.
  5. Write the typed manifest at <dst>/frozen-reference.manifest.json.

Usage::

  python3 bench/tools/freeze_qwen_3_6_27b_doppler_reference.py \\
    --src /tmp/qwen36-reference-fixture \\
    --transcript /tmp/qwen36-reference-bundle.json \\
    --dst bench/fixtures/r3-2-27b-doppler-frozen \\
    --layers 0,1,2,3 \\
    --probes post_rmsnorm,post_qkv,post_attn,post_ffn

The default layers cover the first three linear-attention layers
(L=0/1/2) plus the first full-attention layer (L=3) so downstream
parity receipts can bisect the residual stream across the SSM-to-
full-attention boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = Path("/tmp/qwen36-reference-fixture")
DEFAULT_TRANSCRIPT = Path("/tmp/qwen36-reference-bundle.json")
DEFAULT_DST = REPO_ROOT / "bench/fixtures/r3-2-27b-doppler-frozen"
ALLOWED_PROBES = ("post_rmsnorm", "post_qkv", "post_attn", "post_ffn")
DEFAULT_LAYERS = "0,1,2,3"
DEFAULT_PROBES = ",".join(ALLOWED_PROBES)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=DEFAULT_SRC)
    p.add_argument("--transcript", type=Path, default=DEFAULT_TRANSCRIPT)
    p.add_argument("--dst", type=Path, default=DEFAULT_DST)
    p.add_argument("--layers", default=DEFAULT_LAYERS)
    p.add_argument("--probes", default=DEFAULT_PROBES)
    p.add_argument(
        "--prompt",
        default="The color of the sky is",
        help="Prompt the reference run consumed (recorded in promptText).",
    )
    p.add_argument(
        "--frozen-reason",
        default=(
            "Captured after the Doppler attention-output-gate sigmoid-vs-silu "
            "fix landed (commit fc04ec5c on Doppler feat/qwen-3-6-bringup); "
            "first deterministic Qwen 3.6 27B Doppler reference output. "
            "L=3 post_attn vs HF reference: rel_l2 ≈ 0.068 (down from 1.365 "
            "pre-fix, sign-flipped)."
        ),
    )
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_npy_descr(path: Path) -> tuple[str | None, list[int] | None]:
    import struct
    try:
        with path.open("rb") as h:
            magic = h.read(6)
            if magic != b"\x93NUMPY":
                return None, None
            major = h.read(1)
            h.read(1)  # minor
            if major == b"\x01":
                (hdr_len,) = struct.unpack("<H", h.read(2))
            elif major in (b"\x02", b"\x03"):
                (hdr_len,) = struct.unpack("<I", h.read(4))
            else:
                return None, None
            header = h.read(hdr_len).decode("latin-1")
    except (OSError, struct.error):
        return None, None
    descr_match = re.search(r"'descr':\s*'([^']+)'", header)
    shape_match = re.search(r"'shape':\s*\(([^)]*)\)", header)
    if not descr_match or not shape_match:
        return None, None
    descr = descr_match.group(1).lstrip("<>|=")
    raw_shape = shape_match.group(1)
    shape = [int(p.strip()) for p in raw_shape.split(",") if p.strip()]
    descr_to_name = {
        "f4": "float32", "f2": "float16", "f8": "float64",
    }
    return descr_to_name.get(descr, descr), shape


def main() -> int:
    args = parse_args()
    if not args.src.is_dir():
        raise SystemExit(f"src probe dir missing: {args.src}")
    if not args.transcript.is_file():
        raise SystemExit(f"transcript not found: {args.transcript}")

    layers = [int(s.strip()) for s in args.layers.split(",") if s.strip()]
    probes = [s.strip() for s in args.probes.split(",") if s.strip()]
    bad_probes = [p for p in probes if p not in ALLOWED_PROBES]
    if bad_probes:
        raise SystemExit(
            f"probe(s) not in schema enum: {bad_probes!r}; allowed: {ALLOWED_PROBES}"
        )

    args.dst.mkdir(parents=True, exist_ok=True)
    activations: dict[str, dict[str, dict]] = {}
    for layer_idx in layers:
        src_layer = args.src / f"layer_{layer_idx}"
        if not src_layer.is_dir():
            raise SystemExit(
                f"src layer dir missing: {src_layer}; reference run did not "
                f"capture layer {layer_idx}"
            )
        dst_layer = args.dst / f"layer_{layer_idx}"
        dst_layer.mkdir(parents=True, exist_ok=True)
        per_probe: dict[str, dict] = {}
        for probe in probes:
            src_npy = src_layer / f"{probe}.npy"
            if not src_npy.is_file():
                raise SystemExit(
                    f"src probe missing: {src_npy}; reference run did not "
                    f"capture {probe} at L={layer_idx}"
                )
            dst_npy = dst_layer / f"{probe}.npy"
            shutil.copy2(src_npy, dst_npy)
            sha = _sha256_file(dst_npy)
            byte_length = dst_npy.stat().st_size
            dtype, shape = _read_npy_descr(dst_npy)
            entry = {
                "path": f"layer_{layer_idx}/{probe}.npy",
                "sha256": sha,
                "byteLength": byte_length,
            }
            if dtype is not None:
                entry["elemDtype"] = dtype
            if shape is not None:
                entry["elemShape"] = shape
            per_probe[probe] = entry
        activations[str(layer_idx)] = per_probe

    transcript_dst = args.dst / "transcript.json"
    shutil.copy2(args.transcript, transcript_dst)
    transcript_entry = {
        "path": "transcript.json",
        "sha256": _sha256_file(transcript_dst),
        "byteLength": transcript_dst.stat().st_size,
    }

    digest_payload = {
        "transcript": {
            "path": transcript_entry["path"],
            "sha256": transcript_entry["sha256"],
        },
        "activations": {
            layer: {
                probe: {"path": spec["path"], "sha256": spec["sha256"]}
                for probe, spec in probes_map.items()
            }
            for layer, probes_map in activations.items()
        },
    }
    canonical = json.dumps(digest_payload, sort_keys=True, separators=(",", ":"))
    fixture_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    transcript_obj = json.loads(transcript_dst.read_text(encoding="utf-8"))
    ref = transcript_obj.get("referenceTranscript", {}) if isinstance(transcript_obj, dict) else {}
    tokens_block = ref.get("tokens") if isinstance(ref, dict) else None
    decode_steps = (
        len(tokens_block.get("ids", []))
        if isinstance(tokens_block, dict) and isinstance(tokens_block.get("ids"), list)
        else 0
    )
    prompt_hash = ""
    prompt_block = ref.get("prompt") if isinstance(ref, dict) else None
    if isinstance(prompt_block, dict):
        raw_hash = prompt_block.get("hash", "")
        prompt_hash = raw_hash.split(":", 1)[1] if isinstance(raw_hash, str) and ":" in raw_hash else (raw_hash or "")

    manifest: dict = {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_manifest",
        "modelId": "qwen-3-6-27b-q4k-ehaf16",
        "rdrrVariant": "text-q4k-ehaf16",
        "promptText": args.prompt,
        "decodeSteps": decode_steps,
        "frozenAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frozenReason": args.frozen_reason,
        "fixtureDigest": fixture_digest,
        "transcript": transcript_entry,
        "activations": activations,
    }
    if prompt_hash and re.fullmatch(r"[0-9a-f]{64}", prompt_hash):
        manifest["tokenizedPromptHash"] = prompt_hash

    manifest_path = args.dst / "frozen-reference.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"wrote {manifest_path} fixtureDigest={fixture_digest[:16]}... "
        f"layers={len(layers)} probesPerLayer={len(probes)} "
        f"decodeSteps={decode_steps}"
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
