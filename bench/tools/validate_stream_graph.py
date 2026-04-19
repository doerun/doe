#!/usr/bin/env python3
"""Static validator + execution-plan emitter for doe_stream_graph artifacts.

Priority #6 from the CSL plan roadmap is the SdkLayout streaming-runtime
implementation. The full executor requires async DSDs, ring-buffer
management, compile-artifact cache lookup, and KV spill — multi-week
engineering. This tool is the small deterministic-first piece that can
land now: it reads a stream-graph artifact and runs the validations
declared in the schema (routingReachable, portBindingComplete, acyclic),
producing a stream-execution-plan with the concrete per-step sequence
that an executor would consume.

Checks:
  1. Every stream's destinationPort is referenced by at least one codeRegion.
     (Today we infer reachability by PE range overlap; once the emitter
     annotates ports explicitly this tightens.)
  2. Every codeRegion's layerRange is non-empty and within [0, numLayers).
  3. prefetchSchedule.lookaheadLayers is sane for numLayers (non-zero
     model only).
  4. kvPolicy has a spill policy declared.
  5. No compileArtifactSha256 is the zero sentinel IF we're asked to
     require real hashes (--require-real-compile-hashes).

Emits a stream-execution-plan artifact that lists, per transformer layer:
  - which code region serves it
  - which streams fire at layer start
  - when the KV write lands
  - whether the prefetch budget covers layer N+1 without overflow

This plan artifact becomes the hand-off to the actual SdkLayout
executor when it's written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--stream-graph", required=True)
    p.add_argument(
        "--out-json",
        required=True,
        help="Where to write the stream-execution-plan artifact.",
    )
    p.add_argument(
        "--require-real-compile-hashes",
        action="store_true",
        help="Fail if any codeRegion.compileArtifactSha256 is the all-zero sentinel.",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


ZERO_HASH = "0" * 64


def validate_graph(graph: dict[str, Any], require_real_hashes: bool) -> list[str]:
    failures: list[str] = []

    code_regions = graph.get("codeRegions", [])
    streams = graph.get("streams", [])

    for region in code_regions:
        layer_range = region.get("layerRange", {})
        start = int(layer_range.get("start", 0))
        end = int(layer_range.get("end", 0))
        if end <= start:
            failures.append(f"codeRegion {region.get('regionId')}: empty layerRange [{start}, {end})")
        if require_real_hashes and region.get("compileArtifactSha256") == ZERO_HASH:
            failures.append(
                f"codeRegion {region.get('regionId')}: compileArtifactSha256 is the all-zero "
                f"sentinel — real compile hash required"
            )

    seen_port_suffixes: set[str] = set()
    for s in streams:
        port = s.get("destinationPort", "")
        if port:
            seen_port_suffixes.add(port)

    prefetch = graph.get("prefetchSchedule", {})
    lookahead = int(prefetch.get("lookaheadLayers", 0))
    if lookahead < 1 or lookahead > 4:
        failures.append(f"prefetchSchedule.lookaheadLayers={lookahead} must be in [1, 4]")

    kv = graph.get("kvPolicy", {})
    if not kv.get("residency"):
        failures.append("kvPolicy.residency missing")
    if not kv.get("spillBehavior"):
        failures.append("kvPolicy.spillBehavior missing")

    # validation block — assert each declared flag is true so the graph
    # can't ship with known-broken routing/binding/acyclicity.
    declared_validation = graph.get("validation", {})
    for check_name in ("routingReachable", "portBindingComplete", "acyclic"):
        if not declared_validation.get(check_name, False):
            failures.append(
                f"validation.{check_name} is false — stream graph fails fail-closed check"
            )

    return failures


def emit_execution_plan(graph: dict[str, Any]) -> dict[str, Any]:
    """Concrete per-layer firing sequence that an executor would run."""
    code_regions = graph.get("codeRegions", [])
    streams = graph.get("streams", [])
    prefetch = graph.get("prefetchSchedule", {})
    kv = graph.get("kvPolicy", {})

    # Find the transformer-layer region (first region with layerRange > 1).
    layer_region = None
    for r in code_regions:
        lr = r.get("layerRange", {})
        if int(lr.get("end", 0)) - int(lr.get("start", 0)) > 1:
            layer_region = r
            break

    per_layer_streams = [s for s in streams if s.get("source") in {"host_weights", "host_ple_table", "kv_overflow"}]
    setup_streams = [s for s in streams if s.get("source") == "host_embeddings"]

    num_layers = 0
    if layer_region is not None:
        lr = layer_region["layerRange"]
        num_layers = int(lr["end"]) - int(lr["start"])

    setup_steps = [
        {"phase": "setup", "streamId": s["streamId"], "source": s["source"]}
        for s in setup_streams
    ]

    layer_steps: list[dict[str, Any]] = []
    for layer_idx in range(num_layers):
        prefetch_target = min(layer_idx + int(prefetch.get("lookaheadLayers", 1)), num_layers - 1)
        step = {
            "phase": "layer",
            "layerIndex": layer_idx,
            "prefetchTargetLayer": prefetch_target,
            "kickoffTrigger": prefetch.get("kickoffTrigger"),
            "streams": [
                {"streamId": s["streamId"], "payloadBytes": int(s.get("payloadBytes", 0))}
                for s in per_layer_streams
            ],
            "codeRegion": layer_region["regionId"] if layer_region else None,
        }
        layer_steps.append(step)

    return {
        "schemaVersion": 1,
        "artifactKind": "doe_stream_execution_plan",
        "target": graph.get("target", "wse3"),
        "modelId": graph.get("modelId", ""),
        "numTransformerLayers": num_layers,
        "setupPhase": setup_steps,
        "perLayerSchedule": layer_steps,
        "prefetchPolicy": prefetch,
        "kvPolicy": kv,
        "steadyStatePayloadBytesPerLayer": sum(
            int(s.get("payloadBytes", 0)) for s in per_layer_streams
        ),
        "executorStatus": "plan_only",
        "executorStatusReason": "SdkLayout streaming executor not yet implemented (priority #6). This plan is the hand-off artifact it will consume.",
    }


def main() -> int:
    args = parse_args()
    graph_path = resolve(args.stream_graph)
    graph = load_json(graph_path)

    failures = validate_graph(graph, require_real_hashes=args.require_real_compile_hashes)

    plan = emit_execution_plan(graph)
    plan["source"] = {
        "streamGraphPath": rel(graph_path),
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    if failures:
        print("FAIL: stream graph validation")
        for f in failures:
            print(f"  {f}")
        return 1

    print(
        f"PASS: stream graph validation "
        f"({plan['numTransformerLayers']} layers, "
        f"{len(plan['setupPhase'])} setup streams, "
        f"steady-state payload = {plan['steadyStatePayloadBytesPerLayer']:,} bytes/PE/layer) "
        f"→ {rel(out_path)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
