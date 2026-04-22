#!/usr/bin/env python3
"""Bind a Doppler INT4 PLE export into Doe CSL parity receipt shape."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_bool(raw: str) -> bool:
    value = raw.lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {raw!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-export", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--export-schema",
        default="config/doppler-int4ple-reference-export.schema.json",
    )
    parser.add_argument(
        "--parity-schema",
        default="config/doe-csl-reference-parity.schema.json",
    )
    parser.add_argument("--csl-trace")
    parser.add_argument("--csl-output")
    parser.add_argument("--csl-transcript-receipt")
    parser.add_argument(
        "--csl-transcript-schema",
        default="config/doe-csl-int4ple-transcript.schema.json",
    )
    parser.add_argument("--csl-weight-sha256")
    parser.add_argument("--csl-status")
    parser.add_argument(
        "--kernel-stage",
        default=None,
    )
    parser.add_argument("--kernel-is-stub", type=parse_bool, default=None)
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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def schema_failures(data: Any, schema: Any) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(data),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    ]


def parity_output_from_export(tensor: dict[str, Any]) -> dict[str, Any]:
    result = {
        "dtype": tensor["dtype"],
        "shape": tensor["shape"],
        "path": tensor["path"],
        "sha256": tensor["sha256"],
    }
    if "preview" in tensor:
        result["preview"] = tensor["preview"]
    return result


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
        "decodeStepsProduced": transcript.get("decodeStepsProduced", 0),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": sha256_json(transcript.get("logitsDigests", [])),
    }


def compare_f32_outputs(
    reference_path: Path,
    csl_path: Path,
    atol: float,
) -> tuple[bool, float]:
    import numpy as np

    reference = np.fromfile(reference_path, dtype=np.float32)
    csl = np.fromfile(csl_path, dtype=np.float32)
    if reference.shape != csl.shape:
        return False, float("inf")
    if reference.size == 0:
        return False, float("inf")
    max_abs = float(np.max(np.abs(reference - csl)))
    return max_abs <= atol, max_abs


def pending_csl_run(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "tracePath": "pending",
        "traceSha256": "pending",
        "status": "pending_csl_output",
        "kernelStage": args.kernel_stage or "pending_full_int4ple_csl_lowering",
        "kernelIsStub": True,
    }


def trace_source_program(trace: dict[str, Any]) -> dict[str, Any]:
    source = trace.get("sourceProgram", {})
    return source if isinstance(source, dict) else {}


def trace_value_matches(
    trace_source: dict[str, Any],
    trace_key: str,
    expected: Any,
) -> bool:
    return bool(expected) and trace_source.get(trace_key) == expected


def trace_full_model_depth_executed(trace: dict[str, Any]) -> bool:
    executed = trace.get("executedRun", {})
    if isinstance(executed, dict) and executed.get("fullModelDepthExecuted") is True:
        return True
    source = trace_source_program(trace)
    if source.get("executionDepth") == "full_model":
        return True
    model_execution = trace.get("modelExecution", {})
    return isinstance(model_execution, dict) and (
        model_execution.get("fullModelDepthExecuted") is True
    )


def transcript_digest_from_csl(receipt: dict[str, Any]) -> dict[str, Any]:
    transcript = receipt.get("cslTranscript") or {}
    linked = transcript.get("transcript") or {}
    generated = transcript.get("generatedTokenIds") or {}
    return {
        "path": linked.get("path", "pending"),
        "sha256": linked.get("sha256", "pending"),
        "requestedDecodeSteps": transcript.get("requestedDecodeSteps", 0),
        "actualDecodeSteps": transcript.get("actualDecodeSteps", 0),
        "stopReason": transcript.get("stopReason", "pending"),
        "decodeStepsProduced": transcript.get("actualDecodeSteps", 0),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": sha256_json(transcript.get("logitsDigests", [])),
    }


def transcript_token_ids_match(
    export: dict[str, Any],
    csl_receipt: dict[str, Any],
) -> bool:
    reference = export.get("decodeTranscript") or {}
    csl = csl_receipt.get("cslTranscript") or {}
    ref_tokens = reference.get("generatedTokenIds") or {}
    csl_tokens = csl.get("generatedTokenIds") or {}
    return (
        reference.get("requestedDecodeSteps") == csl.get("requestedDecodeSteps")
        and reference.get("actualDecodeSteps") == csl.get("actualDecodeSteps")
        and reference.get("stopReason") == csl.get("stopReason")
        and ref_tokens.get("sha256") == csl_tokens.get("sha256")
    )


def compare_transcript_logits(
    export: dict[str, Any],
    csl_receipt: dict[str, Any],
    atol: float,
) -> tuple[bool, float | None]:
    reference_steps = (export.get("decodeTranscript") or {}).get("logitsDigests") or []
    csl_steps = (csl_receipt.get("cslTranscript") or {}).get("logitsDigests") or []
    if len(reference_steps) == 0 or len(reference_steps) != len(csl_steps):
        return False, None
    max_abs: float | None = None
    for ref_step, csl_step in zip(reference_steps, csl_steps, strict=True):
        for key in ("stepIndex", "phase", "selectedTokenId"):
            if ref_step.get(key) != csl_step.get(key):
                return False, max_abs
        if ref_step.get("shape") != csl_step.get("shape"):
            return False, max_abs
        if ref_step.get("sha256") == csl_step.get("sha256"):
            step_abs = 0.0
        else:
            ref_path = resolve(ref_step.get("path", ""))
            csl_path = resolve(csl_step.get("path", ""))
            if not ref_path.is_file() or not csl_path.is_file():
                return False, max_abs
            passed, step_abs = compare_f32_outputs(ref_path, csl_path, atol)
            if not passed:
                max_abs = step_abs if max_abs is None else max(max_abs, step_abs)
                return False, max_abs
        max_abs = step_abs if max_abs is None else max(max_abs, step_abs)
    return True, max_abs


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


def build_receipt(args: argparse.Namespace, export: dict[str, Any]) -> dict[str, Any]:
    tensor = export["tensorDigest"]
    if export.get("exportStatus") != "output_ready":
        raise ValueError("reference export must have exportStatus=output_ready")
    if tensor.get("status") != "output_ready":
        raise ValueError("reference tensorDigest must have status=output_ready")

    csl_output_bound = args.csl_output is not None
    if csl_output_bound and args.csl_trace is None:
        raise ValueError("--csl-output requires --csl-trace")
    csl_transcript_receipt_bound = args.csl_transcript_receipt is not None

    reference_output = parity_output_from_export(tensor)
    reference_transcript = parity_transcript_from_export(export)
    tolerance = export.get("tolerancePolicy", {})
    atol = float(tolerance.get("atol", 0.0))
    rtol = float(tolerance.get("rtol", 0.0))

    csl_run = pending_csl_run(args)
    output_hash_match = False
    parity_passed = False
    max_abs_err: float | None = None
    same_manifest_hash = True
    same_graph_hash = True
    trace_input_matched = False
    full_model_depth_executed = False
    csl_decode_transcript_bound = False
    token_ids_match = False
    per_step_logits_parity_passed = False
    real_kv_cache = False
    csl_transcript_digest: dict[str, Any] | None = None
    csl_transcript_blocker: str | None = None
    csl_weight_matched = (
        args.csl_weight_sha256 is not None
        and args.csl_weight_sha256 == export.get("weightSetSha256")
    )

    if csl_transcript_receipt_bound:
        transcript_path = resolve(args.csl_transcript_receipt)
        if not transcript_path.is_file():
            raise FileNotFoundError(f"CSL transcript receipt not found: {transcript_path}")
        transcript_receipt = load_json(transcript_path)
        transcript_source = transcript_receipt.get("sourceProgram") or {}
        same_manifest_hash = trace_value_matches(
            transcript_source,
            "manifestSha256",
            export["manifestSha256"],
        )
        same_graph_hash = trace_value_matches(
            transcript_source,
            "graphSha256",
            export["executionGraphSha256"],
        )
        trace_input_matched = trace_value_matches(
            transcript_source,
            "inputSetSha256",
            export["inputSetSha256"],
        )
        csl_weight_matched = trace_value_matches(
            transcript_source,
            "weightSha256",
            export["weightSetSha256"],
        )
        blocker_text = transcript_receipt.get("blocker")
        if isinstance(blocker_text, str) and blocker_text:
            csl_transcript_blocker = blocker_text
        simulator = transcript_receipt.get("simulatorRun") or {}
        run_reason = simulator.get("runReason") if isinstance(simulator, dict) else None
        if csl_transcript_blocker is None and isinstance(run_reason, str):
            csl_transcript_blocker = run_reason
        csl_transcript = transcript_receipt.get("cslTranscript") or {}
        csl_decode_transcript_bound = (
            transcript_receipt.get("status") == "simulator_success"
            and csl_transcript.get("status") == "output_ready"
        )
        token_ids_match = (
            csl_decode_transcript_bound
            and transcript_token_ids_match(export, transcript_receipt)
        )
        if csl_decode_transcript_bound:
            per_step_logits_parity_passed, max_abs_err = compare_transcript_logits(
                export,
                transcript_receipt,
                atol,
            )
        real_kv_cache = real_kv_cache_used(transcript_receipt)
        full_model_depth_executed = (
            transcript_source.get("executionDepth") == "full_model"
            and csl_decode_transcript_bound
            and real_kv_cache
        )
        csl_transcript_digest = transcript_digest_from_csl(transcript_receipt)
        csl_run = {
            "tracePath": repo_relative(transcript_path),
            "traceSha256": sha256_file(transcript_path),
            "status": transcript_receipt.get("status", "unknown"),
            "kernelStage": simulator.get("kernelStage", "unknown_csl_stage"),
            "kernelIsStub": bool(simulator.get("kernelIsStub", True)),
            "decodeTranscript": csl_transcript_digest,
        }

    if csl_output_bound:
        csl_trace = resolve(args.csl_trace)
        csl_output = resolve(args.csl_output)
        if not csl_trace.is_file():
            raise FileNotFoundError(f"CSL trace not found: {csl_trace}")
        if not csl_output.is_file():
            raise FileNotFoundError(f"CSL output not found: {csl_output}")
        trace = load_json(csl_trace)
        executed_run = trace.get("executedRun", {})
        if not isinstance(executed_run, dict):
            executed_run = {}
        layer_block = trace.get("layerBlockSmoke", {})
        if not isinstance(layer_block, dict):
            layer_block = {}
        trace_source = trace_source_program(trace)
        same_manifest_hash = trace_value_matches(
            trace_source,
            "manifestSha256",
            export["manifestSha256"],
        )
        same_graph_hash = trace_value_matches(
            trace_source,
            "graphSha256",
            export["executionGraphSha256"],
        )
        trace_input_matched = trace_value_matches(
            trace_source,
            "inputSetSha256",
            export["inputSetSha256"],
        )
        trace_weight_matched = trace_value_matches(
            trace_source,
            "weightSha256",
            export["weightSetSha256"],
        )
        csl_weight_matched = csl_weight_matched and trace_weight_matched
        full_model_depth_executed = trace_full_model_depth_executed(trace)
        csl_output_sha = sha256_file(csl_output)
        output_hash_match = csl_output_sha == tensor.get("sha256")
        parity_passed, max_abs_err = compare_f32_outputs(
            resolve(tensor["path"]),
            csl_output,
            atol,
        )
        kernel_is_stub = (
            args.kernel_is_stub
            if args.kernel_is_stub is not None
            else bool(layer_block.get("kernelIsStub", True))
        )
        csl_run = {
            "tracePath": repo_relative(csl_trace),
            "traceSha256": sha256_file(csl_trace),
            "status": args.csl_status or executed_run.get("status", "unknown"),
            "kernelStage": (
                args.kernel_stage
                or layer_block.get("kernelStage")
                or "unknown_csl_stage"
            ),
            "kernelIsStub": kernel_is_stub,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": atol,
                "rtol": rtol,
                "passed": parity_passed,
            },
            "output": {
                "dtype": tensor["dtype"],
                "shape": tensor["shape"],
                "path": repo_relative(csl_output),
                "sha256": csl_output_sha,
            },
        }

    comparison_status = "pending_csl_output_hash"
    if reference_transcript is not None:
        blocker = (
            "Doe CSL simfabric bounded prefill+decode transcript has not "
            "been produced for the production Doppler INT4 PLE source program."
        )
    else:
        blocker = (
            "Doe CSL simfabric final_logits output has not been produced for "
            "the production Doppler INT4 PLE source program."
        )
    if csl_output_bound or csl_transcript_receipt_bound:
        comparison_ready = (
            same_manifest_hash
            and same_graph_hash
            and trace_input_matched
            and full_model_depth_executed
            and (parity_passed or per_step_logits_parity_passed)
            and csl_weight_matched
            and (not reference_transcript or csl_decode_transcript_bound)
            and (not reference_transcript or token_ids_match)
            and (not reference_transcript or real_kv_cache)
            and not csl_run["kernelIsStub"]
        )
        comparison_status = "passed" if comparison_ready else "failed"
        blocker = ""
        if not same_manifest_hash:
            blocker = "CSL trace manifest hash does not match the export."
        elif not same_graph_hash:
            blocker = "CSL trace graph hash does not match the export."
        elif not trace_input_matched:
            blocker = "CSL trace input set hash does not match the export."
        elif reference_transcript and not csl_decode_transcript_bound:
            blocker = (
                csl_transcript_blocker
                or "CSL bounded decode transcript is not output_ready."
            )
        elif reference_transcript and not token_ids_match:
            blocker = "CSL generated token IDs or early-stop contract do not match."
        elif reference_transcript and not per_step_logits_parity_passed:
            blocker = "CSL per-step logits are outside tolerance or unavailable."
        elif reference_transcript and not real_kv_cache:
            blocker = "CSL receipt does not prove real KV/cache behavior."
        elif not full_model_depth_executed:
            blocker = "CSL trace does not prove full-model depth execution."
        elif not reference_transcript and not parity_passed:
            blocker = "CSL final_logits output is outside tolerance."
        elif not csl_weight_matched:
            blocker = "CSL weight identity was not proven against the export."
        elif csl_run["kernelIsStub"]:
            blocker = "CSL kernel stage is still marked as stub."

    comparison: dict[str, Any] = {
        "status": comparison_status,
        "sameManifestHash": same_manifest_hash,
        "sameGraphHash": same_graph_hash,
        "outputHashMatch": output_hash_match,
        "tokenIdsMatch": token_ids_match,
        "perStepLogitsParityPassed": per_step_logits_parity_passed,
        "realKvCacheUsed": real_kv_cache,
        "atol": atol,
    }
    if max_abs_err is not None:
        comparison["maxAbsErr"] = max_abs_err
    if blocker:
        comparison["blocker"] = blocker

    reference_run: dict[str, Any] = {
        "producer": export["producer"]["runtime"],
        "status": "output_ready",
        "inputsSynthetic": export["inputsSynthetic"],
        "weightsSynthetic": export["weightsSynthetic"],
        "inputSetSha256": export["inputSetSha256"],
        "output": reference_output,
    }
    if reference_transcript is not None:
        reference_run["decodeTranscript"] = reference_transcript

    source_program = {
        "authoringSurface": "doppler_execution_v1",
        "manifestPath": export["manifestPath"],
        "manifestSha256": export["manifestSha256"],
        "graphPath": export["executionGraph"]["path"],
        "graphSha256": export["executionGraphSha256"],
        "weightSetId": export["weightSetId"],
        "weightSha256": export["weightSetSha256"],
    }
    if csl_transcript_receipt_bound:
        for key in (
            "programBundle",
            "programContractVersion",
            "wgslModulesSha256",
            "hostEntrypointSha256",
            "runtimeProfile",
            "captureProfile",
        ):
            if key in transcript_source:
                source_program[key] = transcript_source[key]

    return {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_reference_parity",
        "modelId": export["modelId"],
        "sourceProgram": source_program,
        "referenceRun": reference_run,
        "cslRun": csl_run,
        "comparison": comparison,
        "promotionCriteria": {
            "fullModelDepthExecuted": full_model_depth_executed,
            "manifestHashMatched": same_manifest_hash,
            "graphHashMatched": same_graph_hash,
            "weightHashMatched": csl_weight_matched,
            "externalReferenceOutputBound": True,
            "cslOutputHashBound": csl_output_bound or csl_decode_transcript_bound,
            "outputParityPassed": parity_passed or per_step_logits_parity_passed,
            "decodeTranscriptBound": csl_decode_transcript_bound,
            "tokenIdsMatched": token_ids_match,
            "perStepLogitsParityPassed": per_step_logits_parity_passed,
            "realKvCacheUsed": real_kv_cache,
            "stubStagesAbsent": not csl_run["kernelIsStub"],
            "syntheticInputsAbsent": export["inputsSynthetic"] is False,
            "syntheticWeightsAbsent": export["weightsSynthetic"] is False,
            "hardwareReceiptRequiredForHardwareClaim": True,
        },
    }


def main() -> int:
    args = parse_args()
    try:
        export = load_json(resolve(args.reference_export))
        export_schema = load_json(resolve(args.export_schema))
        parity_schema = load_json(resolve(args.parity_schema))
        if args.csl_transcript_receipt:
            transcript = load_json(resolve(args.csl_transcript_receipt))
            transcript_schema = load_json(resolve(args.csl_transcript_schema))
            transcript_failures = schema_failures(transcript, transcript_schema)
            if transcript_failures:
                print("FAIL: CSL transcript receipt schema validation")
                for failure in transcript_failures:
                    print(f"  {failure}")
                return 1
        failures = schema_failures(export, export_schema)
        if failures:
            print("FAIL: reference export schema validation")
            for failure in failures:
                print(f"  {failure}")
            return 1
        receipt = build_receipt(args, export)
        failures = schema_failures(receipt, parity_schema)
        if failures:
            print("FAIL: parity receipt schema validation")
            for failure in failures:
                print(f"  {failure}")
            return 1
        out_path = resolve(args.out)
        write_json(out_path, receipt)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: bind Doppler INT4 PLE reference: {exc}")
        return 1

    print(
        "PASS: bound Doppler INT4 PLE reference into Doe CSL parity "
        f"({repo_relative(resolve(args.out))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
