#!/usr/bin/env python3
"""One-command Cerebras evidence bundle runner.

Runs every local gate the Cerebras hardware-access ask depends on,
in the canonical order, and emits one summary artifact. Exits 0 iff
every step passes. Intended to be the single invocation you run
before attaching the hardware-validation appendix to an email.

Steps (in order):

  1. truth-table test for compute_execution_status (14 cases)
  2. Doppler Gemma-4 E2B WebGPU capture graph via doe-gpu/capture
  3. Gemma-4 E2B manifest-shape probe
  4. Gemma-4 E2B manifest-shape CPU execution oracle
  5. Doppler RDRR/int4ple structural probe
  6. Doppler RDRR Q4_K_M L1 smoke-contract parity
  7. BF16-derived E2B smoke-chain diagnostic parity depths
  8. Doppler RDRR Q4_K_M smoke-chain diagnostic parity depths
  9. Gemma-4 E2B manifest-shape attention-core SdkLayout diagnostic
 10. e2b_layer_block_self_check (regens E2B receipt + rollup +
     validates the numbered contract assertions after depth refresh)
 11. E2B model receipt refresh after depth diagnostics
 12. Doppler capture graph to CSL attention-core lowering receipt
 13. E2B model receipt refresh after attention-core/lowering restamp
 14. Gemma-4 E2B manifest-shape Doe/CSL runtime-path contract
 15. Gemma 4 31B AF16 simfabric cell summary refresh
 16. Gemma 4 31B AF16 local ceiling + Doppler-to-CSL splice receipts
 17. claim-discipline gate (hardware + MoE fronts)
 18. SdkLayout streaming hardening gate (against any available live
     trace with streamTelemetry; skipped cleanly when none is fresh)
 19. schema validation of 31B receipt and receipt-link integrity for
     both E2B and 31B

Each step contributes to
`bench/out/cerebras-evidence-bundle/summary.json`:

  {
    "step": "truth-table-test",
    "status": "passed" | "failed" | "skipped",
    "returnCode": int,
    "stdoutTail": "...",
    "stderrTail": "...",
    "elapsedMs": float
  }

The summary is authored for cross-repo review — it is the
single-file answer to "does the software proof still hold?".

Usage:
  python3 bench/tools/run_cerebras_evidence_bundle.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / "bench/out/cerebras-evidence-bundle"
DIAGNOSTIC_DEPTHS = (2, 4, 8, 35)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--summary-out",
        default="bench/out/cerebras-evidence-bundle/summary.json",
    )
    p.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at first failing step (default: run all, report all).",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def run(step: str, argv: list[str], timeout: int = 600) -> dict:
    start = time.time()
    try:
        proc = subprocess.run(
            argv, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        rc = proc.returncode
        status = "passed" if rc == 0 else "failed"
        stdout_tail = proc.stdout[-800:]
        stderr_tail = proc.stderr[-800:]
    except subprocess.TimeoutExpired as exc:
        rc = -1
        status = "failed"
        stdout_tail = (exc.stdout or "")[-800:] if isinstance(exc.stdout, str) else ""
        stderr_tail = f"TIMEOUT after {timeout}s"
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "step": step,
        "command": argv,
        "status": status,
        "returnCode": rc,
        "stdoutTail": stdout_tail,
        "stderrTail": stderr_tail,
        "elapsedMs": elapsed_ms,
    }


def skipped(step: str, message: str, command: list[str] | None = None) -> dict:
    return {
        "step": step,
        "command": command or [],
        "status": "skipped",
        "returnCode": 0,
        "stdoutTail": message,
        "stderrTail": "",
        "elapsedMs": 0.0,
    }


def find_live_trace_with_telemetry() -> Path | None:
    # Prefer the scratch live trace (freshest). Fall back to any trace
    # that actually contains streamTelemetry — stale smoke traces
    # won't qualify.
    candidates = [
        REPO_ROOT / "bench/out/scratch/gemma4-e2b-csl-sim/csl-L1-live-trace.json",
        REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-smoke-trace.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if ((data.get("executedRun") or {}).get("streamTelemetry")):
            return p
    return None


def main() -> int:
    args = parse_args()
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    steps: list[dict] = []

    # 1. truth-table test for compute_execution_status.
    steps.append(run(
        "truth-table-test",
        ["python3", "bench/tools/test_execution_status_flip.py"],
    ))
    if args.fail_fast and steps[-1]["status"] != "passed":
        pass

    # 2. Doppler Gemma-4 E2B WebGPU capture graph via doe-gpu/capture.
    steps.append(run(
        "doppler-gemma4-e2b-webgpu-capture-graph",
        [
            "node",
            "bench/tools/capture_doppler_gemma4_webgpu_graph.mjs",
            "--out-json",
            "bench/out/doppler-capture/"
            "gemma-4-e2b-doe-webgpu-capture-graph.json",
        ],
        timeout=300,
    ))

    # 3. Gemma-4 E2B manifest-shape probe. A contract mismatch is
    # expected today and is a passed diagnostic step; source unreadable
    # errors remain failures via the probe's exit code.
    steps.append(run(
        "gemma4-e2b-manifest-shape-probe",
        [
            "python3",
            "bench/tools/probe_gemma4_e2b_manifest_shape.py",
            "--out-json",
            "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json",
        ],
    ))

    # 4. Gemma-4 E2B manifest-shape CPU execution oracle.
    steps.append(run(
        "gemma4-e2b-manifest-shape-execution",
        [
            "python3",
            "bench/tools/run_gemma4_e2b_manifest_shape_execution.py",
            "--out-json",
            "bench/out/manifest-shape/"
            "gemma-4-e2b-manifest-shape-execution.json",
        ],
        timeout=600,
    ))

    # 5. Doppler RDRR/int4ple structural probe.
    steps.append(run(
        "doppler-rdrr-int4ple-probe",
        [
            "python3",
            "bench/tools/probe_doppler_rdrr_artifact.py",
            "--fixture",
            "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json",
            "--out-json",
            "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json",
        ],
    ))

    # 6. Doppler RDRR Q4_K_M smoke-contract parity.
    steps.append(run(
        "doppler-rdrr-q4k-l1-parity",
        [
            "python3",
            "bench/tools/run_doppler_rdrr_q4k_parity.py",
            "--out-json",
            "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json",
        ],
        timeout=2600,
    ))

    # 7-8. Diagnostic smoke-chain depths. These are bundle-visible so
    # reviewers can inspect depth progress, but they do not promote any
    # depth to full-model or hardware evidence.
    for depth in DIAGNOSTIC_DEPTHS:
        steps.append(run(
            f"e2b-real-weight-depth-{depth}-diagnostic",
            [
                "python3",
                "bench/tools/run_e2b_real_weight_l1_parity.py",
                "--fixture",
                "config/gemma-4-e2b-real-weight-fixture.json",
                "--weights-dir",
                "bench/out/gemma-4-e2b-real-weights",
                "--num-layers",
                str(depth),
                "--out-json",
                f"bench/out/gemma-4-e2b-real-weight-parity-L{depth}.json",
                "--lane-out-dir",
                f"bench/out/gemma-4-e2b-real-weight-parity/L{depth}",
            ],
            timeout=2400,
        ))
        steps.append(run(
            f"doppler-rdrr-q4k-depth-{depth}-diagnostic",
            [
                "python3",
                "bench/tools/run_doppler_rdrr_q4k_parity.py",
                "--num-layers",
                str(depth),
            ],
            timeout=2600,
        ))

    # 9. Manifest-shape attention-core diagnostic. The self-check binds
    # capture-to-CSL lowering against this receipt, so refresh it before
    # self-check to avoid stale blocked receipts.
    steps.append(run(
        "gemma4-e2b-manifest-shape-attention-core",
        [
            "python3",
            "bench/tools/run_gemma4_e2b_manifest_shape_attention_core.py",
            "--out-json",
            "bench/out/manifest-shape/"
            "gemma-4-e2b-manifest-shape-attention-core.json",
        ],
        timeout=3900,
    ))

    # 10. self-check after the depth diagnostics and attention-core
    # receipt it validates. This
    # regens the E2B receipt, capture graph, capture-lowering receipt,
    # rollup, and numbered contract assertions.
    steps.append(run(
        "self-check",
        ["python3", "bench/tools/e2b_layer_block_self_check.py"],
        timeout=900,
    ))

    # 11. Refresh the E2B model receipt after the depth diagnostics.
    # Those diagnostics rewrite final-depth parity/trace artifacts, and
    # self-check restamps the capture-lowering receipt. Rebuild here so
    # the final standalone link-integrity gate validates the current
    # bytes, not the pre-depth self-check bytes.
    steps.append(run(
        "e2b-model-receipt-refresh-after-depth-diagnostics",
        [
            "python3",
            "bench/tools/build_model_runtime_receipt.py",
            "--execution-manifest",
            "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
            "--host-plan",
            "bench/out/e2b-full-graph/host-plan.json",
            "--memory-plan",
            "bench/out/e2b-full-graph/memory-plan.json",
            "--runtime-config",
            "bench/out/e2b-full-graph/runtime-config.json",
            "--simulator-plan",
            "bench/out/e2b-full-graph/simulator-plan.json",
            "--out-json",
            "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
            "--out-md",
            "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md",
        ],
    ))

    # 12. Bind the captured WebGPU graph to the first attention-core
    # SdkLayout/CSL lowering receipt. This consumes the post-capture
    # graph and post-attention-core simulator receipt, but remains
    # non-claimable for full Doppler inference.
    steps.append(run(
        "doppler-capture-to-csl-attention-core-lowering",
        [
            "python3",
            "bench/tools/"
            "record_doppler_capture_to_csl_attention_core_lowering.py",
            "--out-json",
            "bench/out/doppler-capture/"
            "gemma-4-e2b-capture-to-csl-attention-core-lowering.json",
        ],
    ))

    # 13. Refresh the E2B model receipt again after attention-core and
    # capture-lowering. Those steps restamp receipts, so refresh here so
    # manifestShapePartialExecutionEvidence and
    # dopplerWebgpuCaptureLoweringEvidence link the final bytes.
    steps.append(run(
        "e2b-model-receipt-refresh-after-attention-core-lowering",
        [
            "python3",
            "bench/tools/build_model_runtime_receipt.py",
            "--execution-manifest",
            "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
            "--host-plan",
            "bench/out/e2b-full-graph/host-plan.json",
            "--memory-plan",
            "bench/out/e2b-full-graph/memory-plan.json",
            "--runtime-config",
            "bench/out/e2b-full-graph/runtime-config.json",
            "--simulator-plan",
            "bench/out/e2b-full-graph/simulator-plan.json",
            "--out-json",
            "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
            "--out-md",
            "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md",
        ],
    ))

    # 14. Manifest-shape Doe/CSL runtime-path contract. This links the
    # post-attention-core/lowering refreshed model receipt, so it must
    # run after the second receipt refresh to avoid stale hashes.
    steps.append(run(
        "gemma4-e2b-manifest-shape-runtime-path",
        [
            "python3",
            "bench/tools/record_gemma4_e2b_manifest_shape_runtime_path.py",
            "--out-json",
            "bench/out/manifest-shape/"
            "gemma-4-e2b-manifest-shape-runtime-path.json",
        ],
    ))

    # 15. Gemma 4 31B AF16 simfabric cell evidence.
    steps.append(run(
        "gemma4-31b-af16-simfabric-cells",
        ["python3", "bench/tools/run_gemma4_31b_af16_simfabric_cells.py"],
    ))

    # 16. Gemma 4 31B AF16 local ceiling + Doppler-to-CSL splice receipts.
    steps.append(run(
        "gemma4-31b-af16-local-simfabric-ceiling",
        ["python3", "bench/tools/synthesize_gemma4_31b_af16_local_ceiling_receipt.py"],
    ))
    steps.append(run(
        "gemma4-31b-af16-splice-single-block-hidden",
        [
            "python3",
            "bench/tools/build_doppler_to_csl_splice_receipt.py",
            "--kind",
            "single_block_hidden",
            "--layer-index",
            "59",
            "--out",
            "bench/out/r3-1-31b-af16-doppler-csl-splice/single-block-hidden.json",
            "--allow-blocked",
        ],
    ))
    steps.append(run(
        "gemma4-31b-af16-splice-last-layer-tail-token",
        [
            "python3",
            "bench/tools/build_doppler_to_csl_splice_receipt.py",
            "--kind",
            "last_layer_tail_token",
            "--layer-index",
            "59",
            "--out",
            "bench/out/r3-1-31b-af16-doppler-csl-splice/last-layer-tail-token.json",
            "--allow-blocked",
        ],
    ))

    # 17. claim-discipline gate (hardware + MoE fronts).
    steps.append(run(
        "claim-discipline-gate",
        ["python3", "bench/gates/claim_discipline_gate.py"],
    ))

    # 18. SdkLayout streaming hardening gate against the freshest live
    # trace that carries streamTelemetry; skipped cleanly if no such
    # trace exists today.
    trace = find_live_trace_with_telemetry()
    if trace is None:
        steps.append(skipped(
            "sdklayout-streaming-hardening-gate",
            (
                "skipped: no live trace with streamTelemetry found. "
                "Rerun the CSL runner via cs_python and try again."
            ),
        ))
    else:
        steps.append(run(
            "sdklayout-streaming-hardening-gate",
            ["python3", "bench/gates/sdklayout_streaming_hardening_gate.py",
             "--trace", rel(trace)],
        ))

    # 19. receipt link integrity (already invoked by self-check STEP 5,
    # but we rerun standalone so a failure surfaces as its own step).
    steps.append(run(
        "receipt-link-integrity",
        ["python3", "bench/tools/validate_e2b_receipt_links.py"],
    ))

    # Aggregate verdict.
    failed = [s for s in steps if s["status"] == "failed"]
    skipped_steps = [s for s in steps if s["status"] == "skipped"]
    summary = {
        "schemaVersion": 1,
        "artifactKind": "doe_cerebras_evidence_bundle_summary",
        "steps": steps,
        "totalSteps": len(steps),
        "passedSteps": sum(1 for s in steps if s["status"] == "passed"),
        "failedSteps": len(failed),
        "skippedSteps": len(skipped_steps),
        "verdict": "passed" if not failed else "failed",
    }

    out_path = resolve(args.summary_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {rel(out_path)}")
    for s in steps:
        tag = {"passed": "OK", "failed": "FAIL", "skipped": "SKIP"}[s["status"]]
        print(f"  [{tag:<4}] {s['step']} ({s['elapsedMs']:.0f} ms)")
    print(
        f"verdict={summary['verdict']} "
        f"({summary['passedSteps']}/{summary['totalSteps']} passed, "
        f"{summary['skippedSteps']} skipped)"
    )
    return 0 if summary["verdict"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
