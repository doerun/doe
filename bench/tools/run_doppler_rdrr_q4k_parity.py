#!/usr/bin/env python3
"""Run Doppler RDRR Q4_K_M extraction plus smoke-depth parity."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json"
DEFAULT_OUT = "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json"
DEFAULT_PROBE_OUT = (
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json"
)
DEFAULT_EXTRACTION_OUT = (
    "bench/out/doppler-rdrr/"
    "gemma-4-e2b-int4ple-q4k-extraction.json"
)
DEFAULT_PARITY_OUT = (
    "bench/out/doppler-rdrr/"
    "gemma-4-e2b-int4ple-rdrr-l1-parity.json"
)
DEFAULT_WEIGHTS_DIR = "bench/out/gemma-4-e2b-rdrr-int4ple-weights"
DEFAULT_WEIGHTS_AUDIT = (
    "bench/out/weights-audit/"
    "gemma-4-e2b-rdrr-int4ple-weights-audit.json"
)
DEFAULT_LANE_OUT_DIR = (
    "bench/out/doppler-rdrr/"
    "gemma-4-e2b-int4ple-rdrr-l1-parity-work"
)


def default_out_json(num_layers: int) -> str:
    if num_layers == 1:
        return DEFAULT_OUT
    return (
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-q4k-parity-L{num_layers}.json"
    )


def default_parity_out(num_layers: int) -> str:
    if num_layers == 1:
        return DEFAULT_PARITY_OUT
    return (
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-rdrr-l{num_layers}-parity.json"
    )


def default_lane_out_dir(num_layers: int) -> str:
    if num_layers == 1:
        return DEFAULT_LANE_OUT_DIR
    return (
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-rdrr-l{num_layers}-parity-work"
    )


def l_verdict(num_layers: int, suffix: str) -> str:
    return f"rdrr_q4k_l{num_layers}_{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--num-layers",
        type=int,
        default=1,
        help="Smoke-contract chain depth. L1 remains the default bundle lane.",
    )
    parser.add_argument(
        "--artifact-root",
        default=os.environ.get("DOE_GEMMA4_E2B_RDRR_ROOT", ""),
        help="Override artifactRoot from the RDRR fixture.",
    )
    parser.add_argument("--weights-dir", default=DEFAULT_WEIGHTS_DIR)
    parser.add_argument("--probe-out", default=DEFAULT_PROBE_OUT)
    parser.add_argument("--extraction-out", default=DEFAULT_EXTRACTION_OUT)
    parser.add_argument("--parity-out", default="")
    parser.add_argument("--weights-audit-out", default=DEFAULT_WEIGHTS_AUDIT)
    parser.add_argument("--lane-out-dir", default="")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()
    if args.num_layers < 1:
        parser.error("--num-layers must be >= 1")
    if not args.parity_out:
        args.parity_out = default_parity_out(args.num_layers)
    if not args.lane_out_dir:
        args.lane_out_dir = default_lane_out_dir(args.num_layers)
    if not args.out_json:
        args.out_json = default_out_json(args.num_layers)
    return args


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(path)}")


def run_step(name: str, argv: list[str], timeout: int) -> dict[str, Any]:
    start = time.time()
    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "step": name,
        "command": argv,
        "status": "passed" if proc.returncode == 0 else "failed",
        "returnCode": proc.returncode,
        "stdoutTail": proc.stdout[-800:],
        "stderrTail": proc.stderr[-800:],
        "elapsedMs": (time.time() - start) * 1000.0,
    }


def base_payload(args: argparse.Namespace, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_doppler_rdrr_q4k_parity",
        "numLayers": args.num_layers,
        "fixturePath": args.fixture,
        "artifactRootOverride": args.artifact_root or None,
        "probePath": args.probe_out,
        "extractionPath": args.extraction_out,
        "parityVerdictPath": args.parity_out,
        "weightsDir": args.weights_dir,
        "weightsAuditPath": args.weights_audit_out,
        "laneOutputDir": args.lane_out_dir,
        "steps": steps,
        "claimScope": {
            "claimable": (
                "Doppler RDRR Q4_K_M dequantized slices feed Doe's "
                f"existing Gemma-4 E2B L{args.num_layers} "
                "smoke-contract WebGPU-vs-CSL "
                "parity harness."
            ),
            "notClaimable": [
                "Doppler production inference output parity",
                "Full Gemma-4 E2B execution from the RDRR artifact",
                "Manifest-shape execution",
                "31B real weights",
                "26B/A4B MoE",
                "Cerebras hardware execution",
            ],
        },
    }


def finalize_from_artifacts(
    args: argparse.Namespace,
    steps: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    probe = read_json_if_present(resolve(args.probe_out)) or {}
    extraction = read_json_if_present(resolve(args.extraction_out)) or {}
    parity = read_json_if_present(resolve(args.parity_out)) or {}
    payload = base_payload(args, steps)
    payload["modelId"] = (
        parity.get("modelId")
        or extraction.get("modelId")
        or probe.get("modelId")
    )

    probe_status = probe.get("status")
    extraction_status = extraction.get("status")
    parity_verdict = parity.get("verdict")
    parity_summary = parity.get("parity") or {}
    if probe_status == "blocked_artifact_absent":
        payload.update({
            "status": "blocked",
            "verdict": "blocked_artifact_absent",
            "blocker": "doppler_rdrr_artifact_absent",
        })
        return payload, 0
    if any(step["status"] == "failed" for step in steps):
        payload.update({
            "status": "failed",
            "verdict": l_verdict(args.num_layers, "parity_failed"),
            "blocker": "step_failed",
        })
        return payload, 1
    if extraction_status == "blocked":
        payload.update({
            "status": "blocked",
            "verdict": extraction.get("verdict") or "blocked_extraction",
            "blocker": extraction.get("blocker") or "extraction_blocked",
        })
        return payload, 0
    if parity_verdict == "parity_passed":
        payload.update({
            "status": "succeeded",
            "verdict": l_verdict(args.num_layers, "parity_passed"),
        })
        exit_code = 0
    elif parity_verdict == "lane_incomplete":
        payload.update({
            "status": "blocked",
            "verdict": l_verdict(args.num_layers, "parity_lane_incomplete"),
            "blocker": "runtime_lane_incomplete",
        })
        exit_code = 0
    else:
        payload.update({
            "status": "failed",
            "verdict": l_verdict(args.num_layers, "parity_failed"),
            "blocker": parity_verdict or "parity_verdict_absent",
        })
        exit_code = 1

    payload["structuralProbeVerdict"] = probe.get("verdict")
    payload["extractionVerdict"] = extraction.get("verdict")
    payload["weightSetSha256"] = extraction.get("weightSetSha256")
    payload["parityHarnessVerdict"] = parity_verdict
    payload["paritySummary"] = {
        "outputDigestMatch": bool(parity_summary.get("outputDigestMatch")),
        "tolerancePassed": bool(parity_summary.get("tolerancePassed")),
        "atol": parity_summary.get("atol"),
        "rtol": parity_summary.get("rtol"),
        "layersCompared": parity_summary.get("layersCompared"),
        "maxAbsErrAcrossLayers": parity_summary.get("maxAbsErrAcrossLayers"),
        "maxRelErrAcrossLayers": parity_summary.get("maxRelErrAcrossLayers"),
        "maxAllowedErrAcrossLayers": parity_summary.get("maxAllowedErrAcrossLayers"),
        "meanAbsErrAcrossLayers": parity_summary.get("meanAbsErrAcrossLayers"),
    }
    payload["comparisonToReferenceWeights"] = (
        extraction.get("comparisonToReferenceWeights")
    )
    payload["promotionCriteriaMet"] = {
        "structuralProbePassed": probe.get("verdict")
        == "rdrr_structural_probe_passed",
        "q4kSmokeSlicesExtracted": extraction.get("verdict")
        == "rdrr_q4k_smoke_contract_extracted",
        "weightsAuditPassed": bool(parity.get("weightsAuditPassed")),
        "crossRuntimeParityPassed": parity_verdict == "parity_passed",
        "fullModelDepthExecuted": False,
        "productionInferencePathExecuted": False,
        "hardwareExecuted": False,
    }
    return payload, exit_code


def main() -> int:
    args = parse_args()
    steps: list[dict[str, Any]] = []
    probe_cmd = [
        "python3",
        "bench/tools/probe_doppler_rdrr_artifact.py",
        "--fixture",
        args.fixture,
        "--out-json",
        args.probe_out,
    ]
    if args.artifact_root:
        probe_cmd.extend(["--artifact-root", args.artifact_root])
    steps.append(run_step("doppler-rdrr-structural-probe", probe_cmd, 600))
    probe = read_json_if_present(resolve(args.probe_out)) or {}
    if steps[-1]["status"] != "passed" or probe.get("status") == "blocked_artifact_absent":
        payload, exit_code = finalize_from_artifacts(args, steps)
        write_json(resolve(args.out_json), payload)
        print(f"rdrr q4k parity: verdict={payload.get('verdict')}")
        return exit_code

    extraction_cmd = [
        "python3",
        "bench/tools/extract_gemma4_e2b_rdrr_weight_slices.py",
        "--fixture",
        args.fixture,
        "--out-dir",
        args.weights_dir,
        "--out-json",
        args.extraction_out,
    ]
    if args.artifact_root:
        extraction_cmd.extend(["--artifact-root", args.artifact_root])
    steps.append(run_step("doppler-rdrr-q4k-extraction", extraction_cmd, 600))
    if steps[-1]["status"] != "passed":
        payload, exit_code = finalize_from_artifacts(args, steps)
        write_json(resolve(args.out_json), payload)
        print(f"rdrr q4k parity: verdict={payload.get('verdict')}")
        return exit_code

    parity_cmd = [
        "python3",
        "bench/tools/run_e2b_real_weight_l1_parity.py",
        "--fixture",
        "config/gemma-4-e2b-real-weight-fixture.json",
        "--weights-dir",
        args.weights_dir,
        "--num-layers",
        str(args.num_layers),
        "--weight-set-pin-mode",
        "record-only",
        "--weights-source-label",
        "doppler_rdrr_q4k_int4ple",
        "--weights-audit-out",
        args.weights_audit_out,
        "--lane-out-dir",
        args.lane_out_dir,
        "--out-json",
        args.parity_out,
    ]
    steps.append(
        run_step(
            f"doppler-rdrr-q4k-l{args.num_layers}-parity",
            parity_cmd,
            2400,
        )
    )
    payload, exit_code = finalize_from_artifacts(args, steps)
    write_json(resolve(args.out_json), payload)
    print(f"rdrr q4k parity: verdict={payload.get('verdict')}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
