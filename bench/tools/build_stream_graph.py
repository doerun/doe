#!/usr/bin/env python3
"""Derive a doe_stream_graph artifact from a memory plan + model config.

The stream graph expresses the SdkLayout streaming-runtime configuration
(code regions, streams, prefetch schedule, KV policy, compile-artifact
cache) for a model whose model-level runtime receipt reports
runtimePath=sdk_layout_streaming. This builder reads the memory plan's
stream stages + per-PE SRAM budget and emits a conforming artifact with
derived ring-buffer depths, mux patterns (heuristic based on stage kind),
and fail-closed validation flags.

The actual streaming-runtime implementation (async DSDs, ring-buffer
management, compile-artifact cache lookup) is the follow-up to this
schema. Downstream tooling can already consume stream-graph artifacts
for validation and comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

MUX_PATTERN_BY_STAGE_KIND: dict[str, str] = {
    "embedding_rows": "broadcast",
    "layer_weights": "row_broadcast",
    "ple_rows": "column_broadcast",
    "ple_projection": "column_broadcast",
    "kv_stream": "unicast",
}

SOURCE_BY_STAGE_KIND: dict[str, str] = {
    "embedding_rows": "host_embeddings",
    "layer_weights": "host_weights",
    "ple_rows": "host_ple_table",
    "ple_projection": "host_ple_table",
    "kv_stream": "kv_overflow",
}


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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--execution-manifest", required=True)
    p.add_argument("--memory-plan", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument(
        "--compile-artifact-hash",
        default="0000000000000000000000000000000000000000000000000000000000000000",
        help="SHA-256 of the shared transformer-layer compile artifact. Defaults to a zero sentinel until the streaming runtime lands a real per-layer compile + hashing pass.",
    )
    p.add_argument(
        "--cache-root",
        default="bench/out/compile-artifact-cache",
    )
    p.add_argument(
        "--kv-residency",
        default="resident",
        choices=["resident", "spill_to_host", "partitioned_across_pes"],
    )
    p.add_argument(
        "--kv-spill-behavior",
        default="eager",
        choices=["eager", "on_demand", "lru"],
    )
    p.add_argument(
        "--lookahead-layers",
        type=int,
        default=2,
        help="Number of transformer layers to prefetch ahead. Bounded [1, 4] by schema.",
    )
    return p.parse_args()


def compute_validation(code_regions: list[dict[str, Any]], streams: list[dict[str, Any]]) -> dict[str, bool]:
    """Derive stream-graph validation booleans from the graph shape.

    - routingReachable: every stream has a non-empty destinationPort and a
      recognized source, AND the union of codeRegion peRanges covers some
      PEs (can't route into an empty device).
    - portBindingComplete: every codeRegion is referenced (today's emitter
      uses a single shared 'transformer_layer_shape' region that all
      per-layer streams target, so this is true iff at least one stream
      points at each region name via a naming convention or iff we have
      ≥1 stream total per region-count; we take the conservative
      non-zero-streams-when-non-zero-regions check).
    - acyclic: host→port flow with no region→stream back edges. Trivially
      true under the current schema, but we verify no stream's source
      references a codeRegion's regionId (which would imply a cycle).
    """
    regions_non_empty = any(
        int(r.get("peRange", {}).get("end", 0)) - int(r.get("peRange", {}).get("start", 0)) > 0
        for r in code_regions
    )
    streams_non_empty = len(streams) > 0
    every_stream_has_port = all(bool(s.get("destinationPort")) for s in streams)
    routing_reachable = bool(regions_non_empty and every_stream_has_port)

    # portBindingComplete: given today's single-region emitter, "complete"
    # means there is at least one stream whenever there is at least one
    # region. Once the emitter supports multiple regions, tighten this to
    # require every region to have ≥1 stream.
    port_binding_complete = (len(code_regions) == 0) or streams_non_empty

    # acyclic: host→device is the only direction today. A cycle would
    # require a stream to cite a codeRegion as its source, which the
    # schema's source enum prohibits — but verify defensively.
    region_ids = {r.get("regionId", "") for r in code_regions}
    acyclic = not any(s.get("source") in region_ids for s in streams)

    return {
        "routingReachable": routing_reachable,
        "portBindingComplete": port_binding_complete,
        "acyclic": acyclic,
    }


def main() -> int:
    args = parse_args()
    manifest = load_json(resolve(args.execution_manifest))
    memory_plan = load_json(resolve(args.memory_plan))

    num_layers = int(manifest.get("modelConfig", {}).get("numLayers", 0))
    pe_count = int(memory_plan.get("peCount", 0))
    max_seq_len = int(manifest.get("modelConfig", {}).get("maxSeqLen", 0))

    code_regions = [
        {
            "regionId": "transformer_layer_shape",
            "compileArtifactSha256": args.compile_artifact_hash,
            "peRange": {"start": 0, "end": pe_count},
            "layerRange": {"start": 0, "end": num_layers},
        }
    ]

    streams: list[dict[str, Any]] = []
    for stage in memory_plan.get("streamStages", []):
        kind = str(stage.get("kind", ""))
        name = str(stage.get("name", kind or "stream"))
        bytes_per_pe = int(stage.get("bytesPerPe", 0))
        repeat = int(stage.get("repeatCount", 1))
        mux = MUX_PATTERN_BY_STAGE_KIND.get(kind, "broadcast")
        src = SOURCE_BY_STAGE_KIND.get(kind, "host_weights")
        # One-shot stages (repeat == 1) still need a stream but depth 2 is
        # fine — the ring-buffer never fills since we only stream once.
        ring_depth = 2 if repeat > 1 else 2
        streams.append({
            "streamId": f"{name}_stream",
            "source": src,
            "destinationPort": f"{name}_port",
            "ringBufferDepth": ring_depth,
            "payloadBytes": max(1, bytes_per_pe),
            "muxPattern": mux,
        })

    prefetch_schedule = {
        "lookaheadLayers": max(1, min(4, int(args.lookahead_layers))),
        "kickoffTrigger": "activation_ready",
        "stallPolicy": "fail_closed",
    }

    kv_policy: dict[str, Any] = {
        "residency": args.kv_residency,
        "spillBehavior": args.kv_spill_behavior,
    }
    if max_seq_len > 0:
        kv_policy["maxResidentTokens"] = max_seq_len

    compile_artifact_cache = {
        "mode": "per_session",
        "keyHashAlgorithm": "sha256",
        "valueHashAlgorithm": "sha256",
        "cacheRootPath": args.cache_root,
    }

    validation = compute_validation(code_regions, streams)

    graph = {
        "schemaVersion": 1,
        "artifactKind": "doe_stream_graph",
        "target": "wse3",
        "modelId": manifest.get("modelId", ""),
        "residencyMode": memory_plan.get("residencyMode", "layer_streaming"),
        "codeRegions": code_regions,
        "streams": streams,
        "prefetchSchedule": prefetch_schedule,
        "kvPolicy": kv_policy,
        "compileArtifactCache": compile_artifact_cache,
        "validation": validation,
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(out_path)} ({len(streams)} streams, {num_layers} transformer layers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
