#!/usr/bin/env python3
"""Build a dashboard-friendly CSL demo evidence adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-receipt",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    parser.add_argument(
        "--reference-parity",
        default=(
            "examples/"
            "doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json"
        ),
    )
    parser.add_argument(
        "--int4ple-reference-export",
        default=(
            "bench/out/doppler-reference/"
            "gemma-4-e2b-int4ple-production-final-logits/"
            "doppler_int4ple_reference_export.json"
        ),
    )
    parser.add_argument(
        "--int4ple-parity",
        default=(
            "bench/out/doppler-reference/"
            "gemma-4-e2b-int4ple-doe-csl-reference-parity.pending.json"
        ),
    )
    parser.add_argument(
        "--lane-rollup",
        default="bench/out/doe-run/all-lanes-summary-L1.json",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/csl-demo-evidence/gemma-4-e2b-demo-evidence.json",
    )
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> Any | None:
    return load_json(path) if path.is_file() else None


def evidence_sha(path_text: str) -> str:
    path = resolve(path_text)
    return sha256_file(path) if path.is_file() else ""


def source_program_from_parity(parity: dict[str, Any]) -> dict[str, str]:
    source = parity.get("sourceProgram", {})
    return {
        "manifestPath": source.get("manifestPath", ""),
        "manifestSha256": source.get("manifestSha256", ""),
        "graphPath": source.get("graphPath", ""),
        "graphSha256": source.get("graphSha256", ""),
        "weightSetId": source.get("weightSetId", ""),
        "weightSha256": source.get("weightSha256", ""),
    }


def source_program_from_export(export: dict[str, Any]) -> dict[str, str]:
    graph = export.get("executionGraph", {})
    return {
        "manifestPath": export.get("manifestPath", ""),
        "manifestSha256": export.get("manifestSha256", ""),
        "graphPath": graph.get("path", ""),
        "graphSha256": export.get("executionGraphSha256", ""),
        "weightSetId": export.get("weightSetId", ""),
        "weightSha256": export.get("weightSetSha256", ""),
    }


def failed_criteria(criteria: dict[str, Any]) -> list[str]:
    return [
        f"{key}=false"
        for key, value in sorted(criteria.items())
        if key != "hardwareReceiptRequiredForHardwareClaim" and value is not True
    ]


def main() -> int:
    args = parse_args()
    model_path = resolve(args.model_receipt)
    parity_path = resolve(args.reference_parity)
    int4_export_path = resolve(args.int4ple_reference_export)
    int4_parity_path = resolve(args.int4ple_parity)
    lane_rollup_path = resolve(args.lane_rollup)
    model = load_json(model_path)
    parity = load_json(parity_path)
    int4_export = load_optional_json(int4_export_path)
    int4_parity = load_optional_json(int4_parity_path)
    lane_rollup = load_optional_json(lane_rollup_path)

    source = parity["sourceProgram"]
    ref_status = parity["referenceRun"]["status"]
    csl_status = parity["cslRun"]["status"]
    csl_parity = parity["cslRun"].get("numericalParity", {})
    model_blocker = model.get("executionBlocker", "unknown")
    model_status = model.get("executionStatus", "unknown")
    end_to_end = model.get("endToEndModelExecution") or {}
    end_to_end_status = end_to_end.get("status", "not_attempted")
    end_to_end_blocker = end_to_end.get(
        "blocker", "full_e2b_end_to_end_receipt_absent"
    )
    model_end_to_end_passed = end_to_end_status == "succeeded"

    rows = [
        {
            "id": "doppler-browser-reference",
            "label": "Doppler browser/WebGPU reference",
            "runtime": "browser_webgpu",
            "status": "pass" if ref_status == "output_ready" else "metadata_bound",
            "summary": (
                "Same manifest and graph are bound; external browser "
                "output vector is still pending."
            ),
            "evidencePath": rel(parity_path),
            "evidenceSha256": sha256_file(parity_path),
            "blocker": parity["comparison"].get("blocker", ""),
        },
        {
            "id": "csl-simfabric-layer-block",
            "label": "Doe CSL simfabric layer-block proof",
            "runtime": "csl_simfabric",
            "status": (
                "pass"
                if csl_status == "succeeded" and csl_parity.get("passed")
                else "blocked"
            ),
            "summary": parity["cslRun"].get("kernelStage", ""),
            "evidencePath": parity["cslRun"]["tracePath"],
            "evidenceSha256": evidence_sha(parity["cslRun"]["tracePath"]),
            "maxAbsErr": float(csl_parity.get("maxAbsErr", 0.0)),
            "parityPassed": bool(csl_parity.get("passed", False)),
        },
        {
            "id": "csl-full-model",
            "label": "Doe CSL end-to-end E2B gate",
            "runtime": "csl_model",
            "status": "pass" if model_end_to_end_passed else "not_attempted",
            "summary": (
                f"modelRuntimeExecutionStatus={model_status}; "
                f"end_to_end={end_to_end_status}; "
                f"blocker={end_to_end_blocker}"
            ),
            "evidencePath": rel(model_path),
            "evidenceSha256": sha256_file(model_path),
            "blocker": end_to_end_blocker,
        },
        {
            "id": "csl-hardware",
            "label": "Doe CSL WSC hardware receipt",
            "runtime": "csl_hardware",
            "status": "pending",
            "summary": (
                "Hardware row is pending a WSC appliance receipt for "
                "the same manifest and graph."
            ),
            "evidencePath": rel(model_path),
            "evidenceSha256": sha256_file(model_path),
            "blocker": "hardware_receipt_not_available",
        },
    ]

    if int4_export is not None:
        tensor = int4_export.get("tensorDigest", {})
        transcript = int4_export.get("decodeTranscript", {})
        transcript_ready = transcript.get("status") == "output_ready"
        reference_ready = (
            int4_export.get("exportStatus") == "output_ready"
            and tensor.get("status") == "output_ready"
        )
        transcript_summary = (
            f"; transcriptSteps={transcript.get('decodeStepsProduced')}"
            if transcript
            else "; transcript=not_bound"
        )
        rows.append({
            "id": "doppler-int4ple-reference",
            "label": "Doppler production INT4 PLE reference",
            "runtime": int4_export.get("producer", {}).get(
                "runtime", "doppler_node_webgpu"
            ),
            "status": "pass" if reference_ready else "blocked",
            "summary": (
                f"referenceKind={int4_export.get('referenceKind', 'final_logits')}; "
                f"final_logits={tensor.get('sha256', 'missing')}"
                f"{transcript_summary}; reference only until Doe CSL parity binds"
            ),
            "evidencePath": rel(int4_export_path),
            "evidenceSha256": sha256_file(int4_export_path),
            "blocker": "" if transcript_ready else "bounded_decode_transcript_pending",
            "sourceProgram": source_program_from_export(int4_export),
        })

    if int4_parity is not None:
        comparison = int4_parity.get("comparison", {})
        criteria = int4_parity.get("promotionCriteria", {})
        missing = failed_criteria(criteria)
        promoted = not missing and comparison.get("status") == "passed"
        rows.append({
            "id": "doe-csl-int4ple-transcript-parity",
            "label": "Doe CSL INT4 PLE transcript parity",
            "runtime": "csl_simfabric",
            "status": "pass" if promoted else "blocked",
            "summary": (
                f"comparison={comparison.get('status', 'unknown')}; "
                "promotion requires same hashes, real KV/cache, token IDs, "
                "per-step logits, no stubs, no synthetic inputs/weights"
            ),
            "evidencePath": rel(int4_parity_path),
            "evidenceSha256": sha256_file(int4_parity_path),
            "blocker": comparison.get("blocker", "; ".join(missing)),
            "sourceProgram": source_program_from_parity(int4_parity),
        })

    if lane_rollup is not None:
        runtime_map = {
            "webgpu-wgsl": "webgpu_wgsl",
            "csl-webgpu-emulator": "csl_webgpu_emulator",
            "csl-sdklayout": "csl_simfabric",
        }
        label_map = {
            "webgpu-wgsl": "WebGPU WGSL L1 side-by-side lane",
            "csl-webgpu-emulator": "CSL semantic WebGPU emulator L1 lane",
            "csl-sdklayout": "CSL simfabric SdkLayout L1 lane",
        }
        for lane in lane_rollup.get("lanes", []):
            lane_id = lane.get("lane")
            if lane_id not in runtime_map:
                continue
            receipt_path = lane.get("receiptPath") or (
                f"bench/out/doe-run/{lane_id}/L"
                f"{lane_rollup.get('numLayers', 1)}-receipt.json"
            )
            rows.append({
                "id": f"doe-run-{lane_id}-l{lane_rollup.get('numLayers', 1)}",
                "label": label_map[lane_id],
                "runtime": runtime_map[lane_id],
                "status": "pass" if lane.get("status") == "succeeded" else "blocked",
                "summary": (
                    f"outputSha256={lane.get('outputSha256', 'none')}; "
                    f"rollup={lane_rollup.get('verdict', 'unknown')}; "
                    "layer-block lane only"
                ),
                "evidencePath": receipt_path,
                "evidenceSha256": evidence_sha(receipt_path),
                "blocker": (
                    ""
                    if lane.get("status") == "succeeded"
                    else f"lane_status={lane.get('status', 'missing')}"
                ),
            })

    out = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_demo_evidence",
        "modelId": model["modelId"],
        "sourceProgram": {
            "manifestPath": source["manifestPath"],
            "manifestSha256": source["manifestSha256"],
            "graphPath": source["graphPath"],
            "graphSha256": source["graphSha256"],
        },
        "rows": rows,
    }
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
