#!/usr/bin/env python3
"""One-shot pipeline smoke for the E2B layer-block in-loop work.

Runs seven steps in order (early-exits on STEP 0 or STEP 5 drift),
then asserts the contract:

  0. test_e2b_layer_block_compute.py
       -> golden-value unit test for the canonical compute_layer_block
          (early-exit gate: if goldens drifted, downstream regen is
          skipped so stale traces don't propagate the divergence)
  1. generate_e2b_layer_block_runner.py
       -> regen the SDK runner from the live CSL kernel + manifest
  2. emit_e2b_layer_block_synthetic_trace.py
       -> regen the numpy-only synthetic trace
  3. compare_runner_vs_synthetic.py
       -> regen the cross-runtime parity check verdict
  4. build_model_runtime_receipt.py (with E2B inputs)
       -> regen the model receipt; binds steps 2 + 3 by path/sha
  5. validate_e2b_receipt_links.py
       -> walk every (path, sha256) pair the receipt records and
          assert the file is on-disk with matching sha (early-exit
          gate: a stale link means the receipt now disagrees with
          the file system, downstream contract assertions can't
          trust the receipt content)
  6. emit_csl_reference_parity_sample.py
       -> regen the schema sample at
          examples/doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json
          from current artifacts so it auto-surfaces sha drift and
          the numpy-reference output digest (was previously hand-
          maintained and went stale across kernel upgrades)

Then asserts:
  C0. (implicit) STEP 0 unit test passed — compute_layer_block bit-
      exactness matches the captured goldens at every sentinel index
  C1. live kernel sha equals synthetic-trace's kernelSourceSha256InTrace
      (no drift between fixture and source)
  C2. receipt validates against doe-model-runtime-receipt.schema.json
  C3. receipt.streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence
      .syntheticTrace.exists == True AND .syntheticTrace.sha256
      matches the on-disk synthetic trace
  C4. receipt.streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence
      .crossRuntimeParityCheck.exists == True AND .promotionEligible is
      a bool (truthy or falsy is fine — we just need the field present)
  C5. runner regen succeeded (file exists, parses as Python)

Exit 0 if all checks pass; exit 1 if any failed (with a per-check
diff report). Lets the parity-contract gate (parallel-safe support
track) use this as a pre-flight before computing its own gate state.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--manifest",
        default="runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
    )
    p.add_argument(
        "--receipt-out",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    p.add_argument(
        "--receipt-md-out",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md",
    )
    return p.parse_args()


def run_step(label: str, argv: list) -> tuple[bool, str]:
    print(f"  [{label}] " + " ".join(str(a) for a in argv))
    try:
        r = subprocess.run(
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if r.returncode != 0:
        return False, f"exit={r.returncode}\nstderr:\n{r.stderr[-400:]}"
    last = r.stdout.strip().splitlines()
    print(f"     -> {last[-1] if last else '(no output)'}")
    return True, ""


def main() -> int:
    args = parse_args()
    runner_path = REPO_ROOT / "bench/runners/csl-runners/e2b_layer_block_smoke.py"
    kernel_path = REPO_ROOT / (
        "bench/out/streaming-executor/e2b-layer-block-source/"
        "transformer_layer_shape.csl"
    )
    synthetic_path = REPO_ROOT / (
        "bench/out/streaming-executor/e2b-layer-block-synthetic-trace.json"
    )
    parity_path = REPO_ROOT / (
        "bench/out/streaming-executor/"
        "e2b-layer-block-cross-runtime-parity-check.json"
    )
    receipt_path = REPO_ROOT / args.receipt_out
    schema_path = REPO_ROOT / "config/doe-model-runtime-receipt.schema.json"

    print("E2B layer-block self-check (in-loop pipeline)")
    print()
    print("STEP 0: golden-value unit test for compute_layer_block")
    ok, msg = run_step("unit-test", [
        "python3", "bench/tools/test_e2b_layer_block_compute.py",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        print()
        print("ABORT: compute_layer_block goldens drifted from the unit "
              "test. Skipping downstream regen so stale traces don't "
              "propagate the divergence. If the kernel changed "
              "intentionally, regenerate the goldens via:")
        print("  PRINT_GOLDENS=1 python3 bench/tools/test_e2b_layer_block_compute.py")
        print("then update VARYING_GOLDEN_HEX in the test and re-run.")
        return 1

    print()
    print("STEP 1: regen runner from live CSL kernel + manifest")
    ok, msg = run_step("runner", [
        "python3", "bench/tools/generate_e2b_layer_block_runner.py",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        return 1

    print()
    print("STEP 2: regen numpy-only synthetic trace")
    ok, msg = run_step("synthetic", [
        "python3", "bench/tools/emit_e2b_layer_block_synthetic_trace.py",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        return 1

    print()
    print("STEP 3: regen cross-runtime parity check")
    ok, msg = run_step("parity-check", [
        "python3", "bench/tools/compare_runner_vs_synthetic.py",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        return 1

    print()
    print("STEP 4: regen model receipt")
    ok, msg = run_step("receipt", [
        "python3", "bench/tools/build_model_runtime_receipt.py",
        "--execution-manifest", args.manifest,
        "--host-plan", "bench/out/e2b-full-graph/host-plan.json",
        "--memory-plan", "bench/out/e2b-full-graph/memory-plan.json",
        "--runtime-config", "bench/out/e2b-full-graph/runtime-config.json",
        "--simulator-plan", "bench/out/e2b-full-graph/simulator-plan.json",
        "--out-json", args.receipt_out,
        "--out-md", args.receipt_md_out,
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        return 1

    print()
    print("STEP 5: validate receipt link integrity (path + sha for every "
          "linked artifact)")
    ok, msg = run_step("link-integrity", [
        "python3", "bench/tools/validate_e2b_receipt_links.py",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        print()
        print("ABORT: at least one receipt-linked artifact has drifted "
              "on disk (path missing or sha mismatch). The receipt "
              "now disagrees with the file system; rerun the self-"
              "check after fixing the drift.")
        return 1

    print()
    print("STEP 6: regen CSL reference parity sample from current artifacts")
    ok, msg = run_step("parity-sample", [
        "python3", "bench/tools/emit_csl_reference_parity_sample.py",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        return 1

    print()
    print("CONTRACT ASSERTIONS")
    failures: list[str] = []

    # C1: live kernel sha == synthetic trace's kernelSourceSha256InTrace
    if not synthetic_path.is_file():
        failures.append("C1: synthetic trace missing at " + str(synthetic_path))
    else:
        live_sha = sha256_file(kernel_path)
        syn = json.loads(synthetic_path.read_text(encoding="utf-8"))
        in_trace = syn.get("layerBlockSmoke", {}).get("kernelSourceSha256")
        if in_trace == live_sha:
            print(
                "  C1 PASS: synthetic trace kernel sha matches live kernel "
                f"({live_sha[:16]}...)"
            )
        else:
            failures.append(
                f"C1 FAIL: synthetic trace kernel sha {in_trace} "
                f"!= live kernel sha {live_sha}"
            )

    # C2: receipt validates
    try:
        import jsonschema
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(receipt, schema)
        print("  C2 PASS: receipt validates against schema")
    except ImportError:
        print("  C2 SKIP: jsonschema not importable")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except jsonschema.ValidationError as e:
        failures.append(
            f"C2 FAIL: receipt schema violation at "
            f"{list(e.absolute_path)}: {e.message[:200]}"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as e:
        failures.append(f"C2 FAIL: {type(e).__name__}: {str(e)[:200]}")
        receipt = {}

    lbk = (
        receipt.get("streamingExecutorPrimitivesEvidence", {})
        .get("layerBlockKernelEvidence", {})
    )

    # C3: receipt.syntheticTrace.exists + sha matches on-disk
    syn_block = lbk.get("syntheticTrace", {})
    if syn_block.get("exists") is True:
        recorded_sha = syn_block.get("sha256")
        on_disk_sha = sha256_file(synthetic_path) if synthetic_path.is_file() else None
        if recorded_sha == on_disk_sha:
            print(
                "  C3 PASS: receipt.syntheticTrace.sha256 matches on-disk "
                f"({recorded_sha[:16]}...)"
            )
        else:
            failures.append(
                f"C3 FAIL: receipt.syntheticTrace.sha256={recorded_sha} "
                f"!= on-disk={on_disk_sha}"
            )
    else:
        failures.append(
            "C3 FAIL: receipt.syntheticTrace.exists is not True "
            f"({syn_block.get('exists')!r})"
        )

    # C4: receipt.crossRuntimeParityCheck.exists + promotionEligible field present
    pc_block = lbk.get("crossRuntimeParityCheck", {})
    if pc_block.get("exists") is True and "promotionEligible" in pc_block:
        print(
            "  C4 PASS: receipt.crossRuntimeParityCheck.promotionEligible "
            f"= {pc_block.get('promotionEligible')}"
        )
    else:
        failures.append(
            f"C4 FAIL: parity check block invalid "
            f"(exists={pc_block.get('exists')}, "
            f"has promotionEligible={'promotionEligible' in pc_block})"
        )

    # C5: runner regen produced a parseable Python file
    if runner_path.is_file():
        try:
            ast.parse(runner_path.read_text(encoding="utf-8"))
            print("  C5 PASS: regenerated runner parses as Python")
        except SyntaxError as e:
            failures.append(f"C5 FAIL: runner syntax error: {e.msg} at line {e.lineno}")
    else:
        failures.append(f"C5 FAIL: runner missing at {runner_path}")

    # C6: receipt.kernelStage matches the synthetic trace's kernelStage.
    # The kernelStage string is hardcoded in three places (runner source,
    # synthetic emitter, receipt builder). If any one drifts relative to
    # the others the evidence chain silently misrepresents the kernel.
    # This assertion catches receipt-vs-synthetic drift; the runner source
    # is caught transitively when its smoke trace is eventually re-run
    # and compared via the cross-runtime parity check (P2).
    receipt_stage = lbk.get("kernelStage")
    syn_stage = (
        syn.get("layerBlockSmoke", {}).get("kernelStage")
        if synthetic_path.is_file() else None
    )
    if receipt_stage and syn_stage and receipt_stage == syn_stage:
        print(
            "  C6 PASS: receipt.kernelStage matches synthetic trace "
            f"kernelStage ({receipt_stage[:48]}...)"
        )
    else:
        failures.append(
            "C6 FAIL: receipt.kernelStage vs synthetic kernelStage drift:\n"
            f"    receipt:   {receipt_stage!r}\n"
            f"    synthetic: {syn_stage!r}"
        )

    # C7: executionStatus reflects the parity verdict correctly.
    # Locks the flip wire in build_model_runtime_receipt.py — if the
    # wire is accidentally reverted to a hardcoded 'not_attempted' or
    # a false 'simulator_success' sneaks in without matching parity
    # evidence, C7 flips red. The flip requires: promotionEligible=true
    # AND structural gates pass AND modelId is E2B.
    pc_block_c7 = lbk.get("crossRuntimeParityCheck", {})
    pc_eligible = pc_block_c7.get("promotionEligible") is True
    model_id = receipt.get("modelId", "") or ""
    parity_applies = "e2b" in model_id.lower()
    structural_ok = (
        receipt.get("laneStatus") == "structural_full_coverage"
    )
    expected_status = (
        "simulator_success"
        if (pc_eligible and parity_applies and structural_ok)
        else "not_attempted"
    )
    expected_blocker = (
        "none"
        if (pc_eligible and parity_applies and structural_ok)
        else None
    )
    actual_status = receipt.get("executionStatus")
    actual_blocker = receipt.get("executionBlocker")
    status_ok = actual_status == expected_status
    blocker_ok = (expected_blocker is None) or (actual_blocker == expected_blocker)
    if status_ok and blocker_ok:
        print(
            "  C7 PASS: executionStatus reflects parity verdict "
            f"(promotionEligible={pc_eligible}, "
            f"status={actual_status!r}, blocker={actual_blocker!r})"
        )
    else:
        failures.append(
            "C7 FAIL: executionStatus flip wire inconsistent with "
            "parity verdict:\n"
            f"    promotionEligible: {pc_eligible}\n"
            f"    parityApplies:     {parity_applies}\n"
            f"    structuralOk:      {structural_ok}\n"
            f"    expected status:   {expected_status!r}\n"
            f"    actual status:     {actual_status!r}\n"
            f"    expected blocker:  {expected_blocker!r}\n"
            f"    actual blocker:    {actual_blocker!r}"
        )

    # C8: the auto-regenerated CSL reference parity sample passes
    # its own gate. Schema validation + internal consistency checks
    # (cslRun.traceSha256 matches on-disk, cslRun.kernelStage matches
    # the trace, manifest/graph path+sha match). Catches structural
    # regressions in emit_csl_reference_parity_sample.py that schema-
    # only validation (C2) wouldn't catch.
    sample_path = (
        "examples/"
        "doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json"
    )
    sample_gate = subprocess.run(
        ["python3", "bench/gates/csl_reference_parity_gate.py",
         "--receipt", sample_path],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if sample_gate.returncode == 0:
        print(
            "  C8 PASS: CSL reference parity sample passes its gate"
        )
    else:
        failures.append(
            "C8 FAIL: CSL reference parity gate rejected the sample:\n"
            f"    stdout: {sample_gate.stdout.strip()[:400]}\n"
            f"    stderr: {sample_gate.stderr.strip()[:200]}"
        )

    # C9: 31B receipt link integrity. Catches drift between the 31B
    # receipt and its underlying host-plan / memory-plan / runtime-
    # config / simulator-plan on disk. E2B gets its own link-integrity
    # via STEP 5 after the E2B regen in STEP 4; 31B is not regen'd in
    # this pipeline (Build-order step 7 material), but its receipt
    # must still link cleanly to match the plan's "receipts link
    # cleanly" mechanical-defensibility criterion.
    b31_receipt = (
        REPO_ROOT / "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json"
    )
    if b31_receipt.is_file():
        b31_link_gate = subprocess.run(
            ["python3", "bench/tools/validate_e2b_receipt_links.py",
             "--receipt", str(b31_receipt.relative_to(REPO_ROOT))],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if b31_link_gate.returncode == 0:
            last = [
                ln for ln in b31_link_gate.stdout.strip().splitlines()
                if ln.strip().startswith("PASS")
            ]
            summary = last[-1].strip() if last else "PASS"
            print(f"  C9 PASS: 31B receipt link integrity ({summary})")
        else:
            failures.append(
                "C9 FAIL: 31B receipt link-integrity gate rejected:\n"
                f"    stdout: {b31_link_gate.stdout.strip()[:400]}\n"
                f"    stderr: {b31_link_gate.stderr.strip()[:200]}"
            )
    else:
        failures.append(
            f"C9 FAIL: 31B receipt missing at {b31_receipt}"
        )

    # C10: 31B receipt validates against the model-runtime-receipt
    # schema, symmetric with C2 for E2B. Locks T16/T17 improvements
    # so the 31B receipt can't silently drift out of schema shape.
    if b31_receipt.is_file():
        try:
            import jsonschema as _js
            b31_json = json.loads(b31_receipt.read_text(encoding="utf-8"))
            _schema = json.loads(schema_path.read_text(encoding="utf-8"))
            _js.validate(b31_json, _schema)
            print("  C10 PASS: 31B receipt validates against schema")
        except ImportError:
            print("  C10 SKIP: jsonschema not importable")
        except _js.ValidationError as e:
            failures.append(
                "C10 FAIL: 31B receipt schema violation at "
                f"{list(e.absolute_path)}: {e.message[:200]}"
            )
        except Exception as e:
            failures.append(
                f"C10 FAIL: 31B receipt validation error: "
                f"{type(e).__name__}: {str(e)[:200]}"
            )

    print()
    if failures:
        print(f"SELF-CHECK FAILED ({len(failures)} contract violation(s)):")
        for f in failures:
            print("  " + f)
        return 1

    print("SELF-CHECK PASSED — in-loop pipeline is healthy.")
    pc = lbk.get("crossRuntimeParityCheck", {})
    print(
        "  parity-check verdict: promotionEligible="
        + str(pc.get("promotionEligible"))
        + f"  met={len(pc.get('preconditionsMet', []))}/6"
        + f"  missing={pc.get('preconditionsMissing', [])}"
    )
    # When the parity verdict is not yet eligible and the runner
    # trace is stale, print the one command that unblocks the
    # whole chain. cs_python-equipped hosts can copy-paste this
    # directly. The flip wire (compute_execution_status + the
    # parity-check regen in STEP 3) auto-propagates the result to
    # executionStatus on the next self-check run.
    if pc.get("promotionEligible") is not True:
        missing = pc.get("preconditionsMissing", []) or []
        if any(
            token in m
            for m in missing
            for token in ("P2", "P3", "P5", "P6")
        ):
            print()
            print(
                "  to unblock: run the following on a cs_python-equipped "
                "host, then rerun this self-check:"
            )
            print("    python3 bench/runners/csl-runners/e2b_layer_block_smoke.py")
            print(
                "  that command compiles + runs the 35-layer chain, "
                "emits the smoke-trace with output digest, and the "
                "flip wire promotes executionStatus to simulator_success."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
