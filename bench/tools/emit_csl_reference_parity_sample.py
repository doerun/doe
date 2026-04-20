#!/usr/bin/env python3
"""Regenerate examples/doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json
from current artifact state.

The sample parity receipt is schema documentation: it shows what a valid
doe_csl_reference_parity receipt looks like. Hand-maintained samples
drift (the previous one still advertised `..._gelu_stub` long after the
kernel upgraded to poly_c1 + multi-pair rope). This tool derives the
sample mechanically from:

  - live execution manifest            (manifestSha256)
  - live stream execution plan graph   (graphSha256)
  - current synthetic trace            (referenceRun.output digest)
  - current smoke-trace                (cslRun.* fields)
  - live CSL source hash               (drift detection)

When the smoke-trace's kernelSourceSha256 drifts from the live kernel,
the generator records the drift in `comparison.blocker` so anyone
reading the sample sees the honest state instead of assuming a fresh
runner trace.

Run via: python3 bench/tools/emit_csl_reference_parity_sample.py

The parity gate at bench/gates/csl_reference_parity_gate.py validates
the emitted sample against the schema and its trace-consistency rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
GRAPH_PATH = "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json"
KERNEL_SOURCE_PATH = (
    "bench/out/streaming-executor/e2b-layer-block-source/"
    "transformer_layer_shape.csl"
)
SMOKE_TRACE_PATH = (
    "bench/out/streaming-executor/e2b-layer-block-smoke-trace.json"
)
SYNTHETIC_TRACE_PATH = (
    "bench/out/streaming-executor/e2b-layer-block-synthetic-trace.json"
)
DEFAULT_OUT = (
    "examples/"
    "doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json"
)
MODEL_ID = "gemma-4-e2b-it-text-q4k-ehf16-af32"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(rel: str) -> Path:
    return REPO_ROOT / rel


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


EXTERNAL_PRODUCERS = (
    "doppler_browser_webgpu",
    "doppler_node_webgpu",
    "doppler_exported_fixture",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument(
        "--smoke-trace-path",
        default=SMOKE_TRACE_PATH,
        help="Override for the CSL smoke-trace to bind as cslRun.* "
             "evidence. Defaults to the canonical 35-layer trace. Set "
             "to a per-layer (L=1) trace when binding a cross-runtime "
             "reference that only covers a single layer, so the comparison "
             "frame matches.",
    )
    p.add_argument(
        "--external-reference-output",
        default="",
        help="Path to a Doppler-emitted f32 reference output vector. "
             "When provided, referenceRun.producer swaps to "
             "--external-reference-producer (default "
             "doppler_exported_fixture), inputs/weightsSynthetic "
             "flip to false, and promotionCriteria."
             "externalReferenceOutputBound flips true. When empty "
             "(default), the sample uses the in-loop numpy "
             "synthetic trace as the reference producer.",
    )
    p.add_argument(
        "--external-reference-producer",
        default="doppler_exported_fixture",
        choices=EXTERNAL_PRODUCERS,
        help="Producer enum for the external reference. Ignored "
             "unless --external-reference-output is set.",
    )
    p.add_argument(
        "--atol",
        type=float,
        default=None,
        help="Absolute-tolerance threshold for tolerance-based "
             "cross-runtime parity. When set, the generated receipt "
             "populates comparison.atol and comparison.maxAbsErr is "
             "computed element-wise between referenceRun.output and "
             "cslRun.output. comparison.status flips to 'passed' iff "
             "maxAbsErr <= atol. Use this when the reference is non-"
             "bit-exact to scalar f32 (Doppler WebGPU: driver FMA, "
             "vectorized reductions, platform sqrt). Validate the "
             "resulting receipt with "
             "`csl_reference_parity_gate.py --require-tolerance-"
             "parity`. Leave unset for bit-exact sha256 parity "
             "(validated via --require-output-parity).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_path = resolve(args.out)

    manifest_path = resolve(MANIFEST_PATH)
    graph_path = resolve(GRAPH_PATH)
    kernel_path = resolve(KERNEL_SOURCE_PATH)
    smoke_trace_path = resolve(args.smoke_trace_path)
    synthetic_trace_path = resolve(SYNTHETIC_TRACE_PATH)

    for label, p in [
        ("manifest", manifest_path),
        ("graph", graph_path),
        ("kernel", kernel_path),
        ("smoke trace", smoke_trace_path),
        ("synthetic trace", synthetic_trace_path),
    ]:
        if not p.is_file():
            print(f"ERROR: {label} missing at {p}")
            return 2

    live_kernel_sha = sha256_file(kernel_path)
    smoke_trace = load_json(smoke_trace_path)
    synthetic_trace = load_json(synthetic_trace_path)
    manifest = load_json(manifest_path)
    manifest_num_layers = int(
        (manifest.get("modelConfig") or {}).get("numLayers") or 0
    )

    smoke_layer = smoke_trace.get("layerBlockSmoke", {}) or {}
    smoke_run = smoke_trace.get("executedRun", {}) or {}
    smoke_parity = smoke_run.get("numericalParity", {}) or {}
    smoke_trace_kernel_sha = smoke_layer.get("kernelSourceSha256")
    runner_is_stale = (
        smoke_trace_kernel_sha is not None
        and smoke_trace_kernel_sha != live_kernel_sha
    )

    syn_output = (synthetic_trace.get("executedRun", {}) or {}).get("output") or {}

    smoke_output = smoke_run.get("output") or {}
    csl_run: dict[str, Any] = {
        "tracePath": args.smoke_trace_path,
        "traceSha256": sha256_file(smoke_trace_path),
        "status": smoke_run.get("status", "unknown"),
        "kernelStage": smoke_layer.get("kernelStage", ""),
        "kernelIsStub": bool(smoke_layer.get("kernelIsStub", False)),
        "numericalParity": {
            "maxAbsErr": float(smoke_parity.get("maxAbsErr", 0) or 0),
            "atol": int(smoke_parity.get("atol", 0) or 0),
            "passed": bool(smoke_parity.get("passed", False)),
        },
    }
    if smoke_output.get("sha256"):
        csl_run["output"] = {
            "dtype": smoke_output.get("dtype", "float32"),
            "shape": smoke_output.get("shape", []),
            "path": smoke_output.get("path", ""),
            "sha256": smoke_output.get("sha256", ""),
        }

    external_ref_path_raw = args.external_reference_output.strip()
    external_output_bound = False
    if external_ref_path_raw:
        external_path = resolve(external_ref_path_raw)
        if not external_path.is_file():
            print(
                "ERROR: --external-reference-output path missing: "
                + external_ref_path_raw
            )
            return 2
        external_output_bound = True
        reference_run = {
            "producer": args.external_reference_producer,
            "status": "output_ready",
            "inputsSynthetic": False,
            "weightsSynthetic": False,
            "output": {
                "dtype": "float32",
                "path": external_ref_path_raw,
                "sha256": sha256_file(external_path),
            },
        }
    else:
        reference_run = {
            "producer": "numpy_reference",
            "status": "metadata_bound",
            "inputsSynthetic": True,
            "weightsSynthetic": True,
        }
        if syn_output.get("sha256"):
            reference_run["output"] = {
                "dtype": syn_output.get("dtype", "float32"),
                "shape": syn_output.get("shape", []),
                "path": syn_output.get("path", ""),
                "sha256": syn_output.get("sha256", ""),
            }

    csl_output_bound = bool(smoke_output.get("sha256"))
    # fullModelDepthExecuted: true iff the runner chained all
    # manifest-declared layers (35 for E2B) with status=succeeded
    # and its trace isn't stale against the live kernel. Flips
    # automatically when cs_python re-runs the current runner,
    # which defaults --num-layers to manifest.modelConfig.numLayers.
    smoke_num_layers = smoke_run.get("numLayersChained")
    smoke_status = smoke_run.get("status")
    full_model_depth_executed = bool(
        not runner_is_stale
        and manifest_num_layers > 0
        and smoke_num_layers == manifest_num_layers
        and smoke_status == "succeeded"
    )
    # Parity computation: two modes.
    #   - Bit-exact (default): both outputs present AND sha256 equal.
    #   - Tolerance (--atol): both outputs present AND element-wise
    #     max-abs-diff <= atol. Needed when the reference producer is
    #     non-bit-exact to scalar f32 (e.g. Doppler WebGPU driver FMA,
    #     vectorized reductions, platform sqrt). Paired with the gate's
    #     --require-tolerance-parity mode.
    ref_output_sha = (
        reference_run.get("output", {}) or {}
    ).get("sha256", "") or ""
    csl_output_sha = (smoke_output or {}).get("sha256", "") or ""
    ref_output_path = (
        reference_run.get("output", {}) or {}
    ).get("path", "") or ""
    csl_output_path = (smoke_output or {}).get("path", "") or ""

    tolerance_atol = args.atol  # None in bit-exact mode
    tolerance_max_abs_err = None
    if tolerance_atol is not None:
        import numpy as _np
        if not ref_output_path or not csl_output_path:
            print(
                "ERROR: --atol requires both referenceRun.output.path "
                "and cslRun.output.path to be present. Run the CSL "
                "runner first so the smoke-trace emits an output digest."
            )
            return 2
        ref_f32 = _np.fromfile(resolve(ref_output_path), dtype=_np.float32)
        csl_f32 = _np.fromfile(resolve(csl_output_path), dtype=_np.float32)
        if ref_f32.shape != csl_f32.shape:
            print(
                f"ERROR: reference shape {ref_f32.shape} != "
                f"CSL shape {csl_f32.shape}"
            )
            return 2
        tolerance_max_abs_err = float(_np.max(_np.abs(ref_f32 - csl_f32)))
        output_parity_passed = tolerance_max_abs_err <= tolerance_atol
    else:
        output_parity_passed = bool(
            ref_output_sha
            and csl_output_sha
            and ref_output_sha == csl_output_sha
        )
    blocker_parts: list[str] = []
    if runner_is_stale:
        blocker_parts.append(
            "smoke-trace kernelSourceSha256 "
            f"({(smoke_trace_kernel_sha or '')[:16]}) drifted from live "
            f"kernel ({live_kernel_sha[:16]}) — rerun "
            "bench/runners/csl-runners/e2b_layer_block_smoke.py on a "
            "cs_python-equipped host to refresh"
        )
    if not csl_output_bound:
        blocker_parts.append(
            "cslRun.output digest not bound (runner trace predates the "
            "output-digest emission)"
        )
    if not external_output_bound:
        blocker_parts.append(
            "external Doppler/browser output vector not bound yet "
            "(pass --external-reference-output to bind one)"
        )
    blocker = "; ".join(blocker_parts) if blocker_parts else ""

    comparison_status = "metadata_bound"
    if csl_output_bound and not runner_is_stale:
        comparison_status = "pending_csl_output_hash"
    if output_parity_passed:
        comparison_status = "passed"

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_reference_parity",
        "modelId": MODEL_ID,
        "sourceProgram": {
            "authoringSurface": "doppler_execution_v1",
            "manifestPath": MANIFEST_PATH,
            "manifestSha256": sha256_file(manifest_path),
            "graphPath": GRAPH_PATH,
            "graphSha256": sha256_file(graph_path),
            "weightSetId": "synthetic-layer-block-smoke",
        },
        "referenceRun": reference_run,
        "cslRun": csl_run,
        "comparison": ({
            "status": comparison_status,
            "sameManifestHash": True,
            "sameGraphHash": True,
            "outputHashMatch": output_parity_passed if tolerance_atol is None else False,
            "blocker": blocker,
        } | (
            {"atol": tolerance_atol, "maxAbsErr": tolerance_max_abs_err}
            if tolerance_atol is not None
            else {}
        )),
        "promotionCriteria": {
            "fullModelDepthExecuted": full_model_depth_executed,
            "manifestHashMatched": True,
            "graphHashMatched": True,
            "weightHashMatched": False,
            "externalReferenceOutputBound": external_output_bound,
            "cslOutputHashBound": csl_output_bound,
            "outputParityPassed": output_parity_passed,
            "stubStagesAbsent": not bool(
                smoke_layer.get("kernelIsStub", False)
            ),
            "syntheticInputsAbsent": external_output_bound,
            "syntheticWeightsAbsent": external_output_bound,
            "hardwareReceiptRequiredForHardwareClaim": True,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    try:
        rel = str(out_path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(out_path)
    print(
        "wrote " + rel
        + f"  runnerStale={runner_is_stale}"
        + f"  cslOutputBound={csl_output_bound}"
        + f"  externalOutputBound={external_output_bound}"
        + f"  comparison.status={comparison_status!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
