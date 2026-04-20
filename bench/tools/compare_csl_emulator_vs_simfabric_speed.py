#!/usr/bin/env python3
"""CSL WebGPU emulator vs simfabric speed compare (roadmap item #8).

Both sides are LOCAL correctness/debug paths. This tool reports the
wall-time ratio of the CSL WebGPU emulator against the CSL simfabric
runner at matched chain depth and matched program identity. It emits a
verdict artifact whose framing is deliberately narrow:

  - claim: "emulator is Nx faster than local CSL simfabric on the same
    host, at this chain depth, on this program"
  - NOT a claim: "faster than Cerebras hardware"
  - NOT a claim: "faster than Cerebras WSE"
  - NOT a claim: "faster than real simfabric on real Cerebras SDK
    installations outside this host"

Matching discipline:
  - numLayers must match between emulator export_receipt and CSL trace.
  - manifest/graph SHA256s, where recorded on both sides, must match;
    otherwise the comparison is tagged `programIdentityMatched=false`
    and the verdict is advisory, not claimable.

Usage:
  python3 bench/tools/compare_csl_emulator_vs_simfabric_speed.py \\
    --csl-trace bench/out/streaming-executor/e2b-layer-block-smoke-trace.json \\
    --emulator-receipt bench/out/doppler-reference/gemma-4-e2b-layer-block-webgpu-isolated/export_receipt.json \\
    --out-json bench/out/doppler-reference/csl-emulator-speed-verdict-L35.json

Exit 0 when both elapsedMs values are present, depth matches, and the
verdict artifact was written. Exit 1 on any contract failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--csl-trace", required=True,
        help="Path to CSL runner trace (doe_streaming_executor_trace).",
    )
    p.add_argument(
        "--emulator-receipt", required=True,
        help="Path to emulator export_receipt.json (doppler_reference_export).",
    )
    p.add_argument(
        "--out-json", default="",
        help="Optional path for machine-readable speed verdict artifact.",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    csl_path = resolve(args.csl_trace)
    emu_path = resolve(args.emulator_receipt)

    if not csl_path.is_file():
        print(f"FAIL: CSL trace missing: {args.csl_trace}")
        return 1
    if not emu_path.is_file():
        print(f"FAIL: emulator receipt missing: {args.emulator_receipt}")
        return 1

    csl = json.loads(csl_path.read_text(encoding="utf-8"))
    emu = json.loads(emu_path.read_text(encoding="utf-8"))

    executed = csl.get("executedRun", {}) or {}
    csl_elapsed_ms = executed.get("elapsedMs")
    csl_num_layers = executed.get("numLayersChained")
    csl_per_layer = executed.get("perLayerElapsedMs") or []
    csl_status = executed.get("status", "unknown")

    emu_elapsed_ms = emu.get("elapsedMs")
    emu_num_layers = emu.get("numLayers")

    if csl_status != "succeeded":
        print(f"FAIL: CSL trace executedRun.status={csl_status}, cannot compare timing.")
        return 1
    if csl_elapsed_ms is None:
        print("FAIL: CSL trace missing executedRun.elapsedMs.")
        return 1
    if emu_elapsed_ms is None:
        print("FAIL: emulator receipt missing elapsedMs.")
        return 1
    if csl_num_layers is None or emu_num_layers is None:
        print(
            f"FAIL: missing numLayers — csl={csl_num_layers}, emu={emu_num_layers}."
        )
        return 1
    if int(csl_num_layers) != int(emu_num_layers):
        print(
            f"FAIL: chain depth mismatch — csl.numLayersChained={csl_num_layers} "
            f"vs emulator.numLayers={emu_num_layers}. A speed comparison at "
            f"unmatched depth is not meaningful."
        )
        return 1

    emu_manifest = emu.get("manifestSha256")
    emu_graph = emu.get("graphSha256")

    layer_block_smoke = csl.get("layerBlockSmoke") or {}
    csl_graph = layer_block_smoke.get("planSha256") or csl.get("graphSha256")
    csl_manifest = csl.get("manifestSha256")
    source_model_receipt_rel = layer_block_smoke.get("sourceModelReceiptPath")
    if not csl_manifest and source_model_receipt_rel:
        receipt_path = resolve(source_model_receipt_rel)
        if receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                csl_manifest = (
                    (receipt.get("artifactHashes") or {})
                    .get("executionManifest", {})
                    .get("sha256")
                )
            except (OSError, ValueError):
                csl_manifest = None

    manifest_matched = bool(emu_manifest) and bool(csl_manifest) and emu_manifest == csl_manifest
    graph_matched = bool(emu_graph) and bool(csl_graph) and emu_graph == csl_graph

    program_identity_matched = manifest_matched and graph_matched

    speedup = float(csl_elapsed_ms) / float(emu_elapsed_ms) if emu_elapsed_ms > 0 else None
    per_layer_records = []
    if csl_per_layer and emu_elapsed_ms > 0:
        for i, ms in enumerate(csl_per_layer):
            try:
                ms_f = float(ms)
            except (TypeError, ValueError):
                ms_f = None
            if ms_f is None:
                continue
            per_layer_records.append({
                "layer": i,
                "cslSimfabricMs": ms_f,
                "cslSimfabricToEmulatorWholeRunRatio": ms_f / float(emu_elapsed_ms),
            })

    verdict = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_emulator_speed_verdict",
        "modelId": csl.get("modelId", "unknown"),
        "numLayers": int(csl_num_layers),
        "cslTracePath": rel(csl_path),
        "emulatorReceiptPath": rel(emu_path),
        "cslSimfabricElapsedMs": float(csl_elapsed_ms),
        "emulatorElapsedMs": float(emu_elapsed_ms),
        "emulatorSpeedupOverLocalSimfabric": speedup,
        "programIdentity": {
            "cslManifestSha256": csl_manifest,
            "emulatorManifestSha256": emu_manifest,
            "manifestMatched": manifest_matched,
            "cslGraphSha256": csl_graph,
            "emulatorGraphSha256": emu_graph,
            "graphMatched": graph_matched,
            "programIdentityMatched": program_identity_matched,
        },
        "perLayer": per_layer_records,
        "claimScope": {
            "claimable": (
                "emulator wall-time is lower than local CSL simfabric wall-time "
                "on this host for this program at this chain depth"
            ),
            "notClaimable": [
                "faster than Cerebras hardware (WSE/WSC)",
                "faster than Cerebras SDK installations on other hosts",
                "general-purpose performance claim beyond this local debug path",
            ],
            "rationale": (
                "Both sides are local correctness/debug runtimes. The emulator "
                "runs WGSL compute on a local GPU; the simfabric runner runs "
                "Cerebras SDK simfabric on CPU. A ratio between them measures "
                "debug-path ergonomics, not hardware performance."
            ),
        },
        "verdict": (
            "claimable_local_debug_speedup" if program_identity_matched and speedup and speedup > 1.0
            else "advisory_local_debug_speedup" if speedup and speedup > 1.0
            else "no_speedup_detected"
        ),
    }

    if args.out_json:
        out_path = resolve(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {rel(out_path)}")

    identity_tag = (
        "program_identity_matched"
        if program_identity_matched
        else "program_identity_not_confirmed"
    )
    if speedup is None:
        print("FAIL: could not compute speedup ratio (emulator elapsed <= 0?).")
        return 1
    print(
        f"emulator/simfabric local-debug speed: "
        f"csl_simfabric={csl_elapsed_ms:.1f} ms, "
        f"emulator={emu_elapsed_ms:.1f} ms, "
        f"speedup={speedup:.1f}x @ L={csl_num_layers} ({identity_tag}). "
        f"NOT a Cerebras hardware claim."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
