#!/usr/bin/env python3
"""Unified Doe entrypoint: Doppler bundle -> Doe IR/HostPlan -> target backend.

Roadmap item #2 ("unify Doe entrypoint"). Single command that takes a
Doppler-authored execution bundle and dispatches to one of five target
backends, emitting a standardized per-target receipt so a demo page or
CI gate can reason about target identity the same way for every lane.

Targets:

  webgpu-wgsl            browser/Node WebGPU compute shader running the
                         Doppler-equivalent WGSL layer-block
  doe-metal              Doe's own Metal backend running the WGSL shader
                         (Doe's WebGPU implementation, not Chrome's)
  doe-vulkan             Doe's own Vulkan backend running the WGSL
  csl-sdklayout          Cerebras SDK simfabric via cs_python
  csl-webgpu-emulator    WebGPU-based CSL semantic emulator (item #6)
                         — maps CSL streams/PE memory/colors/task phases
                         to WGSL buffers/storage/channels/compute passes.

Each target is either REAL today or STUB (not yet implemented). The
stub targets report `status=unsupported` and name the artifact that
needs to land. Real targets dispatch to existing tools.

Usage:

  python3 bench/tools/doe_run.py --target csl-sdklayout --num-layers 1
  python3 bench/tools/doe_run.py --target webgpu-wgsl --num-layers 1
  python3 bench/tools/doe_run.py --target doe-metal   # STUB
  python3 bench/tools/doe_run.py --list-targets

Output: JSON receipt written to
  bench/out/doe-run/<target>/L<N>-receipt.json

The receipt shape is target-agnostic so the demo page can render every
lane from the same field set: { target, modelId, manifestSha256,
graphSha256, numLayers, status, outputSha256, outputPath, elapsedMs,
runtimeMetadata, artifactPaths }.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BUNDLE = {
    "manifest": "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
    "graph": "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
}


@dataclass(frozen=True)
class Target:
    name: str
    description: str
    is_real: bool
    stub_note: str = ""


TARGETS: dict[str, Target] = {
    "webgpu-wgsl": Target(
        name="webgpu-wgsl",
        description="Node+WebGPU via Dawn (browser-equivalent Doppler path)",
        is_real=True,
    ),
    "doe-metal": Target(
        name="doe-metal",
        description="Doe's own Metal WebGPU backend",
        is_real=False,
        stub_note=(
            "Doe has a Metal backend at packages/doe-gpu/, but it does "
            "not yet load and dispatch this specific WGSL layer-block "
            "shader through a governed entrypoint. Item #4 on the "
            "roadmap wires this path."
        ),
    ),
    "doe-vulkan": Target(
        name="doe-vulkan",
        description="Doe's own Vulkan WebGPU backend",
        is_real=False,
        stub_note=(
            "Doe has a Vulkan backend; same gap as doe-metal for this "
            "shader. Item #4 on the roadmap wires this path."
        ),
    ),
    "csl-sdklayout": Target(
        name="csl-sdklayout",
        description="Cerebras SDK simfabric via cs_python",
        is_real=True,
    ),
    "csl-webgpu-emulator": Target(
        name="csl-webgpu-emulator",
        description=(
            "WebGPU-based CSL semantic emulator (streams->buffers, "
            "PE memory->storage, colors->channels, task phases->passes)"
        ),
        is_real=False,
        stub_note=(
            "Roadmap item #6. Not yet implemented. Entry point will be "
            "a new WGSL module + Python host that consumes the "
            "execution graph directly, not just the transformer layer-"
            "block kernel."
        ),
    ),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def base_receipt(target: str, bundle: dict, num_layers: int) -> dict:
    manifest_path = resolve(bundle["manifest"])
    graph_path = resolve(bundle["graph"])
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_target_run_receipt",
        "target": target,
        "targetDescription": TARGETS[target].description,
        "numLayers": num_layers,
        "bundle": {
            "manifestPath": bundle["manifest"],
            "manifestSha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
            "graphPath": bundle["graph"],
            "graphSha256": sha256_file(graph_path) if graph_path.is_file() else None,
        },
    }


def run_csl_sdklayout(bundle: dict, num_layers: int, out_dir: Path) -> dict:
    sdk = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    cs_python = os.environ.get("DOE_CSL_CS_PYTHON", f"{sdk}/cs_python")
    if not Path(cs_python).exists() and cs_python != "cs_python":
        return {
            "status": "blocked",
            "error": f"cs_python not found at {cs_python}",
            "blocker": "cs_python_not_available",
        }
    trace_path = out_dir / "trace.json"
    compile_out = out_dir / "compile"
    compile_out.mkdir(parents=True, exist_ok=True)
    command = [
        cs_python,
        "bench/runners/csl-runners/e2b_layer_block_smoke.py",
        "--num-layers", str(num_layers),
        "--compile-out", str(compile_out.relative_to(REPO_ROOT))
        if compile_out.is_relative_to(REPO_ROOT) else str(compile_out),
        "--trace-out", str(trace_path.relative_to(REPO_ROOT))
        if trace_path.is_relative_to(REPO_ROOT) else str(trace_path),
    ]
    proc = subprocess.run(
        command, cwd=REPO_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=900, check=False,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "returnCode": proc.returncode,
            "stderrTail": proc.stderr[-800:],
        }
    if not trace_path.is_file():
        return {"status": "failed", "error": "trace not written"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    er = trace.get("executedRun", {}) or {}
    out = er.get("output") or {}
    return {
        "status": er.get("status", "unknown"),
        "elapsedMs": er.get("elapsedMs"),
        "outputPath": out.get("path"),
        "outputSha256": out.get("sha256"),
        "tracePath": str(trace_path.relative_to(REPO_ROOT))
        if trace_path.is_relative_to(REPO_ROOT) else str(trace_path),
        "runtimeMetadata": {
            "kernelSourceSha256": (trace.get("layerBlockSmoke") or {}).get("kernelSourceSha256"),
        },
    }


def run_webgpu_wgsl(bundle: dict, num_layers: int, out_dir: Path) -> dict:
    node = os.environ.get("DOE_NODE", "node")
    if not subprocess.run(["which", node], capture_output=True).stdout:
        return {"status": "blocked", "error": f"node ('{node}') not on PATH"}
    seeds = ["1000"] + [str(2000 + l) for l in range(num_layers)]
    prep = subprocess.run(
        ["python3", "bench/tools/doppler_prepare_webgpu_inputs.py",
         "--size", "1024", "--seeds"] + seeds,
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if prep.returncode != 0:
        return {"status": "failed", "error": f"input-fixture prep failed: {prep.stderr[-400:]}"}
    webgpu_out = out_dir / "webgpu"
    webgpu_out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [node, "bench/tools/doppler_webgpu_reference_export.cjs",
         "--manifest", bundle["manifest"],
         "--graph", bundle["graph"],
         "--size", "1024",
         "--num-layers", str(num_layers),
         "--initial-rows-seed", "1000",
         "--per-layer-base", "2000",
         "--out-dir", str(webgpu_out.relative_to(REPO_ROOT))
         if webgpu_out.is_relative_to(REPO_ROOT) else str(webgpu_out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
        timeout=900, check=False,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "returnCode": proc.returncode,
            "stderrTail": proc.stderr[-800:],
        }
    rec_path = webgpu_out / "export_receipt.json"
    if not rec_path.is_file():
        return {"status": "failed", "error": "WebGPU export receipt not written"}
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    return {
        "status": "succeeded",
        "elapsedMs": rec.get("elapsedMs"),
        "outputPath": rec.get("outputPath"),
        "outputSha256": rec.get("outputSha256"),
        "tracePath": str(rec_path.relative_to(REPO_ROOT))
        if rec_path.is_relative_to(REPO_ROOT) else str(rec_path),
        "runtimeMetadata": {
            "adapter": rec.get("adapterInfo"),
            "stagesCovered": rec.get("stagesCovered"),
        },
    }


def run_stub(target: str, bundle: dict, num_layers: int, out_dir: Path) -> dict:
    return {
        "status": "unsupported",
        "blocker": TARGETS[target].stub_note,
        "roadmapItem": {
            "doe-metal": 4,
            "doe-vulkan": 4,
            "csl-webgpu-emulator": 6,
        }.get(target),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--target",
        choices=list(TARGETS.keys()) + ["all"],
        default=None,
    )
    p.add_argument(
        "--num-layers",
        type=int,
        default=1,
    )
    p.add_argument(
        "--manifest",
        default=DEFAULT_BUNDLE["manifest"],
    )
    p.add_argument(
        "--graph",
        default=DEFAULT_BUNDLE["graph"],
    )
    p.add_argument(
        "--out-dir",
        default="bench/out/doe-run",
    )
    p.add_argument(
        "--list-targets",
        action="store_true",
        help="Print the target table and exit.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_targets:
        print(f"{'target':<22} {'real?':<5} description")
        for t in TARGETS.values():
            marker = "yes" if t.is_real else "stub"
            print(f"  {t.name:<20} {marker:<5} {t.description}")
        return 0
    if args.target is None:
        print("ERROR: --target required (or --list-targets). Choices: "
              + ", ".join(TARGETS.keys()) + ", all")
        return 2
    bundle = {"manifest": args.manifest, "graph": args.graph}
    targets_to_run = list(TARGETS.keys()) if args.target == "all" else [args.target]
    for target in targets_to_run:
        out_dir = resolve(args.out_dir) / target
        out_dir.mkdir(parents=True, exist_ok=True)
        receipt = base_receipt(target, bundle, args.num_layers)
        if target == "csl-sdklayout":
            receipt.update(run_csl_sdklayout(bundle, args.num_layers, out_dir))
        elif target == "webgpu-wgsl":
            receipt.update(run_webgpu_wgsl(bundle, args.num_layers, out_dir))
        else:
            receipt.update(run_stub(target, bundle, args.num_layers, out_dir))
        rec_path = out_dir / f"L{args.num_layers}-receipt.json"
        rec_path.write_text(json.dumps(receipt, indent=2) + "\n")
        marker = {
            "succeeded": "OK",
            "unsupported": "STUB",
            "blocked": "BLOCKED",
            "failed": "FAIL",
        }.get(receipt.get("status", ""), receipt.get("status", "?"))
        print(f"  [{marker:<8}] {target:<22} -> {rec_path.relative_to(REPO_ROOT)}")
        if receipt.get("outputSha256"):
            print(f"             output.sha256: {receipt['outputSha256'][:16]}...")
        elif receipt.get("blocker"):
            print(f"             blocker: {str(receipt['blocker'])[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
