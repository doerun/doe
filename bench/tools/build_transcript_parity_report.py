#!/usr/bin/env python3
"""Build a backend-agnostic transcript parity report.

This tool binds one Doppler reference export and one or more Doe transcript
receipts into a single pairwise comparison report. It understands the existing
CSL transcript receipt shape (`cslTranscript`) and a generic Doe transcript
shape (`transcript` or `webgpuTranscript`) so WebGPU and CSL lanes can be
compared on the same source-program contract without editing the INT4-specific
parity binder.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_KEYS = (
    "transcript",
    "webgpuTranscript",
    "cslTranscript",
)

READY_TRANSCRIPT_STATUS = "output_ready"

READY_TRANSCRIPT_RECEIPT_STATUSES = {
    "output_ready",
    "simulator_success",
}

SOURCE_REQUIRED_FIELDS = (
    "manifestSha256",
    "graphSha256",
    "weightSha256",
    "inputSetSha256",
)


@dataclass(frozen=True)
class TranscriptStep:
    """Normalized transcript step digest used for pairwise comparison."""

    step_index: int
    phase: str | None
    selected_token_id: int | None
    context_token_count: int | None
    shape: tuple[int, ...]
    path: str | None
    sha256: str | None


@dataclass(frozen=True)
class Participant:
    """One normalized report participant."""

    participant_id: str
    role: str
    backend_kind: str
    artifact_kind: str
    receipt_path: str
    receipt_sha256: str
    status: str
    model_id: str
    source_program: dict[str, Any]
    transcript_digest: dict[str, Any]
    transcript_steps: tuple[TranscriptStep, ...]
    evidence: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-export", required=True)
    parser.add_argument(
        "--lane",
        action="append",
        default=[],
        help=(
            "Transcript lane in the form <backend>:<receipt-path>. "
            "Repeat for each Doe transcript receipt."
        ),
    )
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--schema",
        default="config/doe-transcript-parity-report.schema.json",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=None,
        help="Override the parity absolute tolerance.",
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=None,
        help="Override the parity relative tolerance.",
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded + b"\n").hexdigest()


def parse_lane_spec(raw: str) -> tuple[str, Path]:
    if ":" not in raw:
        raise ValueError(
            f"lane must use <backend>:<receipt-path> format, got {raw!r}"
        )
    backend, path_text = raw.split(":", 1)
    backend = backend.strip()
    path_text = path_text.strip()
    if not backend:
        raise ValueError(f"lane backend is empty in {raw!r}")
    if not path_text:
        raise ValueError(f"lane receipt path is empty in {raw!r}")
    return backend, resolve(path_text)


def infer_reference_source_program(export: dict[str, Any]) -> dict[str, Any]:
    source_program = {
        "authoringSurface": "doppler_execution_v1",
        "manifestSha256": export.get("manifestSha256"),
        "graphSha256": export.get("executionGraphSha256"),
        "weightSha256": export.get("weightSetSha256"),
        "inputSetSha256": export.get("inputSetSha256"),
    }
    if export.get("programBundleId"):
        source_program["programBundleId"] = export["programBundleId"]
    return source_program


def normalize_source_program(source: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "authoringSurface": source.get("authoringSurface", "unknown"),
        "manifestSha256": source.get("manifestSha256"),
        "graphSha256": source.get("graphSha256", source.get("executionGraphSha256")),
        "weightSha256": source.get("weightSha256", source.get("weightSetSha256")),
        "inputSetSha256": source.get("inputSetSha256"),
    }
    if source.get("programBundleId"):
        normalized["programBundleId"] = source["programBundleId"]
    if source.get("programContractVersion"):
        normalized["programContractVersion"] = source["programContractVersion"]
    program_bundle = source.get("programBundle")
    if isinstance(program_bundle, dict):
        path_text = program_bundle.get("path")
        sha256_text = program_bundle.get("sha256")
        if isinstance(path_text, str) and isinstance(sha256_text, str):
            normalized["programBundle"] = {
                "path": path_text,
                "sha256": sha256_text,
                **(
                    {"source": program_bundle["source"]}
                    if isinstance(program_bundle.get("source"), str)
                    else {}
                ),
            }
    return normalized


def require_transcript_container(
    receipt: dict[str, Any],
    receipt_path: Path,
) -> tuple[str, dict[str, Any]]:
    for key in TRANSCRIPT_KEYS:
        value = receipt.get(key)
        if isinstance(value, dict):
            nested = value.get("decodeTranscript")
            if isinstance(nested, dict):
                return f"{key}.decodeTranscript", nested
            return key, value
    raise ValueError(
        "transcript receipt missing transcript payload under one of "
        f"{TRANSCRIPT_KEYS}: {repo_relative(receipt_path)}"
    )


def transcript_link_digest(transcript: dict[str, Any]) -> tuple[str | None, str | None]:
    linked = transcript.get("transcript")
    if not isinstance(linked, dict):
        return None, None
    path_text = linked.get("path")
    sha256_text = linked.get("sha256")
    return (
        path_text if isinstance(path_text, str) else None,
        sha256_text if isinstance(sha256_text, str) else None,
    )


def generated_tokens_sha(transcript: dict[str, Any]) -> str:
    generated = transcript.get("generatedTokenIds")
    if isinstance(generated, dict) and isinstance(generated.get("sha256"), str):
        return generated["sha256"]
    digest = transcript.get("generatedTokenIdsSha256")
    if isinstance(digest, str):
        return digest
    raise ValueError("transcript missing generated token ids sha256")


def decode_steps_requested(
    transcript: dict[str, Any],
    receipt: dict[str, Any],
) -> int:
    for value in (
        transcript.get("requestedDecodeSteps"),
        transcript.get("decodeStepsRequested"),
        (receipt.get("decodeRequest") or {}).get("requestedDecodeSteps"),
    ):
        if isinstance(value, int):
            return value
    raise ValueError("transcript missing requested decode step count")


def decode_steps_actual(
    transcript: dict[str, Any],
    receipt: dict[str, Any],
) -> int:
    for value in (
        transcript.get("actualDecodeSteps"),
        transcript.get("decodeStepsProduced"),
        (receipt.get("decodeRequest") or {}).get("expectedActualDecodeSteps"),
    ):
        if isinstance(value, int):
            return value
    raise ValueError("transcript missing actual decode step count")


def stop_reason(
    transcript: dict[str, Any],
    receipt: dict[str, Any],
) -> str:
    for value in (
        transcript.get("stopReason"),
        (receipt.get("decodeRequest") or {}).get("expectedStopReason"),
    ):
        if isinstance(value, str):
            return value
    raise ValueError("transcript missing stop reason")


def transcript_steps(transcript: dict[str, Any]) -> tuple[TranscriptStep, ...]:
    raw_steps = transcript.get("logitsDigests")
    if raw_steps is None:
        return ()
    if not isinstance(raw_steps, list):
        raise ValueError("transcript logitsDigests must be an array")
    steps: list[TranscriptStep] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"transcript logitsDigests[{index}] must be an object")
        shape = raw_step.get("shape") or []
        if not isinstance(shape, list) or not all(isinstance(v, int) for v in shape):
            raise ValueError(f"transcript logitsDigests[{index}].shape must be int[]")
        path_value = raw_step.get("path")
        sha256_value = raw_step.get("sha256")
        steps.append(
            TranscriptStep(
                step_index=int(raw_step.get("stepIndex", index)),
                phase=raw_step.get("phase")
                if isinstance(raw_step.get("phase"), str)
                else None,
                selected_token_id=raw_step.get("selectedTokenId")
                if isinstance(raw_step.get("selectedTokenId"), int)
                else None,
                context_token_count=raw_step.get("contextTokenCount")
                if isinstance(raw_step.get("contextTokenCount"), int)
                else None,
                shape=tuple(shape),
                path=path_value if isinstance(path_value, str) else None,
                sha256=sha256_value if isinstance(sha256_value, str) else None,
            )
        )
    return tuple(steps)


def build_reference_participant(export_path: Path) -> Participant:
    export = load_json(export_path)
    transcript = export.get("decodeTranscript")
    if not isinstance(transcript, dict):
        raise ValueError("reference export missing decodeTranscript")
    model_id = export.get("modelId")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("reference export missing modelId")
    transcript_path, transcript_sha256 = transcript_link_digest(transcript)
    return Participant(
        participant_id="reference",
        role="reference",
        backend_kind="doppler_reference_export",
        artifact_kind=str(export.get("artifactKind", "unknown")),
        receipt_path=repo_relative(export_path),
        receipt_sha256=sha256_file(export_path),
        status=str(export.get("exportStatus", "unknown")),
        model_id=model_id,
        source_program=infer_reference_source_program(export),
        transcript_digest={
            "status": str(transcript.get("status", export.get("exportStatus", "unknown"))),
            "requestedDecodeSteps": decode_steps_requested(transcript, export),
            "actualDecodeSteps": decode_steps_actual(transcript, export),
            "decodeStepsProduced": int(
                transcript.get(
                    "decodeStepsProduced",
                    decode_steps_actual(transcript, export),
                )
            ),
            "stopReason": stop_reason(transcript, export),
            "generatedTokenIdsSha256": generated_tokens_sha(transcript),
            "logitsDigestCount": len(transcript.get("logitsDigests") or []),
            "logitsDigestsSha256": sha256_json(transcript.get("logitsDigests") or []),
            **(
                {"transcriptPath": transcript_path}
                if transcript_path is not None
                else {}
            ),
            **(
                {"transcriptSha256": transcript_sha256}
                if transcript_sha256 is not None
                else {}
            ),
        },
        transcript_steps=transcript_steps(transcript),
        evidence={
            "realKvCache": None,
            "kernelIsStub": None,
            "inputsSynthetic": export.get("inputsSynthetic"),
            "weightsSynthetic": export.get("weightsSynthetic"),
        },
    )


def unique_participant_id(backend: str, used: set[str]) -> str:
    base = f"doe_{backend.replace('-', '_')}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def build_lane_participant(
    backend: str,
    receipt_path: Path,
    used_ids: set[str],
) -> Participant:
    receipt = load_json(receipt_path)
    model_id = receipt.get("modelId")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(
            f"transcript receipt missing modelId: {repo_relative(receipt_path)}"
        )
    source = receipt.get("sourceProgram")
    if not isinstance(source, dict):
        raise ValueError(
            f"transcript receipt missing sourceProgram: {repo_relative(receipt_path)}"
        )
    _, transcript = require_transcript_container(receipt, receipt_path)
    transcript_path, transcript_sha256 = transcript_link_digest(transcript)
    transcript_status = transcript.get("status", receipt.get("status", "unknown"))
    evidence = {
        "realKvCache": (
            (receipt.get("kvCacheEvidence") or {}).get("realKvCache")
            if isinstance(receipt.get("kvCacheEvidence"), dict)
            else None
        ),
        "kernelIsStub": (
            (receipt.get("simulatorRun") or {}).get("kernelIsStub")
            if isinstance(receipt.get("simulatorRun"), dict)
            else None
        ),
        "inputsSynthetic": receipt.get("inputsSynthetic"),
        "weightsSynthetic": receipt.get("weightsSynthetic"),
    }
    return Participant(
        participant_id=unique_participant_id(backend, used_ids),
        role="doe_transcript",
        backend_kind=backend,
        artifact_kind=str(receipt.get("artifactKind", "unknown")),
        receipt_path=repo_relative(receipt_path),
        receipt_sha256=sha256_file(receipt_path),
        status=str(receipt.get("status", transcript_status)),
        model_id=model_id,
        source_program=normalize_source_program(source),
        transcript_digest={
            "status": str(transcript_status),
            "requestedDecodeSteps": decode_steps_requested(transcript, receipt),
            "actualDecodeSteps": decode_steps_actual(transcript, receipt),
            "decodeStepsProduced": int(
                transcript.get(
                    "decodeStepsProduced",
                    decode_steps_actual(transcript, receipt),
                )
            ),
            "stopReason": stop_reason(transcript, receipt),
            "generatedTokenIdsSha256": generated_tokens_sha(transcript),
            "logitsDigestCount": len(transcript.get("logitsDigests") or []),
            "logitsDigestsSha256": sha256_json(transcript.get("logitsDigests") or []),
            **(
                {"transcriptPath": transcript_path}
                if transcript_path is not None
                else {}
            ),
            **(
                {"transcriptSha256": transcript_sha256}
                if transcript_sha256 is not None
                else {}
            ),
        },
        transcript_steps=transcript_steps(transcript),
        evidence=evidence,
    )


def load_f32_values(path: Path) -> list[float]:
    raw = path.read_bytes()
    if len(raw) % 4 != 0:
        raise ValueError(f"float32 artifact has non-multiple-of-4 length: {path}")
    values = struct.iter_unpack("<f", raw)
    return [value[0] for value in values]


def compare_float32_files(
    left_path: Path,
    right_path: Path,
    atol: float,
    rtol: float,
) -> tuple[bool, float]:
    left_values = load_f32_values(left_path)
    right_values = load_f32_values(right_path)
    if len(left_values) != len(right_values):
        return False, float("inf")
    max_abs_err = 0.0
    for left_value, right_value in zip(left_values, right_values, strict=True):
        abs_err = abs(left_value - right_value)
        max_abs_err = max(max_abs_err, abs_err)
        if abs_err > atol + (rtol * max(abs(left_value), abs(right_value))):
            return False, max_abs_err
    return True, max_abs_err


def compare_source_programs(
    left: dict[str, Any],
    right: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    missing_fields: list[str] = []
    comparison: dict[str, Any] = {}
    all_required_match = True
    for field in SOURCE_REQUIRED_FIELDS:
        left_value = left.get(field)
        right_value = right.get(field)
        if not isinstance(left_value, str) or not isinstance(right_value, str):
            missing_fields.append(field)
            comparison[f"{field}Match"] = False
            all_required_match = False
            continue
        matched = left_value == right_value
        comparison[f"{field}Match"] = matched
        all_required_match = all_required_match and matched

    authoring_surface_match: bool | None = None
    left_authoring = left.get("authoringSurface")
    right_authoring = right.get("authoringSurface")
    if isinstance(left_authoring, str) and isinstance(right_authoring, str):
        authoring_surface_match = left_authoring == right_authoring
        all_required_match = all_required_match and authoring_surface_match

    program_bundle_id_match: bool | None = None
    left_bundle_id = left.get("programBundleId")
    right_bundle_id = right.get("programBundleId")
    if isinstance(left_bundle_id, str) and isinstance(right_bundle_id, str):
        program_bundle_id_match = left_bundle_id == right_bundle_id
        all_required_match = all_required_match and program_bundle_id_match

    comparison["comparable"] = len(missing_fields) == 0
    comparison["authoringSurfaceMatch"] = authoring_surface_match
    comparison["programBundleIdMatch"] = program_bundle_id_match
    if missing_fields:
        comparison["missingFields"] = missing_fields
    return comparison, all_required_match


def transcript_step_metadata_matches(
    left_steps: tuple[TranscriptStep, ...],
    right_steps: tuple[TranscriptStep, ...],
) -> bool:
    if len(left_steps) != len(right_steps):
        return False
    for left_step, right_step in zip(left_steps, right_steps, strict=True):
        if (
            left_step.step_index != right_step.step_index
            or left_step.phase != right_step.phase
            or left_step.selected_token_id != right_step.selected_token_id
            or left_step.context_token_count != right_step.context_token_count
            or left_step.shape != right_step.shape
        ):
            return False
    return True


def compare_transcripts(
    left: Participant,
    right: Participant,
    logits_comparison: str,
    atol: float,
    rtol: float,
) -> tuple[dict[str, Any], bool, list[str]]:
    left_digest = left.transcript_digest
    right_digest = right.transcript_digest
    missing_artifacts: list[str] = []
    generated_token_ids_match = (
        left_digest["generatedTokenIdsSha256"]
        == right_digest["generatedTokenIdsSha256"]
    )
    comparison = {
        "requestedDecodeStepsMatch": (
            left_digest["requestedDecodeSteps"] == right_digest["requestedDecodeSteps"]
        ),
        "actualDecodeStepsMatch": (
            left_digest["actualDecodeSteps"] == right_digest["actualDecodeSteps"]
        ),
        "stopReasonMatch": left_digest["stopReason"] == right_digest["stopReason"],
        "generatedTokenIdsMatch": generated_token_ids_match,
        "generatedTokenParityStatus": (
            "matched" if generated_token_ids_match else "mismatch"
        ),
        "logitsDigestCountMatch": (
            left_digest["logitsDigestCount"] == right_digest["logitsDigestCount"]
        ),
        "logitsComparison": logits_comparison,
        "logitsComparisonStatus": "all_within_tolerance",
        "perStepMetadataMatch": transcript_step_metadata_matches(
            left.transcript_steps,
            right.transcript_steps,
        ),
        "comparedLogitsStepCount": 0,
        "maxAbsErr": 0.0,
        "atol": atol,
        "rtol": rtol,
    }

    per_step_parity: bool | None = True
    max_abs_err = 0.0
    if not comparison["perStepMetadataMatch"]:
        per_step_parity = False
    else:
        for index, (left_step, right_step) in enumerate(
            zip(left.transcript_steps, right.transcript_steps, strict=True)
        ):
            comparison["comparedLogitsStepCount"] = index + 1
            if isinstance(left_step.sha256, str) and isinstance(right_step.sha256, str):
                if left_step.sha256 == right_step.sha256:
                    continue
                if logits_comparison == "sha256_exact":
                    per_step_parity = False
                    break
            elif logits_comparison == "sha256_exact":
                missing_artifacts.append(
                    f"{left.participant_id}.logitsDigests[{index}].sha256"
                )
                per_step_parity = False
                continue
            if not isinstance(left_step.path, str):
                missing_artifacts.append(
                    f"{left.participant_id}.logitsDigests[{index}].path"
                )
                continue
            if not isinstance(right_step.path, str):
                missing_artifacts.append(
                    f"{right.participant_id}.logitsDigests[{index}].path"
                )
                continue
            left_path = resolve(left_step.path)
            right_path = resolve(right_step.path)
            if not left_path.is_file():
                missing_artifacts.append(repo_relative(left_path))
                continue
            if not right_path.is_file():
                missing_artifacts.append(repo_relative(right_path))
                continue
            passed, step_abs_err = compare_float32_files(
                left_path,
                right_path,
                atol,
                rtol,
            )
            max_abs_err = max(max_abs_err, step_abs_err)
            if not passed:
                per_step_parity = False
                break

    comparison["maxAbsErr"] = max_abs_err
    comparison["perStepLogitsParityPassed"] = per_step_parity
    comparison["comparable"] = len(missing_artifacts) == 0
    if missing_artifacts:
        comparison["logitsComparisonStatus"] = "blocked"
    elif per_step_parity is True and logits_comparison == "sha256_exact":
        comparison["logitsComparisonStatus"] = "sha256_exact_match"
    elif per_step_parity is True:
        comparison["logitsComparisonStatus"] = "all_within_tolerance"
    elif logits_comparison == "sha256_exact":
        comparison["logitsComparisonStatus"] = "sha256_exact_mismatch"
    else:
        comparison["logitsComparisonStatus"] = "exceeds_tolerance"
    if missing_artifacts:
        comparison["missingArtifacts"] = missing_artifacts

    transcript_ok = (
        comparison["requestedDecodeStepsMatch"]
        and comparison["actualDecodeStepsMatch"]
        and comparison["stopReasonMatch"]
        and comparison["generatedTokenIdsMatch"]
        and comparison["logitsDigestCountMatch"]
        and comparison["perStepMetadataMatch"]
        and per_step_parity is True
    )
    return comparison, transcript_ok, missing_artifacts


def comparison_blocker(
    source_program: dict[str, Any],
    transcript: dict[str, Any],
) -> str | None:
    if not source_program["comparable"]:
        missing = ", ".join(source_program.get("missingFields") or [])
        return f"source program missing fields: {missing}"
    if not transcript["comparable"]:
        missing = ", ".join(transcript.get("missingArtifacts") or [])
        return f"transcript artifacts missing: {missing}"
    return None


def participant_readiness_blocker(participant: Participant) -> str | None:
    transcript_status = participant.transcript_digest["status"]
    if transcript_status != READY_TRANSCRIPT_STATUS:
        return (
            f"{participant.participant_id} transcript status is "
            f"{transcript_status!r}, expected {READY_TRANSCRIPT_STATUS!r}"
        )
    if (
        participant.role == "doe_transcript"
        and participant.status not in READY_TRANSCRIPT_RECEIPT_STATUSES
    ):
        ready_values = ", ".join(sorted(READY_TRANSCRIPT_RECEIPT_STATUSES))
        return (
            f"{participant.participant_id} receipt status is "
            f"{participant.status!r}, expected one of: {ready_values}"
        )
    return None


def compare_participants(
    left: Participant,
    right: Participant,
    logits_comparison: str,
    atol: float,
    rtol: float,
) -> dict[str, Any]:
    source_program, source_program_ok = compare_source_programs(
        left.source_program,
        right.source_program,
    )
    transcript, transcript_ok, _ = compare_transcripts(
        left,
        right,
        logits_comparison,
        atol,
        rtol,
    )
    blocker = comparison_blocker(source_program, transcript)
    if blocker is None:
        blocker = participant_readiness_blocker(left)
    if blocker is None:
        blocker = participant_readiness_blocker(right)
    if blocker is not None:
        status = "blocked"
    elif source_program_ok and transcript_ok:
        status = "passed"
    else:
        status = "failed"
    result = {
        "leftParticipantId": left.participant_id,
        "rightParticipantId": right.participant_id,
        "status": status,
        "sourceProgram": source_program,
        "transcript": transcript,
    }
    if blocker is not None:
        result["blocker"] = blocker
    return result


def validate_report(report: dict[str, Any], schema_path: Path) -> None:
    schema = load_json(schema_path)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(report),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        messages = [
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        ]
        raise ValueError("report schema validation failed: " + "; ".join(messages))


def source_program_identity_matches(comparison: dict[str, Any]) -> bool:
    source_program = comparison["sourceProgram"]
    return (
        source_program["comparable"]
        and all(
            source_program[field] is True
            for field in (
                "manifestSha256Match",
                "graphSha256Match",
                "weightSha256Match",
                "inputSetSha256Match",
            )
        )
        and source_program["authoringSurfaceMatch"] is not False
        and source_program["programBundleIdMatch"] is not False
    )


def build_report(
    reference_export_path: Path,
    lanes: list[tuple[str, Path]],
    schema_path: Path,
    atol_override: float | None = None,
    rtol_override: float | None = None,
) -> dict[str, Any]:
    reference = load_json(reference_export_path)
    comparison_policy = reference.get("tolerancePolicy") or {}
    atol = (
        float(atol_override)
        if atol_override is not None
        else float(comparison_policy.get("atol", 0.0))
    )
    rtol = (
        float(rtol_override)
        if rtol_override is not None
        else float(comparison_policy.get("rtol", 0.0))
    )

    reference_participant = build_reference_participant(reference_export_path)
    used_ids = {reference_participant.participant_id}
    participants = [reference_participant]
    for backend, receipt_path in lanes:
        participants.append(build_lane_participant(backend, receipt_path, used_ids))

    model_ids = {participant.model_id for participant in participants}
    if len(model_ids) != 1:
        raise ValueError(f"participants do not agree on modelId: {sorted(model_ids)}")

    logits_comparison = str(comparison_policy.get("comparison", "max_abs"))
    comparisons = [
        compare_participants(left, right, logits_comparison, atol, rtol)
        for left, right in itertools.combinations(participants, 2)
    ]
    report = {
        "schemaVersion": 2,
        "artifactKind": "doe_transcript_parity_report",
        "modelId": reference_participant.model_id,
        "sourceProgram": reference_participant.source_program,
        "comparisonPolicy": {
            "comparison": logits_comparison,
            "atol": atol,
            "rtol": rtol,
        },
        "participants": [
            {
                "participantId": participant.participant_id,
                "role": participant.role,
                "backendKind": participant.backend_kind,
                "artifactKind": participant.artifact_kind,
                "receiptPath": participant.receipt_path,
                "receiptSha256": participant.receipt_sha256,
                "status": participant.status,
                "sourceProgram": participant.source_program,
                "transcript": participant.transcript_digest,
                "evidence": participant.evidence,
            }
            for participant in participants
        ],
        "comparisons": comparisons,
        "summary": {
            "referenceParticipantId": reference_participant.participant_id,
            "participantCount": len(participants),
            "comparisonCount": len(comparisons),
            "passedCount": sum(1 for item in comparisons if item["status"] == "passed"),
            "failedCount": sum(1 for item in comparisons if item["status"] == "failed"),
            "blockedCount": sum(1 for item in comparisons if item["status"] == "blocked"),
            "sameSourceProgramAcrossParticipants": all(
                source_program_identity_matches(item)
                for item in comparisons
                if reference_participant.participant_id
                in (item["leftParticipantId"], item["rightParticipantId"])
            ),
        },
    }
    validate_report(report, schema_path)
    return report


def main() -> int:
    args = parse_args()
    if not args.lane:
        raise SystemExit("at least one --lane <backend>:<receipt-path> is required")
    try:
        lanes = [parse_lane_spec(value) for value in args.lane]
        report = build_report(
            reference_export_path=resolve(args.reference_export),
            lanes=lanes,
            schema_path=resolve(args.schema),
            atol_override=args.atol,
            rtol_override=args.rtol,
        )
        out_path = resolve(args.out)
        write_json(out_path, report)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: transcript parity report: {exc}")
        return 1

    print(
        "PASS: wrote transcript parity report "
        f"{repo_relative(out_path)} "
        f"(participants={report['summary']['participantCount']}, "
        f"comparisons={report['summary']['comparisonCount']}, "
        f"passed={report['summary']['passedCount']}, "
        f"failed={report['summary']['failedCount']}, "
        f"blocked={report['summary']['blockedCount']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
