#!/usr/bin/env python3
"""Classify Doe WebGPU C-lane first-zero evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_WEBGPU_RECEIPT = Path(
    "bench/out/doppler-reference/gemma-3-1b-doe-webgpu-transcript.json"
)
DEFAULT_EXPORTER_RECEIPT = Path(
    "bench/out/doppler-reference/"
    "gemma-3-1b-doe-webgpu-export/doppler_int4ple_reference_export.json"
)
DEFAULT_OUT = Path(
    "bench/out/doppler-reference/"
    "gemma-3-1b-doe-webgpu-first-zero-diagnostic.json"
)
DEFAULT_SCHEMA = Path("config/doe-webgpu-first-zero-diagnostic.schema.json")
FLOAT32_BYTES = 4
PREVIEW_LIMIT = 8
NO_FINITE_LOGITS_MESSAGE = "no finite candidate logits"


@dataclass(frozen=True)
class DiagnosticInputs:
    webgpu_receipt: Path
    exporter_receipt: Path | None
    final_logits: Path | None
    stdout_log: Path | None
    stderr_log: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--webgpu-receipt",
        default=str(DEFAULT_WEBGPU_RECEIPT),
        help="Doe WebGPU transcript receipt emitted by the shared-contract runner.",
    )
    parser.add_argument(
        "--exporter-receipt",
        default=str(DEFAULT_EXPORTER_RECEIPT),
        help="Underlying Doppler exporter receipt, if one exists.",
    )
    parser.add_argument(
        "--final-logits",
        default=None,
        help="Optional final_logits.f32 path. Defaults to receipt metadata.",
    )
    parser.add_argument(
        "--stdout-log",
        default=None,
        help="Optional exporter stdout log. Defaults to runner receipt metadata.",
    )
    parser.add_argument(
        "--stderr-log",
        default=None,
        help="Optional exporter stderr log. Defaults to runner receipt metadata.",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Diagnostic receipt schema.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Output diagnostic receipt.",
    )
    return parser.parse_args()


def resolve(raw: str | Path | None) -> Path | None:
    if raw is None:
        return None
    text = str(raw)
    if not text or text == "pending":
        return None
    path = Path(text)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_link(path: Path | None, source: str) -> dict[str, str]:
    if path is None or not path.is_file():
        return {"path": "pending", "sha256": "pending", "source": source}
    return {"path": rel(path), "sha256": sha256_file(path), "source": source}


def nested_path(value: dict[str, Any], keys: list[str]) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def resolve_link_path(value: Any) -> Path | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    if not isinstance(path, str):
        return None
    return resolve(path)


def read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def json_float(value: float) -> float | str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return value


def float32_evidence(
    path: Path | None,
    exporter_receipt: dict[str, Any],
) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "status": "missing",
            "path": "pending",
            "sha256": "pending",
            "byteLength": 0,
            "elementCount": 0,
            "finiteCount": 0,
            "nonzeroCount": 0,
            "nanCount": 0,
            "infCount": 0,
            "allZero": False,
            "minFinite": None,
            "maxFinite": None,
            "preview": [],
            "exporterDigestMatchesTensor": None,
        }
    data = path.read_bytes()
    byte_length = len(data)
    if byte_length % FLOAT32_BYTES != 0:
        return {
            "status": "invalid_float32",
            "path": rel(path),
            "sha256": sha256_file(path),
            "byteLength": byte_length,
            "elementCount": 0,
            "finiteCount": 0,
            "nonzeroCount": 0,
            "nanCount": 0,
            "infCount": 0,
            "allZero": False,
            "minFinite": None,
            "maxFinite": None,
            "preview": [],
            "exporterDigestMatchesTensor": None,
        }

    finite_count = 0
    nonzero_count = 0
    nan_count = 0
    inf_count = 0
    min_finite: float | None = None
    max_finite: float | None = None
    preview: list[float | str] = []
    for index, (value,) in enumerate(struct.iter_unpack("<f", data)):
        if index < PREVIEW_LIMIT:
            preview.append(json_float(value))
        if math.isnan(value):
            nan_count += 1
            continue
        if math.isinf(value):
            inf_count += 1
            continue
        finite_count += 1
        if value != 0.0:
            nonzero_count += 1
        min_finite = value if min_finite is None else min(min_finite, value)
        max_finite = value if max_finite is None else max(max_finite, value)

    element_count = byte_length // FLOAT32_BYTES
    tensor_sha256 = sha256_file(path)
    exporter_sha256 = nested_path(exporter_receipt, ["tensorDigest", "sha256"])
    return {
        "status": "output_ready",
        "path": rel(path),
        "sha256": tensor_sha256,
        "byteLength": byte_length,
        "elementCount": element_count,
        "finiteCount": finite_count,
        "nonzeroCount": nonzero_count,
        "nanCount": nan_count,
        "infCount": inf_count,
        "allZero": element_count > 0 and finite_count == element_count
        and nonzero_count == 0,
        "minFinite": min_finite,
        "maxFinite": max_finite,
        "preview": preview,
        "exporterDigestMatchesTensor": (
            tensor_sha256 == exporter_sha256
            if isinstance(exporter_sha256, str)
            and exporter_sha256 not in {"", "pending"}
            else None
        ),
    }


def default_log_path(
    explicit: Path | None,
    webgpu_receipt: dict[str, Any],
    field: str,
) -> Path | None:
    if explicit is not None:
        return explicit
    return resolve_link_path(nested_path(webgpu_receipt, ["runtimeRun", field]))


def default_logits_path(
    explicit: Path | None,
    webgpu_receipt: dict[str, Any],
    exporter_receipt: dict[str, Any],
) -> Path | None:
    if explicit is not None:
        return explicit
    for source in (
        nested_path(exporter_receipt, ["tensorDigest"]),
        nested_path(webgpu_receipt, ["webgpuTranscript", "tensorDigest"]),
    ):
        path = resolve_link_path(source)
        if path is not None:
            return path
    return None


def runtime_signals(
    webgpu_receipt: dict[str, Any],
    stdout_text: str,
    stderr_text: str,
) -> dict[str, Any]:
    combined = f"{stdout_text}\n{stderr_text}"
    return {
        "runnerExitCode": int(
            nested_path(webgpu_receipt, ["runtimeRun", "exitCode"]) or 0
        ),
        "hasF16Advertised": "hasF16=true" in stdout_text,
        "hasSubgroupsAdvertised": "hasSubgroups=true" in stdout_text,
        "samplingNoFiniteCandidate": (
            NO_FINITE_LOGITS_MESSAGE in combined.lower()
        ),
        "pipelineCreationFailureMentioned": (
            "vkCreateComputePipelines" in combined
            or "createComputePipeline" in combined
        ),
    }


def decode_evidence(exporter_receipt: dict[str, Any]) -> dict[str, Any]:
    transcript = exporter_receipt.get("decodeTranscript")
    if not isinstance(transcript, dict):
        return {
            "status": "not_captured",
            "requestedDecodeSteps": 0,
            "actualDecodeSteps": 0,
            "stopReason": "pending",
            "generatedTokenCount": 0,
            "generatedTokenPreview": [],
            "logitsStepCount": 0,
        }
    generated = transcript.get("generatedTokenIds")
    if not isinstance(generated, dict):
        generated = {}
    return {
        "status": str(transcript.get("status") or "unknown"),
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "actualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "stopReason": str(transcript.get("stopReason") or "pending"),
        "generatedTokenCount": int(generated.get("tokenCount") or 0),
        "generatedTokenPreview": [
            int(token) for token in generated.get("preview") or []
        ],
        "logitsStepCount": len(transcript.get("logitsDigests") or []),
    }


def kv_evidence(exporter_receipt: dict[str, Any]) -> dict[str, Any]:
    evidence = exporter_receipt.get("kvCacheEvidence")
    if not isinstance(evidence, dict):
        return {
            "status": "not_captured",
            "realKvCache": False,
            "byteDigest": "pending",
            "layerDigestCount": 0,
            "seqLen": 0,
        }
    return {
        "status": str(evidence.get("status") or "unknown"),
        "realKvCache": evidence.get("realKvCache") is True,
        "byteDigest": str(evidence.get("byteDigest") or "pending"),
        "layerDigestCount": int(evidence.get("layerDigestCount") or 0),
        "seqLen": int(evidence.get("seqLen") or 0),
    }


def classify_status(
    logits: dict[str, Any],
    signals: dict[str, Any],
) -> str:
    if logits["status"] == "missing":
        return "blocked_missing_tensor"
    if logits["status"] == "invalid_float32":
        return "inconclusive"
    if signals["samplingNoFiniteCandidate"] and logits["allZero"]:
        return "blocked_all_zero_logits"
    if signals["samplingNoFiniteCandidate"]:
        return "blocked_no_finite_logits"
    if logits["allZero"]:
        return "blocked_all_zero_logits"
    if logits["finiteCount"] > 0 and logits["nonzeroCount"] > 0:
        return "not_blocked_by_zero_logits"
    return "inconclusive"


def blocker_for_status(status: str) -> str:
    blockers = {
        "blocked_all_zero_logits": (
            "Doe native Vulkan produced an all-zero final_logits.f32 tensor; "
            "sampling then reported no finite candidate logits."
        ),
        "blocked_no_finite_logits": (
            "Doe native Vulkan reached sampling but the logits distribution "
            "had no finite candidate after masking."
        ),
        "blocked_missing_tensor": (
            "Doe WebGPU diagnostics could not locate final_logits.f32."
        ),
        "inconclusive": (
            "Doe WebGPU diagnostics did not isolate a first-zero condition."
        ),
        "not_blocked_by_zero_logits": (
            "final_logits.f32 contains finite non-zero values; the first-zero "
            "blocker was not reproduced by this artifact."
        ),
    }
    return blockers[status]


def build_diagnostic(inputs: DiagnosticInputs) -> dict[str, Any]:
    webgpu_receipt = load_json(inputs.webgpu_receipt)
    exporter_receipt = load_json(inputs.exporter_receipt)
    stdout_log = default_log_path(
        inputs.stdout_log,
        webgpu_receipt,
        "stdoutLog",
    )
    stderr_log = default_log_path(
        inputs.stderr_log,
        webgpu_receipt,
        "stderrLog",
    )
    stdout_text = read_text(stdout_log)
    stderr_text = read_text(stderr_log)
    logits_path = default_logits_path(
        inputs.final_logits,
        webgpu_receipt,
        exporter_receipt,
    )
    logits = float32_evidence(logits_path, exporter_receipt)
    signals = runtime_signals(webgpu_receipt, stdout_text, stderr_text)
    status = classify_status(logits, signals)
    source_program = webgpu_receipt.get("sourceProgram")
    if not isinstance(source_program, dict):
        source_program = {}
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_webgpu_first_zero_diagnostic",
        "status": status,
        "modelId": str(
            webgpu_receipt.get("modelId")
            or exporter_receipt.get("modelId")
            or "pending"
        ),
        "sourceProgram": source_program,
        "artifacts": {
            "webgpuReceipt": hash_link(
                inputs.webgpu_receipt,
                "doe_webgpu_transcript",
            ),
            "exporterReceipt": hash_link(
                inputs.exporter_receipt,
                "doppler_reference_export",
            ),
            "finalLogits": hash_link(logits_path, "final_logits_f32"),
            "stdoutLog": hash_link(stdout_log, "doe_webgpu_export_stdout"),
            "stderrLog": hash_link(stderr_log, "doe_webgpu_export_stderr"),
        },
        "runtimeSignals": signals,
        "logitsEvidence": logits,
        "decodeEvidence": decode_evidence(exporter_receipt),
        "kvCacheEvidence": kv_evidence(exporter_receipt),
        "blocker": blocker_for_status(status),
        "nextProbes": [
            "capture per-dispatch output buffers for embed, attention, residual, gelu, and lm_head",
            "compare first non-zero/non-finite boundary against browser WebGPU reference tensors",
            "bind the failing dispatch to the shared execution graph node and kernelPathId",
        ],
        "claimBoundary": {
            "claimable": False,
            "scope": (
                "Diagnostic only. This artifact narrows the Doe native Vulkan "
                "C-lane failure and does not claim browser parity, CSL parity, "
                "or hardware execution."
            ),
            "blockedUntil": [
                "final logits contain finite non-zero candidate values",
                "bounded decode emits token/logit evidence without sampling failure",
                "the same manifest and graph pass the simulator parity receipt",
            ],
        },
    }


def schema_failures(data: Any, schema: Any) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(data),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    ]


def main() -> int:
    args = parse_args()
    inputs = DiagnosticInputs(
        webgpu_receipt=resolve(args.webgpu_receipt) or DEFAULT_WEBGPU_RECEIPT,
        exporter_receipt=resolve(args.exporter_receipt),
        final_logits=resolve(args.final_logits),
        stdout_log=resolve(args.stdout_log),
        stderr_log=resolve(args.stderr_log),
    )
    diagnostic = build_diagnostic(inputs)
    schema = load_json(resolve(args.schema))
    failures = schema_failures(diagnostic, schema)
    if failures:
        print("FAIL: Doe WebGPU first-zero diagnostic schema validation")
        for failure in failures:
            print(f"  {failure}")
        return 1
    out_path = resolve(args.out)
    if out_path is None:
        raise ValueError("--out must not be pending")
    write_json(out_path, diagnostic)
    print(
        "PASS: Doe WebGPU first-zero diagnostic "
        f"({rel(out_path)}, status={diagnostic['status']})"
    )
    return 0 if diagnostic["status"] != "inconclusive" else 1


if __name__ == "__main__":
    raise SystemExit(main())
