#!/usr/bin/env python3
"""Bind parity across Doppler reference, Doe WebGPU, and Doe CSL transcript receipts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.run_doe_csl_int4ple_transcript import (
    load_json,
    rel,
    resolve,
    schema_failures,
    sha256_file,
    sha256_json,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--left-kind",
        required=True,
        choices=[
            "doppler_reference_export",
            "doe_webgpu_transcript",
            "doe_csl_transcript",
        ],
    )
    parser.add_argument("--left-receipt", required=True)
    parser.add_argument(
        "--right-kind",
        required=True,
        choices=[
            "doppler_reference_export",
            "doe_webgpu_transcript",
            "doe_csl_transcript",
        ],
    )
    parser.add_argument("--right-receipt", required=True)
    parser.add_argument(
        "--schema",
        default="config/doe-shared-execution-parity.schema.json",
    )
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def hash_link(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "sha256": sha256_file(path),
    }


def parity_transcript_from_export(export: dict[str, Any]) -> dict[str, Any] | None:
    transcript = export.get("decodeTranscript")
    if not isinstance(transcript, dict):
        return None
    linked = transcript.get("transcript", {})
    generated = transcript.get("generatedTokenIds", {})
    return {
        "path": linked.get("path", "pending"),
        "sha256": linked.get("sha256", "pending"),
        "requestedDecodeSteps": transcript.get(
            "requestedDecodeSteps",
            transcript.get("decodeStepsRequested", 0),
        ),
        "actualDecodeSteps": transcript.get(
            "actualDecodeSteps",
            transcript.get("decodeStepsProduced", 0),
        ),
        "stopReason": transcript.get("stopReason", "pending"),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": sha256_json(transcript.get("logitsDigests", [])),
        "logitsDigests": transcript.get("logitsDigests", []),
    }


def parity_transcript_from_webgpu(receipt: dict[str, Any]) -> dict[str, Any] | None:
    transcript = (receipt.get("webgpuTranscript") or {}).get("decodeTranscript")
    if not isinstance(transcript, dict):
        return None
    generated = transcript.get("generatedTokenIds") or {}
    return {
        "path": (transcript.get("transcript") or {}).get("path", "pending"),
        "sha256": (transcript.get("transcript") or {}).get("sha256", "pending"),
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "actualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "stopReason": transcript.get("stopReason", "pending"),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": sha256_json(transcript.get("logitsDigests", [])),
        "logitsDigests": transcript.get("logitsDigests", []),
    }


def parity_transcript_from_csl(receipt: dict[str, Any]) -> dict[str, Any] | None:
    transcript = receipt.get("cslTranscript") or {}
    linked = transcript.get("transcript") or {}
    generated = transcript.get("generatedTokenIds") or {}
    return {
        "path": linked.get("path", "pending"),
        "sha256": linked.get("sha256", "pending"),
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "actualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "stopReason": transcript.get("stopReason", "pending"),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": sha256_json(transcript.get("logitsDigests", [])),
        "logitsDigests": transcript.get("logitsDigests", []),
    }


def real_kv_cache_used(csl_receipt: dict[str, Any]) -> bool:
    kv = csl_receipt.get("kvCacheEvidence") or {}
    coverage = kv.get("layerSpanCoverage") or {}
    actual = (csl_receipt.get("cslTranscript") or {}).get("actualDecodeSteps")
    return (
        kv.get("realKvCache") is True
        and int(kv.get("cacheWriteCount") or 0) > 0
        and int(kv.get("cacheReadCount") or 0) > 0
        and coverage.get("coveredLayerCount") == coverage.get("layerCount")
        and isinstance(actual, int)
        and len(kv.get("stepStateDigests") or []) == actual
    )


def real_kv_cache_used_webgpu(receipt: dict[str, Any]) -> bool:
    kv = receipt.get("kvCacheEvidence") or {}
    if kv.get("status") != "output_ready" or kv.get("realKvCache") is not True:
        return False
    byte_digest = kv.get("byteDigest")
    if isinstance(byte_digest, str) and byte_digest not in {"", "pending"}:
        return True
    byte_digests = kv.get("byteDigests")
    if isinstance(byte_digests, list) and byte_digests:
        return True
    layer_digest_count = kv.get("layerDigestCount")
    if (
        isinstance(layer_digest_count, int)
        and not isinstance(layer_digest_count, bool)
        and layer_digest_count > 0
    ):
        return True
    return False


def normalize_run(kind: str, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    if kind == "doppler_reference_export":
        return {
            "kind": kind,
            "status": data.get("exportStatus", "unknown"),
            "sourceArtifact": hash_link(path),
            "sourceProgram": {
                "authoringSurface": "doppler_execution_v1",
                "manifestSha256": data.get("manifestSha256", "pending"),
                "graphSha256": data.get("executionGraphSha256", "pending"),
                "weightSha256": data.get("weightSetSha256", "pending"),
                "inputSetSha256": data.get("inputSetSha256", "pending"),
            },
            "transcript": parity_transcript_from_export(data),
            "realKvCacheUsed": False,
            "inputsSynthetic": bool(data.get("inputsSynthetic", False)),
            "weightsSynthetic": bool(data.get("weightsSynthetic", False)),
            "kernelIsStub": False,
        }
    if kind == "doe_webgpu_transcript":
        return {
            "kind": kind,
            "status": data.get("status", "unknown"),
            "sourceArtifact": hash_link(path),
            "sourceProgram": data.get("sourceProgram") or {},
            "transcript": parity_transcript_from_webgpu(data),
            "realKvCacheUsed": real_kv_cache_used_webgpu(data),
            "inputsSynthetic": bool(data.get("inputsSynthetic", False)),
            "weightsSynthetic": bool(data.get("weightsSynthetic", False)),
            "kernelIsStub": False,
        }
    return {
        "kind": kind,
        "status": data.get("status", "unknown"),
        "sourceArtifact": hash_link(path),
        "sourceProgram": data.get("sourceProgram") or {},
        "transcript": parity_transcript_from_csl(data),
        "realKvCacheUsed": real_kv_cache_used(data),
        "inputsSynthetic": bool(data.get("inputsSynthetic", False)),
        "weightsSynthetic": bool(data.get("weightsSynthetic", False)),
        "kernelIsStub": bool((data.get("simulatorRun") or {}).get("kernelIsStub", True)),
    }


def source_program_summary(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_source = left.get("sourceProgram") or {}
    right_source = right.get("sourceProgram") or {}
    return {
        "authoringSurface": "doppler_execution_v1",
        "manifestSha256": left_source.get("manifestSha256")
        if left_source.get("manifestSha256") == right_source.get("manifestSha256")
        else "pending",
        "graphSha256": left_source.get("graphSha256")
        if left_source.get("graphSha256") == right_source.get("graphSha256")
        else "pending",
        "weightSha256": left_source.get("weightSha256")
        if left_source.get("weightSha256") == right_source.get("weightSha256")
        else "pending",
        "inputSetSha256": left_source.get("inputSetSha256")
        if left_source.get("inputSetSha256") == right_source.get("inputSetSha256")
        else "pending",
    }


def transcript_field(transcript: dict[str, Any] | None, key: str, default: Any) -> Any:
    if not isinstance(transcript, dict):
        return default
    return transcript.get(key, default)


def compare_runs(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    left_source = left.get("sourceProgram") or {}
    right_source = right.get("sourceProgram") or {}
    left_transcript = left.get("transcript") or {}
    right_transcript = right.get("transcript") or {}
    same_manifest = (
        left_source.get("manifestSha256") == right_source.get("manifestSha256")
    )
    same_graph = left_source.get("graphSha256") == right_source.get("graphSha256")
    same_input = (
        left_source.get("inputSetSha256") == right_source.get("inputSetSha256")
    )
    requested_match = transcript_field(left_transcript, "requestedDecodeSteps", 0) == (
        transcript_field(right_transcript, "requestedDecodeSteps", 0)
    )
    actual_match = transcript_field(left_transcript, "actualDecodeSteps", 0) == (
        transcript_field(right_transcript, "actualDecodeSteps", 0)
    )
    stop_match = transcript_field(left_transcript, "stopReason", "pending") == (
        transcript_field(right_transcript, "stopReason", "pending")
    )
    token_match = transcript_field(left_transcript, "generatedTokenIdsSha256", "pending") == (
        transcript_field(right_transcript, "generatedTokenIdsSha256", "pending")
    )
    logits_match = transcript_field(left_transcript, "logitsDigestSha256", "pending") == (
        transcript_field(right_transcript, "logitsDigestSha256", "pending")
    )
    real_kv = bool(left.get("realKvCacheUsed") or right.get("realKvCacheUsed"))
    source_match = same_manifest and same_graph and same_input
    decode_match = requested_match and actual_match and stop_match
    status = (
        "passed"
        if source_match
        and decode_match
        and token_match
        and logits_match
        and not left.get("kernelIsStub")
        and not right.get("kernelIsStub")
        else "failed"
    )
    blocker = ""
    if not same_manifest:
        blocker = "manifest hash mismatch"
    elif not same_graph:
        blocker = "graph hash mismatch"
    elif not same_input:
        blocker = "input-set hash mismatch"
    elif not requested_match:
        blocker = "requested decode steps mismatch"
    elif not actual_match:
        blocker = "actual decode steps mismatch"
    elif not stop_match:
        blocker = "stop reason mismatch"
    elif not token_match:
        blocker = "generated token ids mismatch"
    elif not logits_match:
        blocker = "per-step logits digest mismatch"
    elif left.get("kernelIsStub") or right.get("kernelIsStub"):
        blocker = "one run is still marked as stub"
    comparison = {
        "status": status,
        "sameManifestHash": same_manifest,
        "sameGraphHash": same_graph,
        "sameInputSetHash": same_input,
        "requestedDecodeStepsMatched": requested_match,
        "actualDecodeStepsMatched": actual_match,
        "stopReasonMatched": stop_match,
        "generatedTokenIdsMatched": token_match,
        "perStepLogitsParityPassed": logits_match,
        "realKvCacheUsedOnExecutableLane": real_kv,
        "blocker": blocker,
    }
    promotion = {
        "sourceProgramMatched": source_match,
        "decodeContractMatched": decode_match,
        "tokenIdsMatched": token_match,
        "perStepLogitsParityPassed": logits_match,
        "realKvCacheUsedOnExecutableLane": real_kv,
        "syntheticInputsAbsent": not left.get("inputsSynthetic") and not right.get("inputsSynthetic"),
        "syntheticWeightsAbsent": not left.get("weightsSynthetic") and not right.get("weightsSynthetic"),
        "stubStagesAbsent": not left.get("kernelIsStub") and not right.get("kernelIsStub"),
    }
    return comparison, promotion


def main() -> int:
    args = parse_args()
    left_path = resolve(args.left_receipt)
    right_path = resolve(args.right_receipt)
    left_data = load_json(left_path)
    right_data = load_json(right_path)
    left_run = normalize_run(args.left_kind, left_path, left_data)
    right_run = normalize_run(args.right_kind, right_path, right_data)
    comparison, promotion = compare_runs(left_run, right_run)
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_shared_execution_parity",
        "modelId": left_data.get("modelId") or right_data.get("modelId") or "pending",
        "sourceProgram": source_program_summary(left_run, right_run),
        "leftRun": left_run,
        "rightRun": right_run,
        "comparison": comparison,
        "promotionCriteria": promotion,
    }
    schema = load_json(resolve(args.schema))
    failures = schema_failures(receipt, schema)
    if failures:
        raise ValueError(
            "shared execution parity schema validation failed: "
            + "; ".join(failures[:4])
        )
    out_path = resolve(args.out)
    write_json(out_path, receipt)
    return 0 if comparison["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
