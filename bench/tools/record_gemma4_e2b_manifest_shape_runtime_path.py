#!/usr/bin/env python3
"""Record the Gemma-4 E2B manifest-shape Doe/CSL runtime path.

This artifact is a contract and handoff checklist. It links the existing
manifest-shape probe, CPU oracle, execution manifest, and model receipt, then
spells out the missing Doe/CSL stages that must land before this lane can
be promoted beyond blocked status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_EXECUTION_MANIFEST = (
    "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
)
DEFAULT_PROBE = (
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json"
)
DEFAULT_CPU_ORACLE = (
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json"
)
DEFAULT_ATTENTION_CORE = (
    "bench/out/manifest-shape/"
    "gemma-4-e2b-manifest-shape-attention-core.json"
)
DEFAULT_MODEL_RECEIPT = (
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json"
)
DEFAULT_OUT = (
    "bench/out/manifest-shape/"
    "gemma-4-e2b-manifest-shape-runtime-path.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-manifest", default=DEFAULT_EXECUTION_MANIFEST)
    parser.add_argument("--manifest-shape-probe", default=DEFAULT_PROBE)
    parser.add_argument("--cpu-oracle", default=DEFAULT_CPU_ORACLE)
    parser.add_argument("--attention-core-receipt", default=DEFAULT_ATTENTION_CORE)
    parser.add_argument("--model-receipt", default=DEFAULT_MODEL_RECEIPT)
    parser.add_argument("--out-json", default=DEFAULT_OUT)
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json_if_present(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {rel(path)}")
    return payload


def file_link(path: Path) -> dict[str, Any]:
    link: dict[str, Any] = {"path": rel(path), "exists": path.is_file()}
    if path.is_file():
        link["sha256"] = sha256_file(path)
    return link


def int_value(*values: Any, default: int = 0) -> int:
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def model_config(manifest: dict[str, Any]) -> dict[str, Any]:
    config = manifest.get("modelConfig")
    return config if isinstance(config, dict) else {}


def layer_pattern(
    manifest: dict[str, Any],
    *,
    num_layers: int,
    oracle_summary: dict[str, Any],
) -> tuple[list[int], list[int]]:
    oracle_global = oracle_summary.get("globalAttentionLayerIndices")
    if isinstance(oracle_global, list) and all(
        isinstance(v, int) for v in oracle_global
    ):
        global_layers = list(oracle_global)
    else:
        pattern = manifest.get("layerPattern")
        if isinstance(pattern, dict) and pattern.get("type") == "every_n":
            period = int_value(pattern.get("period"), default=0)
            offset = int_value(pattern.get("offset"), default=0)
            global_layers = (
                list(range(offset, num_layers, period)) if period > 0 else []
            )
        else:
            global_layers = []
    global_set = set(global_layers)
    local_layers = [idx for idx in range(num_layers) if idx not in global_set]
    return local_layers, global_layers


def stage(
    *,
    stage_id: str,
    stage_name: str,
    shape: dict[str, Any],
    cpu_oracle_covered: bool,
    blockers: list[str],
    implementation_work: list[str],
) -> dict[str, Any]:
    return {
        "stageId": stage_id,
        "stageName": stage_name,
        "status": "blocked_doe_csl_runtime_missing",
        "shape": shape,
        "coverage": {
            "cpuOracle": cpu_oracle_covered,
            "doeCslRuntime": False,
            "hardware": False,
        },
        "blockers": blockers,
        "implementationWork": implementation_work,
    }


def build_stages(
    *,
    hidden: int,
    num_layers: int,
    local_head_dim: int,
    global_head_dim: int,
    num_heads: int,
    kv_heads: int,
    kv_shared_layers: int,
    ple_width: int,
    vocab_size: int,
    local_layers: list[int],
    global_layers: list[int],
    cpu_oracle_covered: bool,
) -> list[dict[str, Any]]:
    return [
        stage(
            stage_id="embed",
            stage_name="text token embedding",
            shape={"input": ["tokenId"], "output": [hidden]},
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["manifest_shape_embed_stream_not_bound_to_csl"],
            implementation_work=[
                "bind token embedding row load to SdkLayout input stream",
                "emit activation row with hiddenDim-sized f32 contract",
            ],
        ),
        stage(
            stage_id="per_layer_inputs",
            stage_name="per-layer input embedding and projection",
            shape={"output": [num_layers, ple_width]},
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["manifest_shape_ple_stream_layout_missing"],
            implementation_work=[
                "stream embed_tokens_per_layer slices by layer",
                "bind per_layer_model_projection and projection norm",
            ],
        ),
        stage(
            stage_id="local_attention",
            stage_name="local attention head contract",
            shape={
                "layerIndices": local_layers,
                "numAttentionHeads": num_heads,
                "numKeyValueHeads": kv_heads,
                "headDim": local_head_dim,
                "qDim": num_heads * local_head_dim,
                "kvDim": kv_heads * local_head_dim,
            },
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["local_head_dim_256_csl_attention_missing"],
            implementation_work=[
                "replace smoke head_dim=8 kernel path with local headDim",
                "route grouped KV stream for one KV head across attention heads",
            ],
        ),
        stage(
            stage_id="global_attention",
            stage_name="global attention head contract",
            shape={
                "layerIndices": global_layers,
                "numAttentionHeads": num_heads,
                "numKeyValueHeads": kv_heads,
                "headDim": global_head_dim,
                "qDim": num_heads * global_head_dim,
                "kvDim": kv_heads * global_head_dim,
            },
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["global_head_dim_512_csl_attention_missing"],
            implementation_work=[
                "add a global-attention compile shape keyed by globalHeadDim",
                "bind layerPattern global layers to that compile shape",
            ],
        ),
        stage(
            stage_id="grouped_kv_shared_layers",
            stage_name="grouped KV and shared-KV source selection",
            shape={
                "numKeyValueHeads": kv_heads,
                "numKvSharedLayers": kv_shared_layers,
                "kvSourceRule": "last non-shared layer with matching layer type",
            },
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["shared_kv_manifest_shape_state_missing"],
            implementation_work=[
                "materialize per-layer K/V source records in the runner trace",
                "preserve KV source identity across local/global layer types",
            ],
        ),
        stage(
            stage_id="decoder_stack",
            stage_name="decoder layer stack",
            shape={"layers": num_layers, "hidden": hidden},
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["manifest_shape_decoder_stack_runner_missing"],
            implementation_work=[
                "chain manifest-shape layers with distinct stream payloads",
                "emit per-layer parity records against the CPU oracle",
            ],
        ),
        stage(
            stage_id="final_norm",
            stage_name="final RMSNorm",
            shape={"input": [hidden], "output": [hidden]},
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["manifest_shape_final_norm_csl_receipt_missing"],
            implementation_work=[
                "bind final norm weights after decoder stack completion",
            ],
        ),
        stage(
            stage_id="tied_lm_head_logits",
            stage_name="tied LM-head logits",
            shape={"input": [hidden], "output": [vocab_size]},
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["tied_lm_head_logits_csl_receipt_missing"],
            implementation_work=[
                "chunk tied embedding rows across stream windows",
                "emit top-k logits from the same token row contract as oracle",
            ],
        ),
        stage(
            stage_id="logits_parity",
            stage_name="logits parity receipt",
            shape={"comparison": "CPU oracle top-k logits vs Doe/CSL top-k logits"},
            cpu_oracle_covered=cpu_oracle_covered,
            blockers=["manifest_shape_logits_parity_receipt_missing"],
            implementation_work=[
                "compare final hidden digest and top-k logits by schema",
                "keep tolerance and data-source fields visible in the receipt",
            ],
        ),
    ]


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = resolve(args.execution_manifest)
    probe_path = resolve(args.manifest_shape_probe)
    oracle_path = resolve(args.cpu_oracle)
    attention_core_path = resolve(args.attention_core_receipt)
    receipt_path = resolve(args.model_receipt)

    manifest = load_json_if_present(manifest_path)
    probe = load_json_if_present(probe_path)
    oracle = load_json_if_present(oracle_path)
    attention_core = load_json_if_present(attention_core_path)
    receipt = load_json_if_present(receipt_path)

    config = model_config(manifest)
    oracle_summary = oracle.get("executionSummary")
    if not isinstance(oracle_summary, dict):
        oracle_summary = {}

    num_layers = int_value(
        oracle_summary.get("numLayers"),
        config.get("numLayers"),
        default=35,
    )
    hidden = int_value(
        oracle_summary.get("hiddenSize"),
        config.get("hiddenDim"),
        default=1536,
    )
    local_head_dim = int_value(
        oracle_summary.get("localHeadDim"),
        config.get("headDim"),
        default=256,
    )
    global_head_dim = int_value(
        oracle_summary.get("globalHeadDim"),
        config.get("globalHeadDim"),
        default=512,
    )
    num_heads = int_value(
        oracle_summary.get("numAttentionHeads"),
        config.get("numHeads"),
        default=8,
    )
    kv_heads = int_value(
        oracle_summary.get("numKeyValueHeads"),
        config.get("numKeyValueHeads"),
        default=1,
    )
    kv_shared_layers = int_value(
        oracle_summary.get("numKvSharedLayers"),
        config.get("numKvSharedLayers"),
        default=0,
    )
    ple_width = int_value(
        oracle_summary.get("pleWidth"),
        config.get("pleWidth"),
        default=256,
    )
    vocab_size = int_value(
        (oracle.get("output") or {}).get("lmHeadSummary", {}).get("vocabSize")
        if isinstance(oracle.get("output"), dict)
        else None,
        config.get("vocabSize"),
        default=262144,
    )
    local_layers, global_layers = layer_pattern(
        manifest,
        num_layers=num_layers,
        oracle_summary=oracle_summary,
    )

    cpu_oracle_covered = (
        oracle.get("status") == "succeeded"
        and (oracle.get("promotionCriteriaMet") or {}).get(
            "manifestShapeExecuted"
        )
        is True
    )
    smoke_evidence = receipt.get("sdkLayoutModelExecutionEvidence")
    if not isinstance(smoke_evidence, dict):
        smoke_evidence = {}
    attention_coverage = attention_core.get("coverage")
    if not isinstance(attention_coverage, dict):
        attention_coverage = {}
    attention_core_passed = (
        attention_core.get("status") == "succeeded"
        and attention_coverage.get("attentionCoreCslRuntimeExecuted") is True
    )

    blockers = [
        "manifest_shape_doe_csl_runner_missing",
        "embed_unembed_csl_binding_missing",
        "manifest_shape_logits_parity_receipt_missing",
        "cerebras_hardware_receipt_missing",
    ]
    if not attention_core_passed:
        blockers.extend([
            "local_global_head_dim_csl_kernel_rewrite_missing",
            "grouped_kv_manifest_shape_state_missing",
        ])
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_manifest_shape_runtime_path",
        "status": "blocked",
        "verdict": "manifest_shape_doe_csl_runtime_path_blocked",
        "modelId": manifest.get("modelId") or "gemma-4-e2b-it",
        "inputs": {
            "executionManifest": file_link(manifest_path),
            "manifestShapeProbe": file_link(probe_path),
            "cpuOracle": file_link(oracle_path),
            "attentionCoreReceipt": file_link(attention_core_path),
            "modelReceipt": file_link(receipt_path),
        },
        "manifestShapeContract": {
            "hiddenSize": hidden,
            "numLayers": num_layers,
            "localHeadDim": local_head_dim,
            "globalHeadDim": global_head_dim,
            "numAttentionHeads": num_heads,
            "numKeyValueHeads": kv_heads,
            "numKvSharedLayers": kv_shared_layers,
            "localAttentionLayerIndices": local_layers,
            "globalAttentionLayerIndices": global_layers,
            "pleWidth": ple_width,
            "vocabSize": vocab_size,
        },
        "existingEvidence": {
            "manifestShapeProbeStatus": probe.get("status"),
            "cpuOracleStatus": oracle.get("status"),
            "cpuOracleVerdict": oracle.get("verdict"),
            "attentionCoreStatus": attention_core.get("status"),
            "attentionCoreVerdict": attention_core.get("verdict"),
            "attentionCoreCslRuntimeExecuted": attention_coverage.get(
                "attentionCoreCslRuntimeExecuted"
            ),
            "sdkLayoutSmokePromotionStatus": smoke_evidence.get(
                "promotionStatus"
            ),
            "sdkLayoutSmokeClaimScope": smoke_evidence.get("claimScope"),
        },
        "runtimeStages": build_stages(
            hidden=hidden,
            num_layers=num_layers,
            local_head_dim=local_head_dim,
            global_head_dim=global_head_dim,
            num_heads=num_heads,
            kv_heads=kv_heads,
            kv_shared_layers=kv_shared_layers,
            ple_width=ple_width,
            vocab_size=vocab_size,
            local_layers=local_layers,
            global_layers=global_layers,
            cpu_oracle_covered=cpu_oracle_covered,
        ),
        "promotionCriteriaMet": {
            "cpuOracleLinked": bool(file_link(oracle_path).get("sha256")),
            "upstreamManifestShapeRecorded": bool(
                file_link(probe_path).get("sha256")
            ),
            "localGlobalHeadDimCoveredByPath": bool(
                attention_coverage.get("localHeadDimExecuted")
                and attention_coverage.get("globalHeadDimExecuted")
            ),
            "groupedKvCoveredByPath": bool(
                attention_coverage.get("groupedKvExecuted")
            ),
            "embedUnembedCoveredByPath": False,
            "logitsParityCoveredByPath": False,
            "doeRuntimeExecuted": False,
            "cslRuntimeExecuted": False,
            "hardwareExecuted": False,
            "claimable": False,
        },
        "claimScope": {
            "claimable": False,
            "summary": (
                "Runtime-path contract only. The artifact identifies the "
                "manifest-shape Doe/CSL stages and the evidence required "
                "for promotion, but no manifest-shape Doe/CSL runtime "
                "receipt has been produced."
            ),
            "notClaimable": [
                "Doe/CSL manifest-shape runtime receipt",
                "Cerebras hardware receipt",
                "Doppler production inference parity",
                "performance or efficiency claims",
            ],
        },
        "blockers": blockers,
        "nextOperatorReceipts": [
            {
                "name": "manifest_shape_csl_runner_trace",
                "required": True,
                "expectedFields": [
                    "stage coverage for embed, attention, decoder, norm, logits",
                    "per-layer local/global head-dim shape records",
                    "grouped KV source records",
                    "final hidden digest",
                    "top-k logits parity",
                ],
            },
            {
                "name": "hardware_operator_receipt",
                "required": True,
                "expectedFields": [
                    "cmaddr or WSC endpoint identity",
                    "compile/run status",
                    "redacted run log references",
                    "hardware execution verdict",
                ],
            },
        ],
        "errors": [],
    }


def main() -> int:
    args = parse_args()
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = build_payload(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "schemaVersion": 1,
            "artifactKind": "doe_gemma4_e2b_manifest_shape_runtime_path",
            "status": "failed",
            "verdict": "manifest_shape_runtime_path_record_failed",
            "modelId": "gemma-4-e2b-it",
            "inputs": {},
            "manifestShapeContract": {},
            "existingEvidence": {},
            "runtimeStages": [],
            "promotionCriteriaMet": {
                "cpuOracleLinked": False,
                "upstreamManifestShapeRecorded": False,
                "localGlobalHeadDimCoveredByPath": False,
                "groupedKvCoveredByPath": False,
                "embedUnembedCoveredByPath": False,
                "logitsParityCoveredByPath": False,
                "doeRuntimeExecuted": False,
                "cslRuntimeExecuted": False,
                "hardwareExecuted": False,
                "claimable": False,
            },
            "claimScope": {
                "claimable": False,
                "summary": "Runtime-path artifact generation failed.",
                "notClaimable": [
                    "Doe/CSL manifest-shape runtime receipt",
                    "Cerebras hardware receipt",
                ],
            },
            "blockers": ["manifest_shape_runtime_path_record_failed"],
            "nextOperatorReceipts": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {rel(out_path)}")
        return 1
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
