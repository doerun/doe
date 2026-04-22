#!/usr/bin/env python3
"""Prepare the Doe CSL INT4 PLE hardware receipt surface.

This tool does not claim hardware execution. It binds the current
Doppler/Doe parity receipts to the command shape a Cerebras endpoint
or WSC appliance run must use later, with endpoint redaction recorded
before any hardware_success receipt can land.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARITY_RECEIPT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-reference-parity.pending.json"
)
DEFAULT_TRANSCRIPT_RECEIPT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json"
)
DEFAULT_OUT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-hardware-receipt.pending.json"
)
DEFAULT_PROGRAM_BUNDLE = (
    "/home/x/deco/doppler/examples/program-bundles/"
    "gemma-4-e2b-it-q4k-ehf16-af32-int4ple.program-bundle.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parity-receipt", default=DEFAULT_PARITY_RECEIPT)
    parser.add_argument("--transcript-receipt", default=DEFAULT_TRANSCRIPT_RECEIPT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--schema",
        default="config/doe-csl-int4ple-hardware-receipt.schema.json",
    )
    parser.add_argument(
        "--execution-target",
        choices=["system", "wsc_appliance"],
        default="system",
    )
    parser.add_argument(
        "--program-bundle",
        default=DEFAULT_PROGRAM_BUNDLE,
        help="Program Bundle path to use in the redacted hardware rerun command.",
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def link(path: Path, source: str) -> dict[str, str]:
    return {
        "path": repo_relative(path),
        "sha256": sha256_file(path),
        "source": source,
    }


def transcript_digest(transcript: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": transcript.get("path", "pending"),
        "sha256": transcript.get("sha256", "pending"),
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "actualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "stopReason": transcript.get("stopReason", "pending"),
        "decodeStepsProduced": int(transcript.get("decodeStepsProduced") or 0),
        "generatedTokenIdsSha256": transcript.get(
            "generatedTokenIdsSha256",
            "pending",
        ),
        "logitsDigestSha256": transcript.get("logitsDigestSha256", "pending"),
    }


def csl_transcript_digest(receipt: dict[str, Any]) -> dict[str, Any]:
    transcript = receipt.get("cslTranscript") or {}
    linked = transcript.get("transcript") or {}
    generated = transcript.get("generatedTokenIds") or {}
    return {
        "path": linked.get("path", "pending"),
        "sha256": linked.get("sha256", "pending"),
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "actualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "stopReason": transcript.get("stopReason", "pending"),
        "decodeStepsProduced": int(transcript.get("actualDecodeSteps") or 0),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": hashlib.sha256(
            (json.dumps(transcript.get("logitsDigests", []), sort_keys=True) + "\n")
            .encode("utf-8")
        ).hexdigest(),
    }


def kv_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    kv = receipt.get("kvCacheEvidence") or {}
    coverage = kv.get("layerSpanCoverage") or {}
    return {
        "realKvCache": bool(kv.get("realKvCache")),
        "cacheReadCount": int(kv.get("cacheReadCount") or 0),
        "cacheWriteCount": int(kv.get("cacheWriteCount") or 0),
        "coveredLayerCount": int(coverage.get("coveredLayerCount") or 0),
        "layerCount": int(coverage.get("layerCount") or 0),
        "stepStateDigestCount": len(kv.get("stepStateDigests") or []),
    }


def hardware_command(args: argparse.Namespace) -> list[str]:
    base = [
        "env",
        "DOE_CSL_CMADDR=$DOE_CSL_CMADDR",
        "python3",
        "bench/tools/run_doe_csl_int4ple_transcript.py",
        "--program-bundle",
        args.program_bundle,
    ]
    if args.execution_target == "wsc_appliance":
        return [
            "python3",
            "runtime/zig/tools/csl_appliance_driver.py",
            "--system",
            "--runner-command",
            " ".join(base).replace("$DOE_CSL_CMADDR", "%CMADDR%"),
        ]
    return base


def build_receipt(
    args: argparse.Namespace,
    parity_path: Path,
    transcript_path: Path,
) -> dict[str, Any]:
    parity = load_json(parity_path)
    transcript_receipt = load_json(transcript_path)
    source = dict(parity.get("sourceProgram") or {})
    if "inputSetSha256" not in source:
        source["inputSetSha256"] = (parity.get("referenceRun") or {}).get(
            "inputSetSha256",
            "pending",
        )
    reference = parity.get("referenceRun") or {}
    comparison = parity.get("comparison") or {}
    criteria = parity.get("promotionCriteria") or {}
    simulator_ready = (
        comparison.get("status") == "passed"
        and criteria.get("fullModelDepthExecuted") is True
        and criteria.get("decodeTranscriptBound") is True
        and criteria.get("realKvCacheUsed") is True
    )
    csl_digest = csl_transcript_digest(transcript_receipt)
    kv = kv_summary(transcript_receipt)
    blocker = ""
    if not simulator_ready:
        blocker = (
            "hardware run waits for Doe-vs-Doppler simfabric parity with "
            "real token/logit/KV transcript evidence"
        )
    hardware_status = (
        "pending_endpoint_access" if simulator_ready else "pending_simulator_parity"
    )
    hardware_executed = hardware_status == "hardware_success"

    return {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_int4ple_hardware_receipt",
        "modelId": parity.get("modelId", "pending"),
        "sourceProgram": source,
        "referenceTranscript": transcript_digest(
            reference.get("decodeTranscript") or {}
        ),
        "simulatorParityReceipt": link(
            parity_path,
            "doe_csl_reference_parity",
        ),
        "simulatorTranscriptReceipt": link(
            transcript_path,
            "doe_csl_int4ple_transcript",
        ),
        "hardwareRun": {
            "status": hardware_status,
            "executionTarget": args.execution_target,
            "cmaddrProvided": False,
            "endpointRedaction": "$DOE_CSL_CMADDR",
            "command": hardware_command(args),
            "cslTranscript": csl_digest,
            "kvCacheEvidence": kv,
            "blocker": blocker,
        },
        "promotionCriteria": {
            "sameSourceIdentity": True,
            "simulatorParityPassed": simulator_ready,
            "hardwareExecuted": hardware_executed,
            "hardwareTranscriptBound": False,
            "tokenIdsMatched": False,
            "perStepLogitsParityPassed": False,
            "realKvCacheUsed": False,
            "endpointRedacted": True,
            "stubStagesAbsent": criteria.get("stubStagesAbsent") is True,
            "syntheticInputsAbsent": criteria.get("syntheticInputsAbsent") is True,
            "syntheticWeightsAbsent": criteria.get("syntheticWeightsAbsent") is True,
            "hardwareSuccessClaimable": False,
        },
        "claimBoundary": {
            "claimable": False,
            "scope": (
                "Hardware receipt preflight only. This is software evidence "
                "and an access request surface until hardwareRun.status is "
                "hardware_success and strict promotion criteria are true."
            ),
            "blockedUntil": [
                "Doe simfabric parity passes for the same Program Bundle",
                "Cerebras endpoint or WSC appliance access is available",
                "Hardware run emits matching token/logit/KV transcript evidence",
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
    try:
        parity_path = resolve(args.parity_receipt)
        transcript_path = resolve(args.transcript_receipt)
        schema = load_json(resolve(args.schema))
        receipt = build_receipt(args, parity_path, transcript_path)
        failures = schema_failures(receipt, schema)
        if failures:
            print("FAIL: INT4 PLE hardware receipt schema validation")
            for failure in failures:
                print(f"  {failure}")
            return 1
        out_path = resolve(args.out)
        write_json(out_path, receipt)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"FAIL: prepare INT4 PLE hardware receipt: {exc}")
        return 1
    print(f"PASS: prepared INT4 PLE hardware receipt ({repo_relative(out_path)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
