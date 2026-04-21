#!/usr/bin/env python3
"""Validate Doppler INT4 PLE production reference export receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
PENDING_VALUES = {"", "pending", "<pending>"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, help="Export receipt path")
    parser.add_argument(
        "--schema",
        default="config/doppler-int4ple-reference-export.schema.json",
        help="Schema path",
    )
    parser.add_argument(
        "--require-output-ready",
        action="store_true",
        help="Require a complete production tensor export, not only contract shape",
    )
    parser.add_argument(
        "--require-decode-transcript",
        action="store_true",
        help=(
            "Require an output-ready bounded prefill+decode transcript "
            "with generated token IDs and per-step logits."
        ),
    )
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def is_pending(value: Any) -> bool:
    return not isinstance(value, str) or value in PENDING_VALUES


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded + b"\n").hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_path_hash(
    label: str,
    path_text: str,
    expected: str,
    failures: list[str],
    *,
    required: bool,
) -> Path | None:
    if is_pending(path_text) or is_pending(expected):
        if required:
            failures.append(f"{label} path/hash pending")
        return None
    path = resolve(path_text)
    if not path.is_file():
        failures.append(f"{label}.path missing: {path_text}")
        return None
    actual = sha256_file(path)
    if actual != expected:
        failures.append(f"{label}.sha256={expected!r}, actual {actual!r}")
    return path


def manifest_shard_map(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    shards = manifest.get("shards", [])
    if not isinstance(shards, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for shard in shards:
        if isinstance(shard, dict) and isinstance(shard.get("index"), int):
            result[shard["index"]] = shard
    return result


def check_shard_identities(
    export: dict[str, Any],
    manifest: dict[str, Any],
    failures: list[str],
) -> None:
    declared = manifest_shard_map(manifest)
    if not declared:
        failures.append("manifest.shards missing or empty")
        return
    for shard in export.get("shardIdentities", []):
        index = shard.get("index")
        manifest_shard = declared.get(index)
        if manifest_shard is None:
            failures.append(f"shardIdentities[{index}] not present in manifest")
            continue
        expected_hash = manifest_shard.get("sha256") or manifest_shard.get("hash")
        expected_size = manifest_shard.get("sizeBytes") or manifest_shard.get("size")
        if shard.get("sha256") != expected_hash:
            failures.append(
                f"shardIdentities[{index}].sha256 does not match manifest"
            )
        if shard.get("filename") != manifest_shard.get("filename"):
            failures.append(
                f"shardIdentities[{index}].filename does not match manifest"
            )
        if shard.get("sizeBytes") != expected_size:
            failures.append(
                f"shardIdentities[{index}].sizeBytes does not match manifest"
            )


def check_u32_file(
    label: str,
    tokenized: dict[str, Any],
    failures: list[str],
    *,
    required: bool,
) -> None:
    path = check_path_hash(
        label,
        tokenized.get("path", ""),
        tokenized.get("sha256", ""),
        failures,
        required=required,
    )
    if path is None:
        return
    byte_len = path.stat().st_size
    if byte_len % 4 != 0:
        failures.append("tokenizedPrompt byte length is not uint32-aligned")
        return
    token_count = byte_len // 4
    if token_count != tokenized.get("tokenCount"):
        failures.append(
            f"{label}.tokenCount="
            f"{tokenized.get('tokenCount')!r}, actual {token_count}"
        )


def check_tensor_file(
    label: str,
    tensor: dict[str, Any],
    failures: list[str],
    *,
    required: bool,
) -> None:
    path = check_path_hash(
        label,
        tensor.get("path", ""),
        tensor.get("sha256", ""),
        failures,
        required=required,
    )
    if path is None:
        return
    byte_len = path.stat().st_size
    if byte_len != tensor.get("byteLength"):
        failures.append(
            f"{label}.byteLength={tensor.get('byteLength')!r}, "
            f"actual {byte_len}"
        )
    expected_shape = tensor.get("shape", [])
    if expected_shape and byte_len != int(expected_shape[0]) * 4:
        failures.append(f"{label}.shape[0] does not match f32 byte length")


def check_decode_transcript(
    export: dict[str, Any],
    failures: list[str],
    *,
    required: bool,
) -> None:
    transcript = export.get("decodeTranscript")
    if not isinstance(transcript, dict):
        if required:
            failures.append("decodeTranscript missing")
        return
    if required and export.get("referenceKind") != "prefill_decode_transcript":
        failures.append("referenceKind must be prefill_decode_transcript")
    if required and transcript.get("status") != "output_ready":
        failures.append(
            "decodeTranscript.status="
            f"{transcript.get('status')!r}, expected 'output_ready'"
        )

    transcript_path = check_path_hash(
        "decodeTranscript.transcript",
        transcript.get("transcript", {}).get("path", ""),
        transcript.get("transcript", {}).get("sha256", ""),
        failures,
        required=required,
    )
    check_u32_file(
        "decodeTranscript.generatedTokenIds",
        transcript.get("generatedTokenIds", {}),
        failures,
        required=required,
    )
    logits_digests = transcript.get("logitsDigests", [])
    if not isinstance(logits_digests, list):
        failures.append("decodeTranscript.logitsDigests must be an array")
        logits_digests = []
    produced = transcript.get("decodeStepsProduced")
    actual = transcript.get("actualDecodeSteps")
    requested = transcript.get("decodeStepsRequested")
    requested_alias = transcript.get("requestedDecodeSteps")
    if requested != requested_alias:
        failures.append(
            "decodeTranscript.requestedDecodeSteps does not match "
            "decodeStepsRequested"
        )
    if produced != actual:
        failures.append(
            "decodeTranscript.actualDecodeSteps does not match "
            "decodeStepsProduced"
        )
    if isinstance(produced, int) and len(logits_digests) != produced:
        failures.append(
            "decodeTranscript.logitsDigests length "
            f"{len(logits_digests)} != decodeStepsProduced {produced}"
        )
    if required and (not isinstance(produced, int) or produced <= 0):
        failures.append("decodeTranscript.decodeStepsProduced must be positive")
    token_count = transcript.get("generatedTokenIds", {}).get("tokenCount")
    if isinstance(produced, int) and token_count != produced:
        failures.append(
            "decodeTranscript.generatedTokenIds.tokenCount "
            f"{token_count!r} != decodeStepsProduced {produced}"
        )
    for index, digest in enumerate(logits_digests):
        check_tensor_file(
            f"decodeTranscript.logitsDigests[{index}]",
            digest,
            failures,
            required=required,
        )
    if transcript_path is None:
        return
    try:
        transcript_json = load_json(transcript_path)
    except json.JSONDecodeError as exc:
        failures.append(f"decodeTranscript.transcript invalid JSON: {exc}")
        return
    if transcript_json.get("inputSetSha256") != export.get("inputSetSha256"):
        failures.append("decodeTranscript inputSetSha256 does not match export")
    steps = transcript_json.get("steps")
    if isinstance(steps, list) and isinstance(produced, int) and len(steps) != produced:
        failures.append(
            f"decodeTranscript.transcript steps length {len(steps)} "
            f"!= decodeStepsProduced {produced}"
        )


def main() -> int:
    args = parse_args()
    failures: list[str] = []

    try:
        export = load_json(resolve(args.receipt))
        schema = load_json(resolve(args.schema))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: Doppler INT4 PLE reference export gate: {exc}")
        return 1

    failures.extend(
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(export),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    )

    output_ready = export.get("exportStatus") == "output_ready"
    if args.require_output_ready and not output_ready:
        failures.append(
            f"exportStatus={export.get('exportStatus')!r}, expected 'output_ready'"
        )

    if export.get("inputsSynthetic") is not False:
        failures.append("inputsSynthetic must be false")
    if export.get("weightsSynthetic") is not False:
        failures.append("weightsSynthetic must be false")

    producer = export.get("producer", {})
    if producer.get("runtime") not in {
        "doppler_browser_webgpu",
        "doppler_node_webgpu",
    }:
        failures.append("producer.runtime is not a Doppler production WebGPU runtime")

    manifest_path = check_path_hash(
        "manifest",
        export.get("manifestPath", ""),
        export.get("manifestSha256", ""),
        failures,
        required=args.require_output_ready,
    )

    manifest: dict[str, Any] = {}
    if manifest_path is not None:
        try:
            manifest = load_json(manifest_path)
        except json.JSONDecodeError as exc:
            failures.append(f"manifest invalid JSON: {exc}")

    if manifest:
        if manifest.get("modelId") != export.get("modelId"):
            failures.append(
                f"modelId={export.get('modelId')!r}, "
                f"manifest.modelId={manifest.get('modelId')!r}"
            )
        check_shard_identities(export, manifest, failures)

    execution_graph = export.get("executionGraph", {})
    graph_path = check_path_hash(
        "executionGraph",
        execution_graph.get("path", ""),
        execution_graph.get("sha256", ""),
        failures,
        required=args.require_output_ready,
    )
    if (
        not is_pending(export.get("executionGraphSha256"))
        and execution_graph.get("sha256") != export.get("executionGraphSha256")
    ):
        failures.append("executionGraph.sha256 differs from executionGraphSha256")
    if graph_path is not None:
        try:
            graph = load_json(graph_path)
        except json.JSONDecodeError as exc:
            failures.append(f"executionGraph invalid JSON: {exc}")
        else:
            if graph.get("manifestSha256") != export.get("manifestSha256"):
                failures.append(
                    "executionGraph.manifestSha256 does not match export"
                )

    check_path_hash(
        "prompt",
        export.get("prompt", {}).get("path", ""),
        export.get("prompt", {}).get("sha256", ""),
        failures,
        required=args.require_output_ready,
    )
    check_u32_file(
        "tokenizedPrompt",
        export.get("tokenizedPrompt", {}),
        failures,
        required=args.require_output_ready,
    )
    check_tensor_file(
        "tensorDigest",
        export.get("tensorDigest", {}),
        failures,
        required=args.require_output_ready,
    )
    check_decode_transcript(
        export,
        failures,
        required=args.require_decode_transcript,
    )

    input_set = export.get("inputSetComponents", {})
    input_set_sha = export.get("inputSetSha256", "")
    if not is_pending(input_set_sha):
        actual = sha256_json(input_set)
        if actual != input_set_sha:
            failures.append(
                f"inputSetSha256={input_set_sha!r}, actual {actual!r}"
            )
    elif args.require_output_ready:
        failures.append("inputSetSha256 pending")

    weight_set_sha = export.get("weightSetSha256", "")
    if not is_pending(weight_set_sha):
        actual = sha256_json(
            {
                "shardIdentities": export.get("shardIdentities", []),
                "weightSetId": export.get("weightSetId"),
            }
        )
        if actual != weight_set_sha:
            failures.append(
                f"weightSetSha256={weight_set_sha!r}, actual {actual!r}"
            )
    elif args.require_output_ready:
        failures.append("weightSetSha256 pending")

    if output_ready and export.get("tensorDigest", {}).get("status") != "output_ready":
        failures.append("tensorDigest.status must be output_ready")

    if failures:
        print("FAIL: Doppler INT4 PLE reference export gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(
        "PASS: Doppler INT4 PLE reference export gate "
        f"(model={export.get('modelId', '?')}, "
        f"status={export.get('exportStatus', '?')}, "
        f"producer={producer.get('runtime', '?')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
