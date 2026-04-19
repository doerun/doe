#!/usr/bin/env python3
"""Build a model-level runtime receipt binding manifest, host-plan, memory-plan,
runtime-config, and per-kernel CSL runtime-ready evidence into one artifact.

This is the unit that answers 'can Doe run this model end-to-end' for
Gemma 4 E2B and structurally the same shape that 31B will extend with a
streaming runtime path.

Inputs:
  --execution-manifest  path to execution-v1 manifest (gemma-4-e2b-smoke.json)
  --host-plan           path to host-plan.json produced by doe-csl-host-plan-tool
  --memory-plan         path to memory-plan.json
  --runtime-config      path to runtime-config.json
  --simulator-plan      path to simulator-plan.json
  --registry            path to config/csl-runtime-fixtures.json

Output:
  A JSON receipt artifact with:
    - modelId, modelConfig, gridDims, peCount
    - artifact SHA-256 for every input above
    - per-kernel resolution: classifier pattern, fixture id if any, runtime status
    - WGSL source path + sha256 for every kernel that has one
    - CSL compile evidence path + sha256 for every kernel with compiled ELFs
    - kernelCoverage: ready / compile_only / missing counts
    - fits: memory-plan.fits boolean
    - residencyMode: from memory-plan
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--execution-manifest", required=True)
    p.add_argument("--host-plan", required=True)
    p.add_argument("--memory-plan", required=True)
    p.add_argument("--runtime-config", required=True)
    p.add_argument("--simulator-plan", required=True)
    p.add_argument("--registry", default="config/csl-runtime-fixtures.json")
    p.add_argument(
        "--chain-parity-receipt",
        action="append",
        default=[],
        help=(
            "Path to a doe_kernel_chain_parity receipt to bind as model-level "
            "execution evidence. May repeat. Only chains whose kernel patterns "
            "intersect this model's host-plan patterns count toward coverage."
        ),
    )
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-md", default="")
    return p.parse_args()


def build_kernel_indices(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index fixtures by (a) fixture id and (b) classifier pattern (first fixture per pattern wins)."""
    by_id: dict[str, dict[str, Any]] = {}
    by_pattern: dict[str, dict[str, Any]] = {}
    for fix in registry.get("fixtures", []):
        fixture_id = fix.get("id")
        if fixture_id:
            by_id[fixture_id] = fix
        pattern = fix.get("kernelPattern")
        if pattern and pattern not in by_pattern:
            by_pattern[pattern] = fix
    return by_id, by_pattern


def derive_streaming_migration(memory_plan: dict[str, Any], model_config: dict[str, Any]) -> dict[str, Any]:
    """Compute streaming-runtime migration fields from the existing memory plan.

    The memcpy RPC runtime ('mode: sdk-runtime-command' in runtime-config.json)
    works when the steady-state per-PE working set fits comfortably in SRAM.
    Beyond that, the SdkLayout streaming runtime is required — code regions,
    ports, streams, async send/receive, demux/mux — to overlap weight prefetch
    with compute via double-buffering, and to spill KV cache off-PE.

    This derivation flags when each condition kicks in so the model receipt
    makes the priority #6 migration boundary explicit without requiring the
    schema itself to track every streaming-runtime knob upfront.
    """
    per_pe_budget = int(memory_plan.get("totalSramAvailable", 0))
    pe_count = int(memory_plan.get("peCount", 1)) or 1
    per_pe_sram = per_pe_budget // pe_count if pe_count else 0

    persistent_per_pe = int(memory_plan.get("persistentBytesPerPe", 0))
    streamed_working_set_per_pe = int(memory_plan.get("streamedWorkingSetBytesPerPe", 0))

    # Double-buffered streaming needs two layers worth of streamed weights
    # in residence so prefetch can overlap compute. The steady-state payload
    # lives in stages with repeatCount > 1 (they run once per transformer
    # layer). One-shot stages like embedding_rows (repeatCount == 1) are
    # loaded once at model init and don't need double-buffering.
    stages = memory_plan.get("streamStages", [])
    max_stage_per_pe = 0
    max_stage_name = ""
    max_setup_stage_per_pe = 0
    max_setup_stage_name = ""
    for s in stages:
        v = int(s.get("bytesPerPe", 0))
        repeat = int(s.get("repeatCount", 1))
        if repeat > 1:
            if v > max_stage_per_pe:
                max_stage_per_pe = v
                max_stage_name = str(s.get("name", ""))
        else:
            if v > max_setup_stage_per_pe:
                max_setup_stage_per_pe = v
                max_setup_stage_name = str(s.get("name", ""))

    double_buffered_working_set_per_pe = persistent_per_pe + 2 * max_stage_per_pe
    double_buffered_fits = double_buffered_working_set_per_pe <= per_pe_sram

    num_layers = int(model_config.get("numLayers", 0))
    # All transformer layers share the same compile shape, so N layers fold
    # to at most 1 distinct ELF per kernel pattern per pipeline phase. The
    # compile-artifact cache boundary is the hash(compileParams) that the
    # streaming runtime uses to avoid re-compiling layer N when its shape
    # equals layer N-1's.
    distinct_layer_shape_count = 1 if num_layers > 0 else 0

    # KV cache residency: if kv_cache per-PE exceeds (per_pe_sram minus
    # double-buffered working set) the streaming runtime must spill KV to
    # host DRAM or partition across more PEs.
    kv_per_pe = 0
    for b in memory_plan.get("buffers", []):
        if b.get("kind") == "kv_cache":
            kv_per_pe = int(b.get("bytesPerPe", 0))
            break

    headroom_per_pe = per_pe_sram - persistent_per_pe - streamed_working_set_per_pe

    # Streaming runtime becomes required when the simple memcpy RPC path
    # can't keep up — that's when double-buffering needs more than current
    # headroom, or when the working set alone saturates SRAM.
    streaming_runtime_required = (
        not double_buffered_fits
        or streamed_working_set_per_pe > per_pe_sram // 2
    )

    return {
        "perPeSramBudget": per_pe_sram,
        "persistentBytesPerPe": persistent_per_pe,
        "streamedWorkingSetBytesPerPe": streamed_working_set_per_pe,
        "headroomBytesPerPe": headroom_per_pe,
        "kvCacheBytesPerPe": kv_per_pe,
        "maxPerLayerStage": {
            "name": max_stage_name,
            "bytesPerPe": max_stage_per_pe,
        },
        "maxSetupStage": {
            "name": max_setup_stage_name,
            "bytesPerPe": max_setup_stage_per_pe,
        },
        "doubleBufferedWorkingSetPerPe": double_buffered_working_set_per_pe,
        "doubleBufferedFits": double_buffered_fits,
        "numTransformerLayers": num_layers,
        "distinctLayerCompileShapes": distinct_layer_shape_count,
        "compileArtifactReuseFactor": (num_layers // distinct_layer_shape_count) if distinct_layer_shape_count else 0,
        "streamingRuntimeRequired": streaming_runtime_required,
        "runtimePath": "sdk_layout_streaming" if streaming_runtime_required else "memcpy_rpc",
        "notes": (
            "memcpy_rpc: current sdk-runtime-command runtime path works when "
            "single-copy working set fits AND per-layer double-buffer fits. "
            "sdk_layout_streaming: required when per-layer weight prefetch needs "
            "overlap with compute or KV cache must spill — priority #6."
        ),
    }


def resolve_kernel_evidence(
    kernel: dict[str, Any],
    id_index: dict[str, dict[str, Any]],
    pattern_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pattern = kernel.get("pattern", "")
    name = kernel.get("name", "")
    # Prefer a fixture whose id matches the kernel name (handles gelu vs elementwise-double
    # where both are element_wise classifier but represent distinct numerical kernels);
    # fall back to pattern match for kernels whose names are phase-specific (e.g. "rmsnorm"
    # → reduce-sum-workgroup fixture via the reduction pattern).
    fixture = id_index.get(name) or pattern_index.get(pattern)
    entry: dict[str, Any] = {
        "name": name,
        "pattern": pattern,
        "count": kernel.get("count", 1),
    }
    if fixture is None:
        entry["runtimeStatus"] = "missing"
        entry["reason"] = f"no runtime fixture registered for pattern={pattern!r}"
        return entry

    entry["runtimeStatus"] = fixture.get("governedStatus", "unknown")
    entry["fixtureId"] = fixture.get("id", "")
    if "reduceStrategy" in fixture:
        entry["reduceStrategy"] = fixture["reduceStrategy"]
    evidence = fixture.get("evidence", {})
    for k in (
        "sourceWgslPath",
        "sourceEvidenceDir",
        "governedLaneReportPath",
        "tracePath",
    ):
        if k in evidence:
            entry[k] = evidence[k]
            abs_path = resolve(evidence[k])
            if abs_path.is_file():
                entry[f"{k}Sha256"] = sha256_file(abs_path)
            elif abs_path.is_dir():
                entry[f"{k}Exists"] = True
    return entry


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.execution_manifest)
    host_plan_path = resolve(args.host_plan)
    memory_plan_path = resolve(args.memory_plan)
    runtime_config_path = resolve(args.runtime_config)
    simulator_plan_path = resolve(args.simulator_plan)
    registry_path = resolve(args.registry)

    manifest = load_json(manifest_path)
    host_plan = load_json(host_plan_path)
    memory_plan = load_json(memory_plan_path)
    runtime_config = load_json(runtime_config_path)
    registry = load_json(registry_path)

    id_index, pattern_index = build_kernel_indices(registry)
    kernels = host_plan["hostPlan"]["kernels"]
    kernel_entries = [resolve_kernel_evidence(k, id_index, pattern_index) for k in kernels]

    coverage_counts: dict[str, int] = {}
    for entry in kernel_entries:
        status = entry["runtimeStatus"]
        coverage_counts[status] = coverage_counts.get(status, 0) + 1

    grid = host_plan["hostPlan"]["peGrid"]
    pe_count = int(grid["width"]) * int(grid["height"])

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_model_runtime_receipt",
        "target": "wse3",
        "modelId": manifest.get("modelId", ""),
        "modelFamily": manifest.get("modelFamily", ""),
        "modelConfig": manifest.get("modelConfig", {}),
        "grid": {"width": int(grid["width"]), "height": int(grid["height"]), "peCount": pe_count},
        "residencyMode": memory_plan.get("residencyMode", "unknown"),
        "fits": bool(memory_plan.get("fits", False)),
        "memorySummary": {
            "totalModelBytes": int(memory_plan.get("totalModelBytes", 0)),
            "totalPersistentBytes": int(memory_plan.get("totalPersistentBytes", 0)),
            "totalStreamedBytes": int(memory_plan.get("totalStreamedBytes", 0)),
            "totalSramAvailable": int(memory_plan.get("totalSramAvailable", 0)),
            "utilizationPct": int(memory_plan.get("utilizationPct", 0)),
        },
        "artifactHashes": {
            "executionManifest": {"path": rel(manifest_path), "sha256": sha256_file(manifest_path)},
            "hostPlan": {"path": rel(host_plan_path), "sha256": sha256_file(host_plan_path)},
            "memoryPlan": {"path": rel(memory_plan_path), "sha256": sha256_file(memory_plan_path)},
            "runtimeConfig": {"path": rel(runtime_config_path), "sha256": sha256_file(runtime_config_path)},
            "simulatorPlan": {"path": rel(simulator_plan_path), "sha256": sha256_file(simulator_plan_path)},
            "cslRuntimeFixtureRegistry": {"path": rel(registry_path), "sha256": sha256_file(registry_path)},
        },
        "kernels": kernel_entries,
        "kernelCoverage": {
            "total": len(kernel_entries),
            "byStatus": coverage_counts,
            "patternsCovered": sorted({e["pattern"] for e in kernel_entries if e["runtimeStatus"] == "runtime_ready"}),
            "patternsMissing": sorted({e["pattern"] for e in kernel_entries if e["runtimeStatus"] == "missing"}),
        },
        "phaseSummary": {
            "prefillLaunches": len(host_plan["hostPlan"].get("phases", {}).get("prefill", [])),
            "decodeLaunches": len(host_plan["hostPlan"].get("phases", {}).get("decode", [])),
        },
        "streamingMigration": derive_streaming_migration(memory_plan, manifest.get("modelConfig", {})),
    }

    streaming_required = receipt["streamingMigration"]["streamingRuntimeRequired"]
    fits = receipt["fits"]
    missing_kernels = coverage_counts.get("missing", 0) != 0

    # Blocker priority — structural gaps fail fast, executor gaps next,
    # then compile, then hardware. Each step presumes the earlier ones
    # cleared. Once full-grid cslc succeeds and the streaming executor
    # exists, only hardware_endpoint_unavailable remains.
    pe_count = int(receipt["grid"]["peCount"])
    # cslc's SDK memcpy module declares width as i16 — grids above 32,767
    # PEs can't compile as a 1D rectangle. 2D rectangles where each axis
    # stays under 32k (e.g., 31B's 246x236) work in theory; the emitter
    # doesn't emit 2D layouts yet, so flag the blocker explicitly.
    grid_width = int(receipt["grid"]["width"])
    grid_height = int(receipt["grid"]["height"])
    i16_max = 32767
    grid_fits_single_memcpy = grid_width <= i16_max and grid_height <= i16_max
    # For E2B (149x117, both <= i16) and 31B (246x236, both <= i16) the
    # per-axis test passes. The PE-COUNT overflow only affects 1D-flattened
    # layouts, which is the elementwise emitter's current shape.

    if missing_kernels:
        receipt["laneStatus"] = "structural_partial_coverage_kernel_gap"
        execution_blocker = "partial_kernel_coverage"
    elif not fits:
        receipt["laneStatus"] = "structural_memory_plan_does_not_fit"
        execution_blocker = "memory_plan_does_not_fit"
    else:
        receipt["laneStatus"] = "structural_full_coverage"
        if streaming_required:
            # Streaming executor primitives exist and run on simfabric
            # (see bench/out/streaming-executor/*-trace.json). The
            # remaining blocker is wiring the execution plan's stage
            # codegen to emit kernels the executor can dispatch — not
            # the executor itself being missing.
            execution_blocker = "streaming_executor_not_bound_to_execution_plan"
        elif not grid_fits_single_memcpy:
            execution_blocker = "full_grid_compile_unattempted"
        else:
            execution_blocker = "full_grid_compile_unattempted"

    receipt["executionStatus"] = "not_attempted"
    receipt["executionBlocker"] = execution_blocker
    receipt["fullGridCompileProbeEvidence"] = {
        "description": "Pointer to the cslc grid-probe aggregate. Documents which grid sizes cslc accepts for this target.",
        "reportPath": "bench/out/cslc-grid-probe/grid-probe-aggregate.json",
        "maxProvenPeCount1D": 17433,
        "maxProvenPeCount2D": 58056,
        "thirtyOneBFullGridCompileVerified": True,
        "thirtyOneBCompileSeconds2D": 1351.85,
    }
    receipt["streamingExecutorPrimitivesEvidence"] = {
        "description": (
            "SdkLayout streaming executor primitives that have been "
            "proven end-to-end on simfabric. Each trace records the "
            "compile + run + numerical-parity result for one primitive. "
            "These primitives are the substrate the execution plan "
            "generator (future work) will compose into per-layer-block "
            "SdkLayout runners."
        ),
        "tracesDir": "bench/out/streaming-executor/",
        "tracesSample": [
            "bench/out/streaming-executor/iter2-trace.json",
            "bench/out/streaming-executor/iter3-trace.json",
            "bench/out/streaming-executor/iter4-trace.json",
            "bench/out/streaming-executor/iter5-trace.json",
            "bench/out/streaming-executor/iter6-trace.json",
            "bench/out/streaming-executor/iter7-trace.json",
            "bench/out/streaming-executor/add-trace.json",
            "bench/out/streaming-executor/gather-trace.json",
            "bench/out/streaming-executor/sigmoid-trace.json",
            "bench/out/streaming-executor/reduce-trace.json",
        ],
        "primitivesProven": [
            "stream_passthrough",
            "compute_transform",
            "region_to_region_chain",
            "multi_pe_spmd_demux_mux",
            "compile_artifact_cache",
            "layer_block_shaped_chain",
            "multi_input_stream_add",
            "indexed_table_gather",
            "elementwise_sigmoid",
            "blocked_reduce_sum",
        ],
    }

    # Chain-parity binding. For each receipt the user passes, include it
    # in chains[] when at least one of its kernel patterns also appears
    # in this model's host-plan. kernelPatternsChainProven is the union
    # of those patterns across all passing chains — the concrete bridge
    # from per-kernel parity to model-level execution evidence.
    host_plan_patterns = {e["pattern"] for e in kernel_entries}
    chain_entries: list[dict[str, Any]] = []
    patterns_chain_proven: set[str] = set()
    for raw_chain_path in args.chain_parity_receipt:
        chain_path = resolve(raw_chain_path)
        try:
            chain = load_json(chain_path)
        except (OSError, json.JSONDecodeError):
            continue
        chain_patterns = sorted({
            s.get("kernelPattern", "") for s in chain.get("steps", []) if s.get("kernelPattern")
        })
        relevant = [p for p in chain_patterns if p in host_plan_patterns]
        if not relevant:
            continue
        end_to_end = chain.get("endToEndParity", {})
        lane_status = chain.get("laneStatus", "unknown")
        chain_entries.append({
            "chainName": chain.get("chainName", ""),
            "receiptPath": rel(chain_path),
            "kernelPatterns": chain_patterns,
            "endToEndMaxAbsErr": float(end_to_end.get("maxAbsErr", float("inf"))),
            "laneStatus": lane_status,
        })
        if lane_status in ("bit_exact", "bit_close") and end_to_end.get("passed", False):
            for pattern in relevant:
                patterns_chain_proven.add(pattern)

    patterns_chain_unproven = sorted(host_plan_patterns - patterns_chain_proven)
    receipt["chainParityEvidence"] = {
        "chains": chain_entries,
        "kernelPatternsChainProven": sorted(patterns_chain_proven),
        "kernelPatternsChainUnproven": patterns_chain_unproven,
        "chainCoverageCount": len(patterns_chain_proven),
        "chainCoverageTotal": len(host_plan_patterns),
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(out_path)} ({len(kernel_entries)} kernels, laneStatus={receipt['laneStatus']})")

    if args.out_md:
        md_lines = [
            f"# Model runtime receipt: {receipt['modelId']}",
            "",
            f"- Model family: `{receipt['modelFamily']}`",
            f"- Grid: {grid['width']} x {grid['height']} ({pe_count:,} PEs)",
            f"- Residency mode: `{receipt['residencyMode']}`",
            f"- Fits in SRAM: {receipt['fits']}",
            f"- Total model bytes: {receipt['memorySummary']['totalModelBytes']:,}",
            f"- SRAM utilization: {receipt['memorySummary']['utilizationPct']}%",
            f"- Runtime path: **{receipt['streamingMigration']['runtimePath']}** "
            f"(streaming-runtime required: {receipt['streamingMigration']['streamingRuntimeRequired']})",
            f"- Double-buffered working set per PE: {receipt['streamingMigration']['doubleBufferedWorkingSetPerPe']:,} bytes "
            f"(fits: {receipt['streamingMigration']['doubleBufferedFits']})",
            f"- Lane status: **{receipt['laneStatus']}** (structural — kernel coverage + memory fit)",
            f"- Execution status: **{receipt['executionStatus']}**"
            + (f" (blocker: `{receipt['executionBlocker']}`)" if receipt['executionBlocker'] != 'none' else ""),
            "",
            "## Kernel coverage",
            "",
            f"- Total kernels: {receipt['kernelCoverage']['total']}",
            f"- By status: {json.dumps(coverage_counts)}",
            f"- Patterns covered: {', '.join(receipt['kernelCoverage']['patternsCovered'])}",
            f"- Patterns missing: {', '.join(receipt['kernelCoverage']['patternsMissing']) or '(none)'}",
            "",
            "## Per-kernel resolution",
            "",
            "| kernel | pattern | count | runtime | fixture |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in kernel_entries:
            md_lines.append(
                f"| {entry['name']} | {entry['pattern']} | {entry['count']} | "
                f"{entry['runtimeStatus']} | {entry.get('fixtureId', '-')} |"
            )

        chain_evidence = receipt.get("chainParityEvidence", {})
        if chain_evidence:
            md_lines += [
                "",
                "## Chain-parity evidence",
                "",
                f"- Patterns proven in chain: {chain_evidence['chainCoverageCount']} / "
                f"{chain_evidence['chainCoverageTotal']}",
                f"- Proven: {', '.join(chain_evidence['kernelPatternsChainProven']) or '(none)'}",
                f"- Unproven: {', '.join(chain_evidence['kernelPatternsChainUnproven']) or '(none)'}",
                "",
                "| chain | kernel patterns | endToEnd err | laneStatus |",
                "| --- | --- | --- | --- |",
            ]
            for c in chain_evidence.get("chains", []):
                md_lines.append(
                    f"| {c['chainName']} | {', '.join(c['kernelPatterns'])} | "
                    f"{c['endToEndMaxAbsErr']:.2e} | {c['laneStatus']} |"
                )
        md_path = resolve(args.out_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        print(f"wrote {rel(md_path)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
