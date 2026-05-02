#!/usr/bin/env python3
"""Validate Doe CSL INT4 PLE transcript receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
PENDING = {"", "pending", "<pending>"}


def strip_sha256_prefix(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.removeprefix("sha256:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--schema",
        default="config/doe-csl-int4ple-transcript.schema.json",
    )
    parser.add_argument("--reference-export")
    parser.add_argument("--require-simulator-success", action="store_true")
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_f32_values(path: Path) -> list[float]:
    raw = path.read_bytes()
    if len(raw) % 4 != 0:
        raise ValueError(f"float32 artifact byte length is not divisible by 4: {path}")
    return [item[0] for item in struct.iter_unpack("<f", raw)]


def compare_float32_files(
    actual_path: Path,
    reference_path: Path,
    *,
    atol: float,
    rtol: float,
) -> tuple[bool, float]:
    actual_values = load_f32_values(actual_path)
    reference_values = load_f32_values(reference_path)
    if len(actual_values) != len(reference_values):
        return False, float("inf")
    max_abs_err = 0.0
    for actual, reference in zip(actual_values, reference_values, strict=True):
        abs_err = abs(actual - reference)
        max_abs_err = max(max_abs_err, abs_err)
        if abs_err > atol + rtol * max(abs(actual), abs(reference)):
            return False, max_abs_err
    return True, max_abs_err


def schema_failures(data: Any, schema: Any) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            validator.iter_errors(data),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    ]


def check_path_hash(
    label: str,
    path_text: str,
    sha256: str,
    failures: list[str],
    *,
    required: bool,
) -> None:
    if path_text in PENDING or sha256 in PENDING:
        if required:
            failures.append(f"{label} path/hash pending")
        return
    path = resolve(path_text)
    if not path.is_file():
        failures.append(f"{label}.path missing: {path_text}")
        return
    actual = sha256_file(path)
    if actual != sha256:
        failures.append(f"{label}.sha256={sha256!r}, actual {actual!r}")


def check_reference_identity(
    receipt: dict[str, Any],
    export: dict[str, Any],
    failures: list[str],
) -> None:
    source = receipt.get("sourceProgram") or {}
    graph = export.get("executionGraph") or {}
    expected = {
        "manifestSha256": export.get("manifestSha256"),
        "graphSha256": export.get("executionGraphSha256"),
        "weightSha256": export.get("weightSetSha256"),
        "inputSetSha256": export.get("inputSetSha256"),
        "graphPath": graph.get("path"),
    }
    for key, expected_value in expected.items():
        if source.get(key) != expected_value:
            failures.append(
                f"sourceProgram.{key}={source.get(key)!r}, "
                f"expected {expected_value!r}"
            )

    reference = receipt.get("referenceTranscript") or {}
    doppler = export.get("decodeTranscript") or {}
    generated = doppler.get("generatedTokenIds") or {}
    expected_transcript = doppler.get("transcript") or {}
    if reference.get("sha256") != expected_transcript.get("sha256"):
        failures.append("referenceTranscript.sha256 does not match export")
    if reference.get("generatedTokenIdsSha256") != generated.get("sha256"):
        failures.append(
            "referenceTranscript.generatedTokenIdsSha256 does not match export"
        )

    program_link = source.get("programBundle")
    if isinstance(program_link, dict):
        path_text = program_link.get("path", "")
        sha256 = program_link.get("sha256", "")
        check_path_hash(
            "sourceProgram.programBundle",
            path_text,
            sha256,
            failures,
            required=True,
        )
        if path_text not in PENDING and sha256 not in PENDING:
            program_bundle = load_json(resolve(path_text))
            if program_bundle.get("schema") == "doppler.program-bundle/v1":
                sources = program_bundle.get("sources") or {}
                if strip_sha256_prefix(
                    (sources.get("manifest") or {}).get("hash")
                ) != export.get("manifestSha256"):
                    failures.append(
                        "sourceProgram.programBundle manifest hash does not match export"
                    )
                if strip_sha256_prefix(
                    (sources.get("executionGraph") or {}).get("hash")
                ) != export.get("executionGraphSha256"):
                    failures.append(
                        "sourceProgram.programBundle graph hash does not match export"
                    )
                if (
                    source.get("programBundleId")
                    and source.get("programBundleId") != program_bundle.get("bundleId")
                ):
                    failures.append("sourceProgram.programBundleId mismatch")
                return
            if program_bundle.get("artifactKind") != "doppler_program_bundle":
                failures.append("sourceProgram.programBundle artifactKind mismatch")
            if (
                program_bundle.get("manifest") or {}
            ).get("sha256") != export.get("manifestSha256"):
                failures.append(
                    "sourceProgram.programBundle manifest hash does not match export"
                )
            if (
                program_bundle.get("executionGraph") or {}
            ).get("sha256") != export.get("executionGraphSha256"):
                failures.append(
                    "sourceProgram.programBundle graph hash does not match export"
                )
            if (
                program_bundle.get("tokenizerInput") or {}
            ).get("inputSetSha256") != export.get("inputSetSha256"):
                failures.append(
                    "sourceProgram.programBundle input hash does not match export"
                )
            if (
                program_bundle.get("referenceTranscript") or {}
            ).get("sha256") != expected_transcript.get("sha256"):
                failures.append(
                    "sourceProgram.programBundle transcript hash does not match export"
                )


def check_transcript_reference_parity(
    receipt: dict[str, Any],
    export: dict[str, Any],
    failures: list[str],
) -> None:
    transcript = receipt.get("cslTranscript") or {}
    reference = export.get("decodeTranscript") or {}
    policy = export.get("tolerancePolicy") or {}
    comparison = str(policy.get("comparison") or "max_abs")
    try:
        atol = float(policy.get("atol", 0.0))
        rtol = float(policy.get("rtol", 0.0))
    except (TypeError, ValueError):
        failures.append("reference tolerancePolicy.atol/rtol must be numeric")
        atol = 0.0
        rtol = 0.0

    actual_generated = transcript.get("generatedTokenIds") or {}
    reference_generated = reference.get("generatedTokenIds") or {}
    if actual_generated.get("sha256") != reference_generated.get("sha256"):
        failures.append(
            "cslTranscript.generatedTokenIds.sha256 must match "
            "reference decodeTranscript.generatedTokenIds.sha256"
        )

    if transcript.get("requestedDecodeSteps") != reference.get("requestedDecodeSteps"):
        failures.append(
            "cslTranscript.requestedDecodeSteps must match reference export"
        )
    if transcript.get("actualDecodeSteps") != reference.get("actualDecodeSteps"):
        failures.append(
            "cslTranscript.actualDecodeSteps must match reference export"
        )
    if transcript.get("stopReason") != reference.get("stopReason"):
        failures.append("cslTranscript.stopReason must match reference export")

    actual_logits = transcript.get("logitsDigests") or []
    reference_logits = reference.get("logitsDigests") or []
    if len(actual_logits) != len(reference_logits):
        failures.append(
            "cslTranscript.logitsDigests length must match reference export"
        )
        return
    metadata_keys = (
        "stepIndex",
        "phase",
        "contextTokenCount",
        "selectedTokenId",
        "dtype",
        "shape",
    )
    for index, (actual, reference_step) in enumerate(
        zip(actual_logits, reference_logits, strict=True)
    ):
        if not isinstance(actual, dict) or not isinstance(reference_step, dict):
            failures.append(f"logitsDigests[{index}] entries must be objects")
            continue
        for key in metadata_keys:
            if actual.get(key) != reference_step.get(key):
                failures.append(
                    f"cslTranscript.logitsDigests[{index}].{key} must match "
                    "reference export"
                )
                break
        actual_sha = actual.get("sha256")
        reference_sha = reference_step.get("sha256")
        if comparison == "sha256_exact":
            if actual_sha != reference_sha:
                failures.append(
                    f"cslTranscript.logitsDigests[{index}].sha256 must match "
                    "reference export under sha256_exact policy"
                )
            continue
        if comparison != "max_abs":
            failures.append(
                f"unsupported reference tolerancePolicy.comparison={comparison!r}"
            )
            return
        if actual_sha == reference_sha:
            continue
        actual_path_text = actual.get("path")
        reference_path_text = reference_step.get("path")
        if not isinstance(actual_path_text, str) or not isinstance(
            reference_path_text,
            str,
        ):
            failures.append(
                f"logitsDigests[{index}] path fields are required for max_abs "
                "comparison when hashes differ"
            )
            continue
        actual_path = resolve(actual_path_text)
        reference_path = resolve(reference_path_text)
        if not actual_path.is_file() or not reference_path.is_file():
            failures.append(
                f"logitsDigests[{index}] artifacts must exist for max_abs "
                "comparison"
            )
            continue
        try:
            passed, max_abs_err = compare_float32_files(
                actual_path,
                reference_path,
                atol=atol,
                rtol=rtol,
            )
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if not passed:
            failures.append(
                f"cslTranscript.logitsDigests[{index}] max_abs={max_abs_err:.6e} "
                f"exceeds tolerance atol={atol:.6e}, rtol={rtol:.6e}"
            )


def check_success_fields(
    receipt: dict[str, Any],
    failures: list[str],
    reference_export: dict[str, Any] | None,
) -> None:
    plan = receipt.get("loweringPlan") or {}
    if plan.get("status") != "ready_for_simfabric":
        failures.append(
            "loweringPlan.status="
            f"{plan.get('status')!r}, expected ready_for_simfabric"
        )
    if int(plan.get("missingOperationCount") or 0) != 0:
        failures.append("loweringPlan.missingOperationCount must be zero")
    if plan.get("unsupportedKernels"):
        failures.append("loweringPlan.unsupportedKernels must be empty")
    for index, stage in enumerate(plan.get("stages") or []):
        if stage.get("status") != "production_csl_kernel_available":
            failures.append(
                "loweringPlan.stages"
                f"[{index}].status={stage.get('status')!r}, "
                "expected production_csl_kernel_available"
            )
            break

    hostplan = receipt.get("hostPlanBundle") or {}
    if hostplan.get("status") != "hostplan_ready":
        failures.append(
            "hostPlanBundle.status="
            f"{hostplan.get('status')!r}, expected hostplan_ready"
        )
    for label in (
        "normalizedExecution",
        "hostPlan",
        "runtimeConfig",
        "memoryPlan",
        "simulatorPlan",
    ):
        linked = hostplan.get(label) or {}
        check_path_hash(
            f"hostPlanBundle.{label}",
            linked.get("path", ""),
            linked.get("sha256", ""),
            failures,
            required=True,
        )
    coverage = hostplan.get("compileInputCoverage") or {}
    if int(coverage.get("missingTargetCount") or 0) != 0:
        failures.append(
            "hostPlanBundle.compileInputCoverage.missingTargetCount must be zero"
        )
    weight_coverage = hostplan.get("weightMappingCoverage") or {}
    if weight_coverage.get("status") != "complete":
        failures.append(
            "hostPlanBundle.weightMappingCoverage.status must be complete"
        )
    if int(weight_coverage.get("mappedWeightCount") or 0) <= 0:
        failures.append(
            "hostPlanBundle.weightMappingCoverage.mappedWeightCount must be positive"
        )
    if int(weight_coverage.get("missingWeightCount") or 0) != 0:
        failures.append(
            "hostPlanBundle.weightMappingCoverage.missingWeightCount must be zero"
        )
    source_program = receipt.get("sourceProgram") or {}
    if "programBundle" not in source_program:
        failures.append("sourceProgram.programBundle must be present")
    else:
        linked = source_program.get("programBundle") or {}
        check_path_hash(
            "sourceProgram.programBundle",
            linked.get("path", ""),
            linked.get("sha256", ""),
            failures,
            required=True,
        )
    if not source_program.get("wgslModulesSha256"):
        failures.append("sourceProgram.wgslModulesSha256 must be present")
    if not source_program.get("hostEntrypointSha256"):
        failures.append("sourceProgram.hostEntrypointSha256 must be present")
    if (
        weight_coverage.get("manifestSha256")
        != source_program.get("manifestSha256")
    ):
        failures.append(
            "hostPlanBundle.weightMappingCoverage.manifestSha256 must match sourceProgram"
        )
    if (
        weight_coverage.get("weightSetSha256")
        != source_program.get("weightSha256")
    ):
        failures.append(
            "hostPlanBundle.weightMappingCoverage.weightSetSha256 must match sourceProgram"
        )
    host_io_coverage = hostplan.get("hostIoLayoutCoverage") or {}
    if host_io_coverage.get("status") != "complete":
        failures.append(
            "hostPlanBundle.hostIoLayoutCoverage.status must be complete"
        )
    if int(host_io_coverage.get("entryCount") or 0) <= 0:
        failures.append(
            "hostPlanBundle.hostIoLayoutCoverage.entryCount must be positive"
        )
    if host_io_coverage.get("missingRoles"):
        failures.append(
            "hostPlanBundle.hostIoLayoutCoverage.missingRoles must be empty"
        )
    if int(host_io_coverage.get("mappedWeightEntryCount") or 0) <= 0:
        failures.append(
            "hostPlanBundle.hostIoLayoutCoverage.mappedWeightEntryCount "
            "must be positive"
        )
    if int(host_io_coverage.get("stateBufferEntryCount") or 0) <= 0:
        failures.append(
            "hostPlanBundle.hostIoLayoutCoverage.stateBufferEntryCount "
            "must be positive"
        )
    if (
        host_io_coverage.get("runtimeConfigSha256")
        != weight_coverage.get("runtimeConfigSha256")
    ):
        failures.append(
            "hostPlanBundle.hostIoLayoutCoverage.runtimeConfigSha256 must "
            "match weightMappingCoverage"
        )
    driver_result = hostplan.get("simulatorDriverResult") or {}
    check_path_hash(
        "hostPlanBundle.simulatorDriverResult",
        driver_result.get("path", ""),
        driver_result.get("sha256", ""),
        failures,
        required=True,
    )
    if driver_result.get("compileStatus") != "succeeded":
        failures.append(
            "hostPlanBundle.simulatorDriverResult.compileStatus must be succeeded"
        )
    if driver_result.get("runStatus") != "succeeded":
        failures.append(
            "hostPlanBundle.simulatorDriverResult.runStatus must be succeeded"
        )

    if receipt.get("status") != "simulator_success":
        failures.append(f"status={receipt.get('status')!r}, expected simulator_success")
    run = receipt.get("simulatorRun") or {}
    if run.get("status") != "succeeded":
        failures.append(
            f"simulatorRun.status={run.get('status')!r}, expected succeeded"
        )
    if run.get("kernelIsStub") is not False:
        failures.append("simulatorRun.kernelIsStub must be false")
    if run.get("executionTarget") != "simfabric":
        failures.append(
            "simulatorRun.executionTarget="
            f"{run.get('executionTarget')!r}, expected simfabric"
        )
    if run.get("compileStatus") != "succeeded":
        failures.append(
            "simulatorRun.compileStatus="
            f"{run.get('compileStatus')!r}, expected succeeded"
        )
    driver_result = run.get("driverResult") or {}
    check_path_hash(
        "simulatorRun.driverResult",
        driver_result.get("path", ""),
        driver_result.get("sha256", ""),
        failures,
        required=True,
    )
    check_path_hash(
        "simulatorRun.trace",
        run.get("tracePath", ""),
        run.get("traceSha256", ""),
        failures,
        required=True,
    )

    transcript = receipt.get("cslTranscript") or {}
    if transcript.get("status") != "output_ready":
        failures.append("cslTranscript.status must be output_ready")
    if transcript.get("actualDecodeSteps") != (
        receipt.get("decodeRequest") or {}
    ).get("expectedActualDecodeSteps"):
        failures.append("cslTranscript.actualDecodeSteps differs from request")
    if transcript.get("stopReason") != (
        receipt.get("decodeRequest") or {}
    ).get("expectedStopReason"):
        failures.append("cslTranscript.stopReason differs from request")
    check_path_hash(
        "cslTranscript.transcript",
        (transcript.get("transcript") or {}).get("path", ""),
        (transcript.get("transcript") or {}).get("sha256", ""),
        failures,
        required=True,
    )
    check_path_hash(
        "cslTranscript.generatedTokenIds",
        (transcript.get("generatedTokenIds") or {}).get("path", ""),
        (transcript.get("generatedTokenIds") or {}).get("sha256", ""),
        failures,
        required=True,
    )
    for index, digest in enumerate(transcript.get("logitsDigests") or []):
        check_path_hash(
            f"cslTranscript.logitsDigests[{index}]",
            digest.get("path", ""),
            digest.get("sha256", ""),
            failures,
            required=True,
        )
    if len(transcript.get("logitsDigests") or []) != transcript.get(
        "actualDecodeSteps"
    ):
        failures.append(
            "cslTranscript.logitsDigests length differs from actualDecodeSteps"
        )

    kv = receipt.get("kvCacheEvidence") or {}
    if kv.get("realKvCache") is not True:
        failures.append("kvCacheEvidence.realKvCache must be true")
    if int(kv.get("cacheWriteCount") or 0) <= 0:
        failures.append("kvCacheEvidence.cacheWriteCount must be positive")
    if int(kv.get("cacheReadCount") or 0) <= 0:
        failures.append("kvCacheEvidence.cacheReadCount must be positive")
    coverage = kv.get("layerSpanCoverage") or {}
    if coverage.get("coveredLayerCount") != coverage.get("layerCount"):
        failures.append("kvCacheEvidence.layerSpanCoverage is incomplete")
    actual_steps = transcript.get("actualDecodeSteps")
    if isinstance(actual_steps, int) and len(kv.get("stepStateDigests") or []) != actual_steps:
        failures.append("kvCacheEvidence.stepStateDigests length differs from actualDecodeSteps")
    source = receipt.get("sourceProgram") or {}
    if source.get("executionDepth") != "full_model":
        failures.append("sourceProgram.executionDepth must be full_model")
    if reference_export is None:
        failures.append(
            "reference export is required for simulator_success generated-token "
            "parity and logits tolerance comparison"
        )
    else:
        check_transcript_reference_parity(receipt, reference_export, failures)


def main() -> int:
    args = parse_args()
    try:
        receipt = load_json(resolve(args.receipt))
        schema = load_json(resolve(args.schema))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: Doe CSL INT4 PLE transcript gate: {exc}")
        return 1

    failures = schema_failures(receipt, schema)
    export = None
    if args.reference_export:
        try:
            export = load_json(resolve(args.reference_export))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"reference export unreadable: {exc}")
        else:
            check_reference_identity(receipt, export, failures)

    if args.require_simulator_success:
        check_success_fields(receipt, failures, export)

    if failures:
        print("FAIL: Doe CSL INT4 PLE transcript gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(
        "PASS: Doe CSL INT4 PLE transcript gate "
        f"(model={receipt.get('modelId', '?')}, status={receipt.get('status', '?')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
