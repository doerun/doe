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

Then asserts a growing set of structural contracts. The current set
spans C0..C41 (as of the last update; see below for the authoritative
enumeration). Broadly they cover:

  - Core kernel/trace/receipt integrity (C0-C15)
  - Cerebras evidence bundle pack/verify round-trip and the packer ↔
    verifier sync across extensions, path-substrings, and role
    taxonomy (C16, C22, C23, C32)
  - Demo HTML/JS/server invariants: routes, cross-links, data-copy
    targets, emulator soft-fail, ANSI-strip and runner-error
    formatter (C17, C18, C25, C27, C33)
  - Bundle-doc governance: skip-lists synced across packer/gate/
    verifier, pointer-doc stale-lag guard, prep-script ordering,
    tools-index completeness (C28-C31)

Authoritative enumeration lives in two places and stays in sync via
C31: `bench/tools/cerebras-evidence-bundle-tools.md` has the contract
table; this file itself emits `C<N> PASS`/`C<N> FAIL` lines at
runtime. Prefer grepping the code over restating contracts here —
this docstring intentionally does not enumerate individual contracts
because the list drifts faster than prose can keep up.

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
    print("STEP 3a: refresh Doppler WebGPU capture graph")
    ok, msg = run_step("doppler-capture", [
        "node",
        "bench/tools/capture_doppler_gemma4_webgpu_graph.mjs",
        "--out-json",
        "bench/out/doppler-capture/"
        "gemma-4-e2b-doe-webgpu-capture-graph.json",
    ])
    if not ok:
        print(f"  FAILED: {msg}")
        return 1

    print()
    print("STEP 3b: refresh capture-to-CSL attention-core lowering receipt")
    ok, msg = run_step("capture-lowering", [
        "python3",
        "bench/tools/record_doppler_capture_to_csl_attention_core_lowering.py",
        "--out-json",
        "bench/out/doppler-capture/"
        "gemma-4-e2b-capture-to-csl-attention-core-lowering.json",
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

    # Auto-regen the doe_run.py all-lanes rollup so executionStatus +
    # realWeightEvidence the receipt just computed are visible to the
    # dashboard and browser cockpit without a second manual step. Per
    # user's 15-item list (#10): "Regenerate the doe_run.py all-lanes
    # rollup after every receipt regen so the dashboard and demo
    # consume one canonical summary."
    print()
    print("STEP 4b: regen all-lanes rollup from per-target receipts + model receipt")
    ok, msg = run_step("rollup", [
        "python3", "bench/tools/summarize_doe_run_lanes.py",
        "--num-layers", "1",
        "--out-json", "bench/out/doe-run/all-lanes-summary-L1.json",
    ])
    if not ok:
        # Rollup regen is not-fatal — the receipt is authoritative.
        # Just surface the reason so it's visible in the log, then
        # continue. A missing rollup would only affect the dashboard.
        print(f"  NON-FATAL: {msg}")

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
    _rw_criteria = (
        (receipt.get("realWeightEvidence") or {})
        .get("promotionCriteriaMet") or {}
    )
    _rw_promoted = (
        _rw_criteria.get("weightHashMatched") is True
        and _rw_criteria.get("outputParityPassed") is True
    )
    if pc_eligible and parity_applies and structural_ok and _rw_promoted:
        expected_status = "real_weight_layer_block_success"
    elif pc_eligible and parity_applies and structural_ok:
        expected_status = "simulator_success"
    else:
        expected_status = "not_attempted"
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
            f"    realWeightPromoted: {_rw_promoted}\n"
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

    # C12: repo-wide audit — no CSL kernel outside diagnostic probes
    # uses raw `math.sqrt` without wrapping it in the sqrt_nr NR-
    # refined form. The WSE hardware sqrt is 1-ULP off from IEEE-
    # correct-rounded at some input magnitudes (that was the L2
    # drift unlocking simulator_success); future kernels adopting
    # sqrt must use the sqrt_nr pattern. Diagnostic probe files in
    # e2b-layer-block-source/ (stage*_probe.csl, stage3_*_only.csl,
    # stage3_rms_*.csl) are scratch and exempted.
    production_probe_suffixes = (
        "_probe.csl", "_only.csl", "_f64.csl", "_nr.csl",
    )
    csl_audit_skip_prefixes = (
        "bench/out/scratch/csl-sdk-tmp/",
    )
    audit_fails = []
    audit_scanned = 0
    for _csl in REPO_ROOT.rglob("*.csl"):
        _rel = _csl.relative_to(REPO_ROOT).as_posix()
        if any(_rel.startswith(prefix) for prefix in csl_audit_skip_prefixes):
            continue
        if _csl.name.endswith(production_probe_suffixes):
            continue
        audit_scanned += 1
        try:
            _text = _csl.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "math.sqrt(" in _text and "fn sqrt_nr(" not in _text:
            audit_fails.append(_rel)
    if not audit_fails:
        print(
            "  C12 PASS: no CSL production kernel uses raw math.sqrt "
            "outside the sqrt_nr NR-refined wrapper "
            f"(scanned {audit_scanned} CSL files)"
        )
    else:
        failures.append(
            "C12 FAIL: CSL kernels using raw math.sqrt without "
            "sqrt_nr NR-refined wrapper:\n"
            + "\n".join("    " + p for p in audit_fails)
            + "\n    Apply the `math.sqrt(x) + 0.5*(y + x/y)` "
            "pattern (see transformer_layer_shape.csl sqrt_nr)."
        )

    # C11: sqrt_nr function in the canonical E2B kernel uses the
    # math.sqrt(x) + one-Newton-Raphson-step form that unlocked
    # simulator_success. The prior body — a 16-iteration NR loop
    # starting from y=1.0/y=x — converged to a value 1 ULP off from
    # IEEE-correctly-rounded at L2 magnitudes (mean_sq2 ~ 1229),
    # which drifted inv_rms2 by 1 ULP and cascaded through stage 4
    # to a 4.959e-05 L2 output error. Reject that form if it
    # reappears (silent revert).
    kernel_src = kernel_path.read_text(encoding="utf-8")
    import re as _re
    m = _re.search(
        r"fn sqrt_nr\(x: f32\) f32 \{(.*?)\n\}",
        kernel_src,
        flags=_re.DOTALL,
    )
    if m is None:
        failures.append("C11 FAIL: sqrt_nr function not found in kernel")
    else:
        body = m.group(1)
        has_math_sqrt_seed = "math.sqrt(x)" in body
        has_nr_step = (
            "0.5 * (y0 + x / y0)" in body
            or "0.5 * (y + x / y)" in body
        )
        looks_like_old_loop = (
            "@range(u16, 16)" in body
            or "for (@range(u16, 16))" in body
        )
        if has_math_sqrt_seed and has_nr_step and not looks_like_old_loop:
            print(
                "  C11 PASS: sqrt_nr uses math.sqrt + 1 NR step "
                "(IEEE-correctly-rounded f32 sqrt form)"
            )
        else:
            failures.append(
                "C11 FAIL: sqrt_nr body regression. Expected "
                "`math.sqrt(x)` seed + `0.5 * (y0 + x / y0)` NR step; "
                "reject the 16-iteration loop.\n"
                f"    has_math_sqrt_seed: {has_math_sqrt_seed}\n"
                f"    has_nr_step:        {has_nr_step}\n"
                f"    looks_like_old_loop: {looks_like_old_loop}\n"
                f"    body (first 300 chars):\n{body[:300]}"
            )

    # C13: 31B receipt's crossRuntimeParityCheck.promotionEligible
    # is True AND links to the 31B-specific parity artifact.
    # Symmetric with C4 for E2B. Locks tick-11 per-model parity
    # lane so 31B can't silently revert to binding the E2B artifact
    # or losing its parity evidence.
    if b31_receipt.is_file():
        try:
            _b31 = json.loads(b31_receipt.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(
                f"C13 FAIL: 31B receipt JSON parse: {e}"
            )
        else:
            _b31_pc = (
                _b31.get("streamingExecutorPrimitivesEvidence", {})
                .get("layerBlockKernelEvidence", {})
                .get("crossRuntimeParityCheck", {})
            )
            _expected_path_fragment = "gemma-4-31b-layer-block"
            _pc_path = _b31_pc.get("path") or ""
            if (
                _b31_pc.get("exists") is True
                and _b31_pc.get("promotionEligible") is True
                and _expected_path_fragment in _pc_path
            ):
                print(
                    "  C13 PASS: 31B receipt binds its own parity "
                    f"artifact, promotionEligible=True "
                    f"({_pc_path[-60:]})"
                )
            else:
                failures.append(
                    "C13 FAIL: 31B receipt's parity binding off:\n"
                    f"    exists: {_b31_pc.get('exists')}\n"
                    f"    promotionEligible: {_b31_pc.get('promotionEligible')}\n"
                    f"    path: {_pc_path!r}\n"
                    f"    expected path contains: {_expected_path_fragment!r}"
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

    # C14: real-weight fixture bundle integrity. Every sha256 the
    # fixture pins for manifest/graph/input must match the bytes on
    # disk. If any artifact drifts, the eventual parity run would
    # silently compare the wrong program — this is the regression
    # lock that catches the drift at self-check time instead.
    _fixture_path = REPO_ROOT / "config/gemma-4-e2b-real-weight-fixture.json"
    if _fixture_path.is_file():
        try:
            _fix = json.loads(_fixture_path.read_text(encoding="utf-8"))
            import hashlib as _hashlib_c14
            _c14_misses = []
            for _label, _node_path in [
                ("manifest", ("bundle", "manifest")),
                ("graph", ("bundle", "graph")),
                ("input", ("input",)),
            ]:
                _node = _fix
                for _k in _node_path:
                    _node = (_node or {}).get(_k, {})
                _rel = _node.get("path")
                _expected = _node.get("sha256")
                if not (_rel and _expected):
                    _c14_misses.append(f"fixture missing path/sha for {_label}")
                    continue
                _abs = REPO_ROOT / _rel
                if not _abs.is_file():
                    _c14_misses.append(f"{_label} path {_rel} not on disk")
                    continue
                _h = _hashlib_c14.sha256()
                with _abs.open("rb") as _fh:
                    for _ch in iter(lambda: _fh.read(1 << 20), b""):
                        _h.update(_ch)
                _actual = _h.hexdigest()
                if _actual != _expected:
                    _c14_misses.append(
                        f"{_label} {_rel} sha256 drift: fixture={_expected[:12]}... "
                        f"actual={_actual[:12]}..."
                    )
            if not _c14_misses:
                print(
                    "  C14 PASS: real-weight fixture bundle integrity "
                    "(manifest+graph+input shas match on-disk bytes)"
                )
            else:
                for _m in _c14_misses:
                    failures.append(f"C14 FAIL: {_m}")

            # C15: parity harness state is coherent with the local
            # real-weight materialization state. Fresh clones still pass
            # with blocked_weights_absent; hosts with materialized weights
            # must at least pass the weights audit, and promoted hosts must
            # show parity_passed with tolerance evidence. parity_failed is
            # always a regression.
            import subprocess as _subprocess_c15
            _c15_canonical = (
                REPO_ROOT / "bench/out/gemma-4-e2b-real-weight-parity-L1.json"
            )
            _fixture_sha_c15 = sha256_file(_fixture_path)
            _canonical_current_fixture = False
            if _c15_canonical.is_file():
                try:
                    _canonical_current_fixture = (
                        json.loads(
                            _c15_canonical.read_text(encoding="utf-8")
                        ).get("fixtureSha256")
                        == _fixture_sha_c15
                    )
                except (OSError, ValueError, json.JSONDecodeError):
                    _canonical_current_fixture = False
            _weights_rel = (
                (_fix.get("weightsDir") or {}).get("pathPlaceholder") or ""
            )
            _weights_abs = REPO_ROOT / _weights_rel
            if (
                _weights_abs.is_dir()
                and _c15_canonical.is_file()
                and _canonical_current_fixture
            ):
                _c15_out = _c15_canonical
                _c15 = None
            else:
                _c15_out = (
                    REPO_ROOT
                    / "bench/out/scratch/gemma-4-e2b-real-weight-parity-C15.json"
                )
                _c15_out.parent.mkdir(parents=True, exist_ok=True)
                _c15 = _subprocess_c15.run(
                    ["python3", "bench/tools/run_e2b_real_weight_l1_parity.py",
                     "--out-json", str(_c15_out.relative_to(REPO_ROOT))],
                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800,
                )
            if _c15 is not None and _c15.returncode != 0:
                failures.append(
                    f"C15 FAIL: parity harness returned {_c15.returncode}: "
                    f"{_c15.stderr[-200:]}"
                )
            elif not _c15_out.is_file():
                failures.append("C15 FAIL: parity harness wrote no verdict")
            else:
                _v = json.loads(_c15_out.read_text(encoding="utf-8"))
                _verdict = _v.get("verdict")
                _bundle_ok = _v.get("bundleIdentityMatched")
                _weights_present = _v.get("weightsDirPresent")
                _audit_ok = _v.get("weightsAuditPassed")
                _expected_weight_sha = (
                    (_fix.get("weightsDir") or {})
                    .get("expectedWeightSetSha256")
                )
                _actual_weight_sha = _v.get("weightSetSha256")
                _weight_sha_ok = (
                    _expected_weight_sha is None
                    or _actual_weight_sha == _expected_weight_sha
                )
                _parity = _v.get("parity") or {}
                _tolerance_ok = bool(
                    _parity.get("outputDigestMatch")
                    or _parity.get("tolerancePassed")
                )
                if _verdict == "blocked_weights_absent" and _bundle_ok is True:
                    print(
                        "  C15 PASS: parity harness skeleton exits "
                        "blocked_weights_absent with bundleIdentityMatched=true"
                    )
                elif (
                    _verdict == "lane_incomplete"
                    and _bundle_ok is True
                    and _weights_present is True
                    and _audit_ok is True
                    and _weight_sha_ok
                ):
                    print(
                        "  C15 PASS: real-weight harness audited weights "
                        "but a runtime lane is incomplete on this host "
                        f"(weightSetSha256={str(_actual_weight_sha)[:16]}...)"
                    )
                elif (
                    _verdict == "parity_passed"
                    and _bundle_ok is True
                    and _weights_present is True
                    and _audit_ok is True
                    and _weight_sha_ok
                    and _tolerance_ok
                ):
                    print(
                        "  C15 PASS: real-weight L1 parity passed with "
                        "bundle identity + weights audit + tolerance evidence "
                        f"(weightSetSha256={str(_actual_weight_sha)[:16]}...)"
                    )
                else:
                    failures.append(
                        f"C15 FAIL: parity harness verdict={_verdict!r} "
                        f"bundleIdentityMatched={_bundle_ok!r}, "
                        f"weightsDirPresent={_weights_present!r}, "
                        f"weightsAuditPassed={_audit_ok!r}, "
                        f"weightShaOk={_weight_sha_ok!r}, "
                        f"toleranceOk={_tolerance_ok!r}; expected either "
                        "blocked_weights_absent for fresh clones, "
                        "lane_incomplete with audited weights, or "
                        "parity_passed with audited weights + tolerance."
                    )
        except (OSError, ValueError, json.JSONDecodeError) as _e:
            failures.append(f"C14/C15 FAIL: fixture evaluation error: {_e}")
    else:
        failures.append(
            f"C14 FAIL: fixture missing at {_fixture_path.relative_to(REPO_ROOT)}"
        )

    # C36: Doe can structurally consume the local Doppler RDRR/int4ple
    # artifact without pretending Q4_K_M dequant or production-output
    # parity is complete. Fresh clones may skip as blocked_artifact_absent;
    # hosts with ../doppler/models/local/... must validate the manifest,
    # selected shard hash, tensor spans, and int4 PLE metadata.
    _rdrr_fixture = (
        REPO_ROOT
        / "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json"
    )
    _rdrr_probe_script = REPO_ROOT / "bench/tools/probe_doppler_rdrr_artifact.py"
    _c36_errors: list[str] = []
    if not _rdrr_fixture.is_file():
        _c36_errors.append(
            f"fixture missing at {_rdrr_fixture.relative_to(REPO_ROOT)}"
        )
    elif not _rdrr_probe_script.is_file():
        _c36_errors.append(
            f"probe missing at {_rdrr_probe_script.relative_to(REPO_ROOT)}"
        )
    else:
        try:
            _rdrr_fix = json.loads(_rdrr_fixture.read_text(encoding="utf-8"))
            _probe_rel = (
                (_rdrr_fix.get("probe") or {}).get("outputPath")
                or "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json"
            )
            _probe_out = REPO_ROOT / _probe_rel
            _c36 = subprocess.run(
                [
                    "python3",
                    "bench/tools/probe_doppler_rdrr_artifact.py",
                    "--fixture",
                    str(_rdrr_fixture.relative_to(REPO_ROOT)),
                    "--out-json",
                    str(_probe_out.relative_to(REPO_ROOT)),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if _c36.returncode != 0:
                _c36_errors.append(
                    f"probe returned {_c36.returncode}: {_c36.stderr[-300:]}"
                )
            elif not _probe_out.is_file():
                _c36_errors.append("probe did not write its output artifact")
            else:
                _probe = json.loads(_probe_out.read_text(encoding="utf-8"))
                _status = _probe.get("status")
                if _status == "blocked_artifact_absent":
                    print(
                        "  C36 SKIP: Doppler RDRR/int4ple artifact absent; "
                        "probe emitted blocked_artifact_absent"
                    )
                else:
                    _shard_ok = (
                        ((_probe.get("shardAudit") or {})
                         .get("selectedShardHashAudit") or {})
                        .get("status") == "passed"
                    )
                    _tensor_ok = (
                        ((_probe.get("tensorAudit") or {}).get("status"))
                        == "passed"
                    )
                    _dequant = _probe.get("dequantStatus") or {}
                    _q4_blocked = (
                        _dequant.get("q4k") == "blocked_not_implemented"
                    )
                    _ple_meta = (
                        _dequant.get("int4Ple")
                        == "metadata_validated_no_runtime_dequant"
                    )
                    _summary = _probe.get("artifactSummary") or {}
                    _expected_extra = (
                        (_rdrr_fix.get("expected") or {})
                        .get("extraLocalShards") or []
                    )
                    _extra_ok = (
                        _summary.get("extraLocalShards")
                        == _expected_extra
                    )
                    if (
                        _status == "succeeded"
                        and _shard_ok
                        and _tensor_ok
                        and _q4_blocked
                        and _ple_meta
                        and _extra_ok
                    ):
                        print(
                            "  C36 PASS: Doppler RDRR/int4ple artifact "
                            "structural probe passed (manifest+target "
                            "shard+tensor spans; Q4 dequant still blocked)"
                        )
                    else:
                        _c36_errors.append(
                            "unexpected probe state: "
                            f"status={_status!r}, shardOk={_shard_ok!r}, "
                            f"tensorOk={_tensor_ok!r}, "
                            f"q4Blocked={_q4_blocked!r}, "
                            f"pleMeta={_ple_meta!r}, extraOk={_extra_ok!r}"
                        )
        except (OSError, ValueError, json.JSONDecodeError) as _e:
            _c36_errors.append(
                f"fixture/probe evaluation error: {type(_e).__name__}: {_e}"
            )
    for _err in _c36_errors:
        failures.append(f"C36 FAIL: {_err}")

    # C37: Optional Doppler RDRR Q4_K_M L1 parity verdict, when
    # generated, must preserve the narrow smoke-contract claim
    # boundary. The evidence-bundle runner is responsible for
    # generating it; fresh clones or hosts without the local Doppler
    # artifact may be absent/blocked here.
    _q4k_parity = (
        REPO_ROOT
        / "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json"
    )
    if _q4k_parity.is_file():
        try:
            _q4k = json.loads(_q4k_parity.read_text(encoding="utf-8"))
            _status = _q4k.get("status")
            _verdict = _q4k.get("verdict")
            if _verdict == "blocked_artifact_absent":
                print(
                    "  C37 SKIP: Doppler RDRR Q4_K_M parity blocked "
                    "because the local artifact is absent"
                )
            else:
                _criteria = _q4k.get("promotionCriteriaMet") or {}
                _parity = _q4k.get("paritySummary") or {}
                _claim_scope = _q4k.get("claimScope") or {}
                _not_claimable = _claim_scope.get("notClaimable") or []
                _blocks_full = any(
                    "Full Gemma-4 E2B execution" in str(item)
                    for item in _not_claimable
                )
                _blocks_hardware = any(
                    "Cerebras hardware" in str(item)
                    for item in _not_claimable
                )
                if (
                    _status == "succeeded"
                    and _verdict == "rdrr_q4k_l1_parity_passed"
                    and _criteria.get("structuralProbePassed") is True
                    and _criteria.get("q4kSmokeSlicesExtracted") is True
                    and _criteria.get("weightsAuditPassed") is True
                    and _criteria.get("crossRuntimeParityPassed") is True
                    and _criteria.get("fullModelDepthExecuted") is False
                    and _criteria.get("hardwareExecuted") is False
                    and _parity.get("tolerancePassed") is True
                    and int(_parity.get("layersCompared", 0)) == 1
                    and _blocks_full
                    and _blocks_hardware
                ):
                    print(
                        "  C37 PASS: Doppler RDRR Q4_K_M L1 "
                        "smoke-contract parity passed while full-model "
                        "and hardware claims remain blocked"
                    )
                elif (
                    _status == "blocked"
                    and _verdict == "rdrr_q4k_l1_parity_lane_incomplete"
                    and _criteria.get("q4kSmokeSlicesExtracted") is True
                    and _criteria.get("weightsAuditPassed") is True
                ):
                    print(
                        "  C37 PASS: Doppler RDRR Q4_K_M slices were "
                        "extracted and audited, but a runtime lane is "
                        "incomplete on this host"
                    )
                else:
                    failures.append(
                        "C37 FAIL: unexpected RDRR Q4_K_M parity state: "
                        f"status={_status!r}, verdict={_verdict!r}, "
                        f"criteria={_criteria!r}, parity={_parity!r}"
                    )
        except (OSError, ValueError, json.JSONDecodeError) as _e:
            failures.append(
                "C37 FAIL: q4k parity verdict unreadable: "
                f"{type(_e).__name__}: {_e}"
            )
    else:
        print(
            "  C37 SKIP: Doppler RDRR Q4_K_M parity verdict not yet "
            "generated"
        )

    # C38: Optional real-weight diagnostics, when generated, must pass
    # exactly their requested smoke-chain depth while preserving the
    # non-full-model boundary. These artifacts are CSL strategy rungs
    # after L1; they are not required on fresh clones.
    _diagnostic_depths = (2, 4, 8, 35)
    _c38_seen = False
    _c38_errors = []
    for _depth in _diagnostic_depths:
        _bf16_path = (
            REPO_ROOT
            / f"bench/out/gemma-4-e2b-real-weight-parity-L{_depth}.json"
        )
        if _bf16_path.is_file():
            _c38_seen = True
            try:
                _bf16 = json.loads(_bf16_path.read_text(encoding="utf-8"))
                _bf16_parity = _bf16.get("parity") or {}
                if _bf16.get("verdict") == "blocked_weights_absent":
                    print(
                        "  C38 SKIP: BF16-derived E2B diagnostic depth "
                        f"{_depth} blocked because local weight slices "
                        "are absent"
                    )
                elif (
                    _bf16.get("verdict") == "parity_passed"
                    and int(_bf16.get("numLayers", 0)) == _depth
                    and _bf16.get("weightsAuditPassed") is True
                    and _bf16_parity.get("tolerancePassed") is True
                    and int(_bf16_parity.get("layersCompared", 0)) == _depth
                ):
                    print(
                        "  C38 PASS: BF16-derived E2B diagnostic depth "
                        f"{_depth} succeeded with matching layer count"
                    )
                else:
                    _c38_errors.append(
                        f"BF16 depth {_depth} unexpected state: "
                        f"verdict={_bf16.get('verdict')!r}, "
                        f"numLayers={_bf16.get('numLayers')!r}, "
                        "weightsAuditPassed="
                        f"{_bf16.get('weightsAuditPassed')!r}, "
                        f"parity={_bf16_parity!r}"
                    )
            except (OSError, ValueError, json.JSONDecodeError) as _e:
                _c38_errors.append(
                    f"BF16 depth {_depth} verdict unreadable: "
                    f"{type(_e).__name__}: {_e}"
                )

        _rdrr_path = (
            REPO_ROOT
            / (
                "bench/out/doppler-rdrr/"
                f"gemma-4-e2b-int4ple-q4k-parity-L{_depth}.json"
            )
        )
        if _rdrr_path.is_file():
            _c38_seen = True
            try:
                _rdrr = json.loads(_rdrr_path.read_text(encoding="utf-8"))
                _criteria = _rdrr.get("promotionCriteriaMet") or {}
                _parity = _rdrr.get("paritySummary") or {}
                _claim_scope = _rdrr.get("claimScope") or {}
                _not_claimable = _claim_scope.get("notClaimable") or []
                _blocks_full = any(
                    "Full Gemma-4 E2B execution" in str(item)
                    for item in _not_claimable
                )
                _blocks_hardware = any(
                    "Cerebras hardware" in str(item)
                    for item in _not_claimable
                )
                if _rdrr.get("verdict") == "blocked_artifact_absent":
                    print(
                        "  C38 SKIP: Doppler RDRR Q4_K_M diagnostic "
                        f"depth {_depth} blocked because the local "
                        "artifact is absent"
                    )
                elif (
                    _rdrr.get("status") == "succeeded"
                    and _rdrr.get("verdict")
                    == f"rdrr_q4k_l{_depth}_parity_passed"
                    and int(_rdrr.get("numLayers", 0)) == _depth
                    and _criteria.get("structuralProbePassed") is True
                    and _criteria.get("q4kSmokeSlicesExtracted") is True
                    and _criteria.get("weightsAuditPassed") is True
                    and _criteria.get("crossRuntimeParityPassed") is True
                    and _criteria.get("fullModelDepthExecuted") is False
                    and _criteria.get("hardwareExecuted") is False
                    and _parity.get("tolerancePassed") is True
                    and int(_parity.get("layersCompared", 0)) == _depth
                    and _blocks_full
                    and _blocks_hardware
                ):
                    print(
                        "  C38 PASS: Doppler RDRR Q4_K_M diagnostic "
                        f"depth {_depth} succeeded with full-model and "
                        "hardware claims blocked"
                    )
                else:
                    _c38_errors.append(
                        f"RDRR depth {_depth} unexpected state: "
                        f"status={_rdrr.get('status')!r}, "
                        f"verdict={_rdrr.get('verdict')!r}, "
                        f"numLayers={_rdrr.get('numLayers')!r}, "
                        f"criteria={_criteria!r}, parity={_parity!r}"
                    )
            except (OSError, ValueError, json.JSONDecodeError) as _e:
                _c38_errors.append(
                    f"RDRR depth {_depth} verdict unreadable: "
                    f"{type(_e).__name__}: {_e}"
                )
    if not _c38_seen:
        print(
            "  C38 SKIP: E2B real-weight diagnostic verdicts not yet "
            "generated for declared depths"
        )
    for _err in _c38_errors:
        failures.append(f"C38 FAIL: {_err}")

    # C39: Manifest-shape blocker is explicit and source-backed. The
    # probe reads the upstream E2B config + SafeTensors header and
    # records the current Doe manifest mismatch instead of leaving the
    # head-dim/global-head contract as implicit lore. Fresh clones may
    # emit the source-absent blocker; hosts with /home/x/model-downloads
    # must show tensor shapes pass and the manifest contract block.
    _shape_probe_script = (
        REPO_ROOT / "bench/tools/probe_gemma4_e2b_manifest_shape.py"
    )
    _shape_probe_out = (
        REPO_ROOT
        / "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json"
    )
    if not _shape_probe_script.is_file():
        failures.append("C39 FAIL: manifest-shape probe script missing")
    else:
        try:
            _c39 = subprocess.run(
                [
                    "python3",
                    str(_shape_probe_script.relative_to(REPO_ROOT)),
                    "--out-json",
                    str(_shape_probe_out.relative_to(REPO_ROOT)),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _c39.returncode != 0:
                failures.append(
                    "C39 FAIL: manifest-shape probe returned "
                    f"{_c39.returncode}: {_c39.stderr[-300:]}"
                )
            elif not _shape_probe_out.is_file():
                failures.append(
                    "C39 FAIL: manifest-shape probe did not write output"
                )
            else:
                _probe = json.loads(
                    _shape_probe_out.read_text(encoding="utf-8")
                )
                _verdict = _probe.get("verdict")
                _status = _probe.get("status")
                if _verdict == "manifest_shape_probe_blocked_source_absent":
                    print(
                        "  C39 SKIP: manifest-shape source checkpoint "
                        "absent; probe recorded source-absent blocker"
                    )
                else:
                    _tensor_ok = all(
                        bool(item.get("passed"))
                        for item in (_probe.get("tensorAudit") or [])
                    )
                    _blockers = "\n".join(_probe.get("blockers") or [])
                    _has_head = "modelConfig.headDim" in _blockers
                    _has_global = "modelConfig.globalHeadDim" in _blockers
                    _has_kv_heads = "modelConfig.numKeyValueHeads" in _blockers
                    _has_q_shape = "q_proj" in _blockers
                    _has_o_shape = "o_proj" in _blockers
                    _upstream = _probe.get("upstreamConfig") or {}
                    _local_head_ok = _upstream.get("headDim") == 256
                    _global_head_ok = _upstream.get("globalHeadDim") == 512
                    _kv_heads_ok = _upstream.get("numKeyValueHeads") == 1
                    if (
                        _status == "blocked"
                        and _verdict
                        == "manifest_shape_probe_blocked_contract_mismatch"
                        and _tensor_ok
                        and _has_head
                        and _has_global
                        and _has_kv_heads
                        and _has_q_shape
                        and _has_o_shape
                        and _local_head_ok
                        and _global_head_ok
                        and _kv_heads_ok
                    ):
                        print(
                            "  C39 PASS: manifest-shape probe records "
                            "upstream E2B local/global head contract and "
                            "blocks stale Doe manifest shape"
                        )
                    elif _status == "succeeded":
                        print(
                            "  C39 PASS: manifest-shape probe passes; "
                            "Doe manifest fields match upstream tensor "
                            "metadata"
                        )
                    else:
                        failures.append(
                            "C39 FAIL: unexpected manifest-shape probe "
                            f"state: status={_status!r}, "
                            f"verdict={_verdict!r}, tensorOk={_tensor_ok!r}, "
                            f"blockers={_probe.get('blockers')!r}, "
                            f"upstream={_upstream!r}"
                        )
        except (OSError, ValueError, json.JSONDecodeError) as _e:
            failures.append(
                "C39 FAIL: manifest-shape probe evaluation error: "
                f"{type(_e).__name__}: {_e}"
            )

    # C40: The raw BF16 E2B checkpoint can execute as a text-only
    # CPU/Numpy manifest-shape oracle through all 35 decoder layers,
    # final norm, and tied lm-head top-k. This is deliberately NOT a
    # Doe/CSL runtime promotion; the artifact must keep those blockers
    # explicit while proving the upstream tensor dimensions are
    # executable with finite outputs.
    _shape_exec_script = (
        REPO_ROOT / "bench/tools/run_gemma4_e2b_manifest_shape_execution.py"
    )
    _shape_exec_out = (
        REPO_ROOT
        / "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json"
    )
    if not _shape_exec_script.is_file():
        failures.append("C40 FAIL: manifest-shape execution script missing")
    else:
        try:
            _c40 = subprocess.run(
                [
                    "python3",
                    str(_shape_exec_script.relative_to(REPO_ROOT)),
                    "--out-json",
                    str(_shape_exec_out.relative_to(REPO_ROOT)),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if _c40.returncode != 0:
                failures.append(
                    "C40 FAIL: manifest-shape execution returned "
                    f"{_c40.returncode}: {_c40.stderr[-300:]}"
                )
            elif not _shape_exec_out.is_file():
                failures.append(
                    "C40 FAIL: manifest-shape execution wrote no output"
                )
            else:
                _exec = json.loads(
                    _shape_exec_out.read_text(encoding="utf-8")
                )
                _verdict = _exec.get("verdict")
                _status = _exec.get("status")
                if _verdict == "manifest_shape_execution_blocked_source_absent":
                    print(
                        "  C40 SKIP: manifest-shape execution source "
                        "checkpoint absent; probe recorded blocker"
                    )
                else:
                    _summary = _exec.get("executionSummary") or {}
                    _criteria = _exec.get("promotionCriteriaMet") or {}
                    _output = _exec.get("output") or {}
                    _blockers = set(_exec.get("blockers") or [])
                    _layers = _exec.get("layerRecords") or []
                    _all_layers_finite = all(
                        bool(row.get("hiddenFinite")) for row in _layers
                    )
                    _global_layers = _summary.get("globalAttentionLayerIndices")
                    _local_head_ok = _summary.get("localHeadDim") == 256
                    _global_head_ok = _summary.get("globalHeadDim") == 512
                    _depth_ok = (
                        _summary.get("numLayers") == 35
                        and _summary.get("layersExecuted") == 35
                        and len(_layers) == 35
                    )
                    _lm_ok = (
                        (_output.get("lmHeadSummary") or {}).get("finite")
                        is True
                        and len(_output.get("lmHeadTopK") or []) >= 1
                    )
                    _runtime_blocked = (
                        _criteria.get("doeRuntimeExecuted") is False
                        and _criteria.get("cslRuntimeExecuted") is False
                        and _criteria.get("hardwareExecuted") is False
                        and "doe_csl_manifest_shape_runtime_not_executed"
                        in _blockers
                    )
                    if (
                        _status == "succeeded"
                        and _verdict
                        == "manifest_shape_cpu_full_text_forward_passed"
                        and _criteria.get("manifestShapeExecuted") is True
                        and _criteria.get("fullLayerDepthExecuted") is True
                        and _criteria.get("lmHeadTopKComputed") is True
                        and _runtime_blocked
                        and _depth_ok
                        and _local_head_ok
                        and _global_head_ok
                        and _global_layers == [4, 9, 14, 19, 24, 29, 34]
                        and _summary.get("allLayerOutputsFinite") is True
                        and _output.get("finalHiddenFinite") is True
                        and _all_layers_finite
                        and _lm_ok
                    ):
                        print(
                            "  C40 PASS: manifest-shape CPU oracle "
                            "executes E2B text stack through 35 layers "
                            "and lm-head top-k while Doe/CSL runtime "
                            "claims remain blocked"
                        )
                    else:
                        failures.append(
                            "C40 FAIL: unexpected manifest-shape "
                            "execution state:\n"
                            f"    status={_status!r}, verdict={_verdict!r}\n"
                            f"    summary={_summary!r}\n"
                            f"    criteria={_criteria!r}\n"
                            f"    outputKeys={list(_output.keys())!r}\n"
                            f"    blockers={sorted(_blockers)!r}"
                        )
        except (OSError, ValueError, json.JSONDecodeError) as _e:
            failures.append(
                "C40 FAIL: manifest-shape execution evaluation error: "
                f"{type(_e).__name__}: {_e}"
            )

    # C41: Cerebras SDK 2.10 source compatibility. The active CSL
    # emitter surface must not reintroduce removed SDK-1.4-only
    # constructs, and fabric DSD declarations need explicit queues so
    # simulator/hardware receipts bind colors through queues instead
    # of removed/ deprecated SDK-1.4-era behavior.
    try:
        _c41_paths = list((REPO_ROOT / "runtime/zig/src/doe_wgsl").glob("emit_csl*.zig"))
        _c41_paths += list((REPO_ROOT / "runtime/zig/src/doe_wgsl").glob("csl_spec.zig"))
        _c41_paths += list(
            (REPO_ROOT / "runtime/zig/examples/simulator").glob(
                "*/compile/*/pe_program.csl"
            )
        )
        _c41_paths += list((REPO_ROOT / "examples/csl").glob("*/pe_program.csl"))
        _c41_bad = []
        for _path in sorted(set(_c41_paths)):
            if _path.name == "emit_csl_validate.zig":
                continue
            _rel = _path.relative_to(REPO_ROOT)
            _text = _path.read_text(encoding="utf-8")
            for _token in ("comptime_struct", "@concat_struct"):
                if _token in _text:
                    _c41_bad.append(f"{_rel}: removed SDK 2.10 token {_token}")
            _lines = _text.splitlines()
            for _idx, _line in enumerate(_lines):
                _window = "\n".join(_lines[_idx : _idx + 8])
                if "@get_dsd(fabin_dsd" in _line:
                    if ".input_queue" not in _window:
                        _c41_bad.append(
                            f"{_rel}:{_idx + 1}: fabin_dsd missing input_queue"
                        )
                    if ".fabric_color" in _window:
                        _c41_bad.append(
                            f"{_rel}:{_idx + 1}: fabin_dsd still uses fabric_color"
                        )
                if "@get_dsd(fabout_dsd" in _line:
                    if ".output_queue" not in _window:
                        _c41_bad.append(
                            f"{_rel}:{_idx + 1}: fabout_dsd missing output_queue"
                        )
                    if ".fabric_color" in _window:
                        _c41_bad.append(
                            f"{_rel}:{_idx + 1}: fabout_dsd still uses fabric_color"
                        )
        _spec_text = (
            REPO_ROOT / "runtime/zig/src/doe_wgsl/csl_spec.zig"
        ).read_text(encoding="utf-8")
        if 'CSLC_SDK_MIN_VERSION: []const u8 = "2.10.0"' not in _spec_text:
            _c41_bad.append("csl_spec.zig does not declare SDK 2.10.0 floor")
        if _c41_bad:
            failures.extend(f"C41 FAIL: {_bad}" for _bad in _c41_bad)
        else:
            print(
                "  C41 PASS: CSL emitters target SDK 2.10 params and "
                "queue-bound fabric DSDs"
            )
    except OSError as _e41:
        failures.append(f"C41 FAIL: SDK 2.10 source scan error: {_e41}")

    # C42: model-level SdkLayout layer-block execution promotion block.
    # The generated runner's successful simfabric run must be visible as
    # first-class model receipt evidence, not only nested primitive text.
    _sdk = receipt.get("sdkLayoutModelExecutionEvidence") or {}
    _c42_bad = []
    if not _sdk:
        _c42_bad.append("sdkLayoutModelExecutionEvidence missing")
    else:
        if _sdk.get("promotionStatus") != "sdk_layout_layer_block_smoke_promoted":
            _c42_bad.append(
                "promotionStatus="
                f"{_sdk.get('promotionStatus')!r}, expected promoted"
            )
        if _sdk.get("blockers") != []:
            _c42_bad.append(f"blockers not empty: {_sdk.get('blockers')!r}")
        _kernel = _sdk.get("kernelSource") or {}
        if _kernel.get("kernelIsStub") is not False:
            _c42_bad.append("kernelSource.kernelIsStub is not false")
        _plan = _sdk.get("streamExecutionPlan") or {}
        if not _plan.get("sha256"):
            _c42_bad.append("streamExecutionPlan.sha256 missing")
        _counts = _sdk.get("sendReceiveCounts") or {}
        if _counts.get("sends") != 3 or _counts.get("receives") != 1:
            _c42_bad.append(f"sendReceiveCounts mismatch: {_counts!r}")
        _stop = _sdk.get("runtimeStop") or {}
        if _stop.get("reached") is not True:
            _c42_bad.append("runtimeStop.reached is not true")
        _parity = _sdk.get("parity") or {}
        if _parity.get("promotionEligible") is not True:
            _c42_bad.append("parity.promotionEligible is not true")
        if _parity.get("tolerancePassed") is not True:
            _c42_bad.append("parity.tolerancePassed is not true")
        _telemetry = _sdk.get("hostSdkTelemetry") or {}
        if _telemetry.get("measurementSource") != "host_sdk_task_handles":
            _c42_bad.append("hostSdkTelemetry.measurementSource mismatch")
        _streams = _telemetry.get("streams") or []
        _stream_ids = {
            s.get("streamId") for s in _streams if isinstance(s, dict)
        }
        _expected_stream_ids = {
            "ple_rows_stream",
            "ple_projection_stream",
            "layer_weights_stream",
            "activation_out_stream",
        }
        if _stream_ids != _expected_stream_ids:
            _c42_bad.append(f"stream telemetry ids mismatch: {_stream_ids!r}")
        _host_io = _sdk.get("hostIoLayout") or []
        _host_io_ids = {
            s.get("streamId") for s in _host_io if isinstance(s, dict)
        }
        if _host_io_ids != _expected_stream_ids:
            _c42_bad.append(f"hostIoLayout ids mismatch: {_host_io_ids!r}")
        _artifacts = _sdk.get("simulatorArtifacts") or {}
        for _name in ("trace", "output"):
            _link = _artifacts.get(_name) or {}
            _path = _link.get("path")
            if not (_path and (REPO_ROOT / _path).is_file()):
                _c42_bad.append(f"simulatorArtifacts.{_name}.path missing")
            if not _link.get("sha256"):
                _c42_bad.append(f"simulatorArtifacts.{_name}.sha256 missing")
        _compile_dir = (_artifacts.get("compileDir") or {}).get("path")
        if not (_compile_dir and (REPO_ROOT / _compile_dir).is_dir()):
            _c42_bad.append("simulatorArtifacts.compileDir missing")
    if _c42_bad:
        failures.extend(f"C42 FAIL: {_bad}" for _bad in _c42_bad)
    else:
        print(
            "  C42 PASS: model receipt promotes generated E2B SdkLayout "
            "layer-block smoke with stream graph, telemetry, rt.stop, "
            "and parity evidence"
        )

    # C43: full-depth smoke diagnostics are model-receipt-visible but
    # still non-claimable. This locks the next rung toward full E2B
    # without allowing L35 smoke-chain files to masquerade as manifest-
    # shape or hardware evidence.
    _depth_diag = receipt.get("sdkLayoutDepthDiagnosticEvidence") or {}
    _c43_bad = []
    if not _depth_diag:
        _c43_bad.append("sdkLayoutDepthDiagnosticEvidence missing")
    else:
        if _depth_diag.get("status") != "full_depth_smoke_diagnostic_passed":
            _c43_bad.append(
                "status="
                f"{_depth_diag.get('status')!r}, expected diagnostic_passed"
            )
        if _depth_diag.get("claimable") is not False:
            _c43_bad.append("claimable is not false")
        if _depth_diag.get("manifestShapeRuntimeExecuted") is not False:
            _c43_bad.append("manifestShapeRuntimeExecuted is not false")
        if _depth_diag.get("declaredModelDepth") != 35:
            _c43_bad.append("declaredModelDepth is not 35")
        _remaining = set(_depth_diag.get("remainingClaimBlockers") or [])
        for _expected in (
            "full_manifest_shape_doe_csl_runtime_execution",
            "doppler_production_inference_parity",
            "cerebras_hardware_receipt",
        ):
            if _expected not in _remaining:
                _c43_bad.append(
                    f"remainingClaimBlockers missing {_expected}"
                )
        _diagnostics = _depth_diag.get("diagnostics") or []
        _sources = {
            d.get("sourceLabel") for d in _diagnostics
            if isinstance(d, dict)
        }
        _expected_sources = {
            "bf16_safetensors",
            "doppler_rdrr_q4k_int4ple",
        }
        if _sources != _expected_sources:
            _c43_bad.append(f"diagnostic sources mismatch: {_sources!r}")
        for _diag in _diagnostics:
            if not isinstance(_diag, dict):
                _c43_bad.append("diagnostic entry is not an object")
                continue
            _source = _diag.get("sourceLabel")
            if _diag.get("numLayers") != 35:
                _c43_bad.append(f"{_source}: numLayers is not 35")
            if _diag.get("claimable") is not False:
                _c43_bad.append(f"{_source}: claimable is not false")
            if _diag.get("blockers") != []:
                _c43_bad.append(
                    f"{_source}: diagnostic blockers not empty: "
                    f"{_diag.get('blockers')!r}"
                )
            _parity = _diag.get("parity") or {}
            if _parity.get("verdict") != "parity_passed":
                _c43_bad.append(f"{_source}: parity verdict not passed")
            if _parity.get("tolerancePassed") is not True:
                _c43_bad.append(f"{_source}: tolerance not passed")
            if _parity.get("layersCompared") != 35:
                _c43_bad.append(f"{_source}: layersCompared is not 35")
            for _label, _link in (
                ("parity", _parity),
                ("weightsAudit", _parity.get("weightsAudit") or {}),
                ("trace", _diag.get("trace") or {}),
                ("output", ((_diag.get("trace") or {}).get("output") or {})),
            ):
                _path = _link.get("path")
                if not (_path and (REPO_ROOT / _path).is_file()):
                    _c43_bad.append(f"{_source}: {_label} path missing")
                if not _link.get("sha256"):
                    _c43_bad.append(f"{_source}: {_label} sha256 missing")
            _trace = _diag.get("trace") or {}
            if _trace.get("status") != "succeeded":
                _c43_bad.append(f"{_source}: trace status not succeeded")
            if _trace.get("numLayersChained") != 35:
                _c43_bad.append(
                    f"{_source}: trace numLayersChained is not 35"
                )
            if _trace.get("runtimeStopReached") is not True:
                _c43_bad.append(f"{_source}: runtimeStop not reached")
            if _trace.get("kernelIsStub") is not False:
                _c43_bad.append(f"{_source}: kernelIsStub is not false")
            _counts = _trace.get("sendReceiveCounts") or {}
            if _counts.get("sends") != 3 or _counts.get("receives") != 1:
                _c43_bad.append(
                    f"{_source}: sendReceiveCounts mismatch: {_counts!r}"
                )
            _telemetry = _trace.get("hostSdkTelemetry") or {}
            if _telemetry.get("measurementSource") != "host_sdk_task_handles":
                _c43_bad.append(f"{_source}: telemetry source mismatch")
            if _telemetry.get("streamCount") != 4:
                _c43_bad.append(f"{_source}: streamCount is not 4")
    if _c43_bad:
        failures.extend(f"C43 FAIL: {_bad}" for _bad in _c43_bad)
    else:
        print(
            "  C43 PASS: model receipt binds full-depth E2B SdkLayout "
            "smoke diagnostics as non-claimable BF16 + RDRR evidence"
        )

    # C44: first manifest-shape SdkLayout runtime slice is visible in
    # the model receipt as partial evidence. This is intentionally
    # narrower than executionStatus: it proves the local/global head
    # dimensions plus grouped-KV attention-core diagnostic ran and
    # matched its CPU oracle, while full attention semantics, decoder
    # stack, logits, hardware, and performance remain blocked.
    _partial = receipt.get("manifestShapePartialExecutionEvidence") or {}
    _c44_bad = []
    if not _partial:
        _c44_bad.append("manifestShapePartialExecutionEvidence missing")
    else:
        if _partial.get("status") != "attention_core_runtime_slice_passed":
            _c44_bad.append(
                f"status={_partial.get('status')!r}, expected slice_passed"
            )
        if _partial.get("claimable") is not False:
            _c44_bad.append("claimable is not false")
        if _partial.get("blockers") != []:
            _c44_bad.append(f"blockers not empty: {_partial.get('blockers')!r}")
        _receipt_link = _partial.get("attentionCoreReceipt") or {}
        _receipt_path = _receipt_link.get("path")
        if not (_receipt_path and (REPO_ROOT / _receipt_path).is_file()):
            _c44_bad.append("attentionCoreReceipt path missing")
        if not _receipt_link.get("sha256"):
            _c44_bad.append("attentionCoreReceipt sha256 missing")
        _contract = _partial.get("manifestShapeContract") or {}
        if _contract.get("localHeadDim") != 256:
            _c44_bad.append("localHeadDim is not 256")
        if _contract.get("globalHeadDim") != 512:
            _c44_bad.append("globalHeadDim is not 512")
        if _contract.get("numKeyValueHeads") != 1:
            _c44_bad.append("numKeyValueHeads is not 1")
        _coverage = _partial.get("coverage") or {}
        for _field in (
            "localHeadDimExecuted",
            "globalHeadDimExecuted",
            "groupedKvExecuted",
            "attentionCoreCslRuntimeExecuted",
        ):
            if _coverage.get(_field) is not True:
                _c44_bad.append(f"coverage.{_field} is not true")
        for _field in (
            "embedUnembedExecuted",
            "logitsParityExecuted",
            "hardwareExecuted",
            "claimable",
        ):
            if _coverage.get(_field) is not False:
                _c44_bad.append(f"coverage.{_field} is not false")
        _semantic = _partial.get("semanticParity") or {}
        if _semantic.get("scope") != "attention_core_cpu_oracle_bit_exact":
            _c44_bad.append("semanticParity.scope mismatch")
        if _semantic.get("passed") is not True:
            _c44_bad.append("semanticParity.passed is not true")
        if _semantic.get("maxAbsErr") != 0.0:
            _c44_bad.append("semanticParity.maxAbsErr is not 0")
        if _semantic.get("queryHeadsCompared") != 16:
            _c44_bad.append("semanticParity.queryHeadsCompared is not 16")
        _grouped = _partial.get("groupedKvEvidence") or {}
        if _grouped.get("executed") is not True:
            _c44_bad.append("groupedKvEvidence.executed is not true")
        if _grouped.get("queryHeadsPerKvHead") != 8:
            _c44_bad.append("queryHeadsPerKvHead is not 8")
        _runs = _partial.get("shapeRuns") or []
        _run_kinds = {
            run.get("attentionKind") for run in _runs
            if isinstance(run, dict)
        }
        if _run_kinds != {"local", "global"}:
            _c44_bad.append(f"shape run kinds mismatch: {_run_kinds!r}")
        for _run in _runs:
            if not isinstance(_run, dict):
                _c44_bad.append("shape run is not an object")
                continue
            _kind = _run.get("attentionKind")
            if _run.get("status") != "succeeded":
                _c44_bad.append(f"{_kind}: status not succeeded")
            if _run.get("compileStatus") != "succeeded":
                _c44_bad.append(f"{_kind}: compileStatus not succeeded")
            if _run.get("runStatus") != "succeeded":
                _c44_bad.append(f"{_kind}: runStatus not succeeded")
            if _run.get("runtimeStopReached") is not True:
                _c44_bad.append(f"{_kind}: runtimeStop not reached")
            _parity = _run.get("numericalParity") or {}
            if _parity.get("passed") is not True:
                _c44_bad.append(f"{_kind}: numericalParity not passed")
            if _run.get("queryHeadsCompared") != 8:
                _c44_bad.append(f"{_kind}: queryHeadsCompared is not 8")
            if _run.get("queryHeadsPassed") != 8:
                _c44_bad.append(f"{_kind}: queryHeadsPassed is not 8")
            _compile_dir = (_run.get("compileDir") or {}).get("path")
            if not (_compile_dir and (REPO_ROOT / _compile_dir).is_dir()):
                _c44_bad.append(f"{_kind}: compileDir missing")
        _remaining = set(_partial.get("remainingClaimBlockers") or [])
        for _expected in (
            "full_attention_semantics_parity",
            "full_decoder_block_manifest_shape_execution",
            "embed_unembed_and_logits_parity",
            "cerebras_hardware_receipt",
        ):
            if _expected not in _remaining:
                _c44_bad.append(
                    f"remainingClaimBlockers missing {_expected}"
                )
    if _c44_bad:
        failures.extend(f"C44 FAIL: {_bad}" for _bad in _c44_bad)
    else:
        print(
            "  C44 PASS: model receipt binds partial manifest-shape "
            "attention-core SdkLayout execution with local/global heads, "
            "grouped KV, and CPU-oracle parity while full claims stay blocked"
        )

    # C45: Doppler WebGPU capture graph is model-receipt-visible. This
    # locks the shared-input contract: Doppler installs Doe's capture
    # provider through its normal Node WebGPU bootstrap, records WGSL
    # and command graph hashes, and still blocks HostPlan/SdkLayout/CSL
    # lowering claims until the captured graph is consumed downstream.
    _capture = receipt.get("dopplerWebgpuCaptureEvidence") or {}
    _c45_bad = []
    if not _capture:
        _c45_bad.append("dopplerWebgpuCaptureEvidence missing")
    else:
        if _capture.get("status") != "capture_graph_recorded":
            _c45_bad.append(
                f"status={_capture.get('status')!r}, expected recorded"
            )
        if _capture.get("claimable") is not False:
            _c45_bad.append("claimable is not false")
        if _capture.get("blockers") != []:
            _c45_bad.append(
                f"blockers not empty: {_capture.get('blockers')!r}"
            )
        _graph = _capture.get("captureGraph") or {}
        _graph_path = _graph.get("path")
        if not (_graph_path and (REPO_ROOT / _graph_path).is_file()):
            _c45_bad.append("captureGraph.path missing")
        if not _graph.get("sha256"):
            _c45_bad.append("captureGraph.sha256 missing")
        if not _graph.get("graphSha256"):
            _c45_bad.append("captureGraph.graphSha256 missing")
        _bootstrap = _capture.get("bootstrap") or {}
        if _bootstrap.get("sourceRepo") != "../doppler":
            _c45_bad.append("bootstrap.sourceRepo mismatch")
        if _bootstrap.get("providerModule") != "packages/doe-gpu/src/capture.js":
            _c45_bad.append("bootstrap.providerModule mismatch")
        if _bootstrap.get("providerInstalled") is not True:
            _c45_bad.append("providerInstalled is not true")
        if _bootstrap.get("adapterProbeSucceeded") is not True:
            _c45_bad.append("adapterProbeSucceeded is not true")
        _model = _capture.get("model") or {}
        if _model.get("modelId") != "gemma-4-e2b-it-q4k-ehf16-af32":
            _c45_bad.append("model.modelId mismatch")
        _arch = _model.get("architecture") or {}
        if _arch.get("headDim") != 256:
            _c45_bad.append("architecture.headDim is not 256")
        if _arch.get("globalHeadDim") != 512:
            _c45_bad.append("architecture.globalHeadDim is not 512")
        if _arch.get("numKeyValueHeads") != 1:
            _c45_bad.append("architecture.numKeyValueHeads is not 1")
        _subset = _capture.get("webgpuSubset") or {}
        if "device.createShaderModule" not in (
            _subset.get("supportedWebgpuMethods") or []
        ):
            _c45_bad.append("supportedWebgpuMethods missing shader module")
        if _subset.get("recordedUnsupportedCalls") != []:
            _c45_bad.append("recordedUnsupportedCalls not empty")
        if not _subset.get("shaderWgslSha256"):
            _c45_bad.append("shaderWgslSha256 missing")
        _counts = _capture.get("counts") or {}
        for _field in (
            "buffers",
            "bufferWrites",
            "shaderModules",
            "computePipelines",
            "commandBuffers",
            "submissions",
            "readbacks",
        ):
            if int(_counts.get(_field, 0)) < 1:
                _c45_bad.append(f"counts.{_field} < 1")
        if _counts.get("unsupported") != 0:
            _c45_bad.append("counts.unsupported is not 0")
        _lowering = _capture.get("lowering") or {}
        if _lowering.get("status") != "pending_hostplan_lowering":
            _c45_bad.append("lowering.status mismatch")
        if _lowering.get("hostPlanLinked") is not False:
            _c45_bad.append("lowering.hostPlanLinked is not false")
        if not _lowering.get("sourceGraphSha256"):
            _c45_bad.append("lowering.sourceGraphSha256 missing")
        _remaining = set(_capture.get("remainingClaimBlockers") or [])
        for _expected in (
            "captured_graph_to_hostplan_lowering",
            "hostplan_to_sdklayout_compile",
            "csl_simulator_parity_against_doppler_runtime",
            "cerebras_hardware_receipt",
        ):
            if _expected not in _remaining:
                _c45_bad.append(
                    f"remainingClaimBlockers missing {_expected}"
                )
    if _c45_bad:
        failures.extend(f"C45 FAIL: {_bad}" for _bad in _c45_bad)
    else:
        print(
            "  C45 PASS: model receipt binds Doppler Gemma-4 WebGPU "
            "capture graph as shared JS/WGSL input while full graph "
            "lowering claims remain blocked"
        )

    # C46: first captured-graph lowering receipt is model-receipt-visible.
    # This does not promote full inference. It proves the current capture
    # graph hash is consumed by the attention-core SdkLayout/CSL slice and
    # that the resulting simulator parity remains CPU-oracle scoped.
    _capture_lowering = (
        receipt.get("dopplerWebgpuCaptureLoweringEvidence") or {}
    )
    _c46_bad = []
    if not _capture_lowering:
        _c46_bad.append("dopplerWebgpuCaptureLoweringEvidence missing")
    else:
        if _capture_lowering.get("status") != (
            "attention_core_capture_slice_lowered_and_simulated"
        ):
            _c46_bad.append(
                f"status={_capture_lowering.get('status')!r}, "
                "expected attention-core lowering"
            )
        if _capture_lowering.get("claimable") is not False:
            _c46_bad.append("claimable is not false")
        if _capture_lowering.get("blockers") != []:
            _c46_bad.append(
                f"blockers not empty: {_capture_lowering.get('blockers')!r}"
            )
        _lowering_receipt = _capture_lowering.get("loweringReceipt") or {}
        _lowering_path = _lowering_receipt.get("path")
        if not (_lowering_path and (REPO_ROOT / _lowering_path).is_file()):
            _c46_bad.append("loweringReceipt.path missing")
        if not _lowering_receipt.get("sha256"):
            _c46_bad.append("loweringReceipt.sha256 missing")
        _capture_graph_sha = (
            (receipt.get("dopplerWebgpuCaptureEvidence") or {})
            .get("captureGraph", {})
            .get("graphSha256")
        )
        if _lowering_receipt.get("sourceGraphSha256") != _capture_graph_sha:
            _c46_bad.append("sourceGraphSha256 does not match capture graph")
        _lowering_source = _capture_lowering.get("source") or {}
        _lowering_graph = _lowering_source.get("captureGraph") or {}
        if _lowering_graph.get("graphSha256") != _capture_graph_sha:
            _c46_bad.append("source.captureGraph.graphSha256 mismatch")
        if not (_lowering_source.get("shaderModules") or []):
            _c46_bad.append("source.shaderModules missing")
        _host_view = _capture_lowering.get("capturedHostPlanView") or {}
        if _host_view.get("workload") != (
            "gemma4_e2b_manifest_shape_grouped_kv_capture_smoke"
        ):
            _c46_bad.append("capturedHostPlanView.workload mismatch")
        if int(_host_view.get("workgroupDispatchCount", 0)) < 1:
            _c46_bad.append("workgroupDispatchCount < 1")
        if int(_host_view.get("bindingCount", 0)) < 4:
            _c46_bad.append("bindingCount < 4")
        if "grouped_kv_projection_input" not in (
            _host_view.get("bufferRoles") or []
        ):
            _c46_bad.append("grouped KV buffer role missing")
        _lowered = _capture_lowering.get("loweredArtifacts") or {}
        if _lowered.get("sdkVersionFloor") != "2.10.0":
            _c46_bad.append("sdkVersionFloor mismatch")
        for _field in (
            "pythonSdkLayoutRunner",
            "cslKernel",
            "attentionCoreReceipt",
        ):
            _link = _lowered.get(_field) or {}
            _path = _link.get("path")
            if not (_path and (REPO_ROOT / _path).is_file()):
                _c46_bad.append(f"loweredArtifacts.{_field}.path missing")
            if not _link.get("sha256"):
                _c46_bad.append(f"loweredArtifacts.{_field}.sha256 missing")
        _sim = _capture_lowering.get("simulatorEvidence") or {}
        _semantic = _sim.get("semanticParity") or {}
        if _sim.get("status") != "succeeded":
            _c46_bad.append("simulatorEvidence.status mismatch")
        if _sim.get("hardwareExecuted") is not False:
            _c46_bad.append("hardwareExecuted is not false")
        if _semantic.get("passed") is not True:
            _c46_bad.append("semanticParity.passed is not true")
        if _semantic.get("scope") != "attention_core_cpu_oracle_bit_exact":
            _c46_bad.append("semanticParity.scope mismatch")
        if _semantic.get("againstDopplerProductionInference") is not False:
            _c46_bad.append(
                "semanticParity claims Doppler production inference"
            )
        _remaining = set(_capture_lowering.get("remainingClaimBlockers") or [])
        for _expected in (
            "ordinary_doppler_inference_graph_capture",
            "full_captured_webgpu_graph_to_hostplan_lowering",
            "automated_wgsl_to_csl_kernel_lowering",
            "embed_unembed_decoder_logits_parity",
            "cerebras_hardware_receipt",
        ):
            if _expected not in _remaining:
                _c46_bad.append(
                    f"remainingClaimBlockers missing {_expected}"
                )
    if _c46_bad:
        failures.extend(f"C46 FAIL: {_bad}" for _bad in _c46_bad)
    else:
        print(
            "  C46 PASS: model receipt binds the captured WebGPU graph "
            "to the first attention-core SdkLayout/CSL lowering receipt "
            "with CPU-oracle parity and full-inference blockers intact"
        )

    # C27: emulator lane's runCslWebGpuEmulator() soft-fails the CSL
    # contract check when a matching-depth trace is absent — WGSL
    # must always execute, contract check is an independent axis.
    # Structural regression lock: isolate the function body and assert
    # (1) a try/catch wraps loadCslSemanticTrace, (2) the catch branch
    # sets status="unchecked", (3) the return object emits cslContract.
    # Checking inside the function body (not the whole file) prevents
    # false-passes from comments or variable-name coincidences.
    _main_js = REPO_ROOT / "demos/gemma4-e2b-csl-sim/main.js"
    if _main_js.is_file():
        _js = _main_js.read_text(encoding="utf-8")
        _c27_fails = []
        _sig = "async function runCslWebGpuEmulator()"
        _sig_idx = _js.find(_sig)
        if _sig_idx < 0:
            _c27_fails.append("runCslWebGpuEmulator signature missing from main.js")
        else:
            # Extract the function body by brace-matching from the
            # first '{' after the signature.
            _brace_open = _js.find("{", _sig_idx)
            _depth = 0
            _brace_close = -1
            for _i in range(_brace_open, len(_js)):
                _ch = _js[_i]
                if _ch == "{":
                    _depth += 1
                elif _ch == "}":
                    _depth -= 1
                    if _depth == 0:
                        _brace_close = _i
                        break
            if _brace_close < 0:
                _c27_fails.append(
                    "could not find matching closing brace for "
                    "runCslWebGpuEmulator — parse failure"
                )
            else:
                _body = _js[_brace_open : _brace_close + 1]
                # Strip single-line and block comments so comment text
                # can't satisfy the structural requirements.
                import re as _re_c27
                _body_code = _re_c27.sub(r"//[^\n]*", "", _body)
                _body_code = _re_c27.sub(
                    r"/\*.*?\*/", "", _body_code, flags=_re_c27.DOTALL
                )
                if "loadCslSemanticTrace(" not in _body_code:
                    _c27_fails.append(
                        "runCslWebGpuEmulator no longer calls "
                        "loadCslSemanticTrace — contract check path removed"
                    )
                if "try" not in _body_code or "catch" not in _body_code:
                    _c27_fails.append(
                        "runCslWebGpuEmulator lost its try/catch around "
                        "loadCslSemanticTrace — L>=2 will hard-fail "
                        "without a trace"
                    )
                # Ordering invariant: executeLayerBlockWebGpu() must
                # run BEFORE the try/catch, so WGSL executes regardless
                # of trace availability. If someone moves it inside the
                # try, the whole soft-fail contract breaks.
                _exec_idx = _body_code.find("executeLayerBlockWebGpu(")
                _try_idx = _body_code.find("try")
                if _exec_idx < 0:
                    _c27_fails.append(
                        "runCslWebGpuEmulator no longer calls "
                        "executeLayerBlockWebGpu — WGSL path removed"
                    )
                elif _try_idx >= 0 and _exec_idx > _try_idx:
                    _c27_fails.append(
                        "runCslWebGpuEmulator now calls "
                        "executeLayerBlockWebGpu inside or after the "
                        "try/catch — WGSL would be skipped on trace "
                        "failure, breaking soft-fail contract"
                    )
                if 'status: "unchecked"' not in _body_code and \
                   "status: 'unchecked'" not in _body_code:
                    _c27_fails.append(
                        "runCslWebGpuEmulator no longer sets "
                        'status: "unchecked" in the catch branch — '
                        "soft-fail contract removed"
                    )
                if "cslContract:" not in _body_code:
                    _c27_fails.append(
                        "runCslWebGpuEmulator return object no longer "
                        "emits cslContract field — viewers can't "
                        "distinguish verified from unchecked"
                    )
        if _c27_fails:
            for _f in _c27_fails:
                failures.append(f"C27 FAIL: {_f}")
        else:
            print(
                "  C27 PASS: emulator lane soft-fails CSL contract "
                "check when no matching-depth trace exists (WGSL runs "
                "before try/catch + unchecked branch + cslContract field)"
            )

    # C28: three-way sync for bundle-doc skip lists. The packer
    # promotes 4 repo docs to archive-root names. Both the repo
    # claim-discipline gate (source paths) and the archive verifier
    # (archive-root paths) must skip these — they are rule-enumerating
    # by design and name the forbidden phrases the gate rejects. If
    # someone adds a new bundle doc without updating both lists, the
    # next run will either flag the doc's rule prose (false positive)
    # or silently skip a doc that isn't actually governance-grade.
    _packer_path = REPO_ROOT / "bench/tools/pack_cerebras_validation_archive.py"
    _gate_path = REPO_ROOT / "bench/gates/claim_discipline_gate.py"
    _verifier_path = REPO_ROOT / "bench/tools/verify_cerebras_validation_archive.py"
    _c28_fails: list[str] = []
    if not _packer_path.is_file():
        _c28_fails.append("packer missing")
    elif not _gate_path.is_file():
        _c28_fails.append("claim-discipline gate missing")
    elif not _verifier_path.is_file():
        _c28_fails.append("verifier missing")
    else:
        import ast as _ast_c28
        _packer_tree = _ast_c28.parse(_packer_path.read_text(encoding="utf-8"))
        _include_files_tuples: list[tuple[str, str]] = []
        for _node in _ast_c28.walk(_packer_tree):
            _tgt_name = None
            _val = None
            if isinstance(_node, _ast_c28.Assign):
                for _tgt in _node.targets:
                    if isinstance(_tgt, _ast_c28.Name):
                        _tgt_name = _tgt.id
                        _val = _node.value
                        break
            elif isinstance(_node, _ast_c28.AnnAssign):
                if isinstance(_node.target, _ast_c28.Name):
                    _tgt_name = _node.target.id
                    _val = _node.value
            if _tgt_name == "INCLUDE_FILES" and isinstance(
                _val, (_ast_c28.Tuple, _ast_c28.List)
            ):
                for _elt in _val.elts:
                    if (isinstance(_elt, (_ast_c28.Tuple, _ast_c28.List))
                            and len(_elt.elts) == 2
                            and isinstance(_elt.elts[0], _ast_c28.Constant)
                            and isinstance(_elt.elts[1], _ast_c28.Constant)):
                        _include_files_tuples.append(
                            (_elt.elts[0].value, _elt.elts[1].value)
                        )
        _bundle_doc_pairs = [
            (src, dst) for (src, dst) in _include_files_tuples
            if src.startswith("docs/cerebras-evidence-bundle-")
            and src.endswith(".md")
        ]
        if not _bundle_doc_pairs:
            _c28_fails.append(
                "packer INCLUDE_FILES has no cerebras-evidence-bundle "
                "docs — inventory lost?"
            )
        # Use AST to extract the actual literal values, not string
        # slicing (which trips on parens inside comments). For the gate,
        # SKIP_PREFIXES is annotated-assigned to a Tuple[Constant, ...];
        # for the verifier, CLAIM_SCAN_SKIP_ARCHIVE_PATHS is assigned to
        # a Set[Constant, ...].
        def _extract_string_literals(path: Path, var_name: str) -> set[str]:
            _tree = _ast_c28.parse(path.read_text(encoding="utf-8"))
            for _n in _ast_c28.walk(_tree):
                _tn = None
                _tv = None
                if isinstance(_n, _ast_c28.Assign):
                    for _t in _n.targets:
                        if isinstance(_t, _ast_c28.Name) and _t.id == var_name:
                            _tn, _tv = _t.id, _n.value
                            break
                elif isinstance(_n, _ast_c28.AnnAssign):
                    if (isinstance(_n.target, _ast_c28.Name)
                            and _n.target.id == var_name):
                        _tn, _tv = _n.target.id, _n.value
                if _tn == var_name and isinstance(
                    _tv, (_ast_c28.Tuple, _ast_c28.List, _ast_c28.Set)
                ):
                    out: set[str] = set()
                    for _e in _tv.elts:
                        if isinstance(_e, _ast_c28.Constant) and isinstance(
                            _e.value, str
                        ):
                            out.add(_e.value)
                    return out
            return set()

        _gate_skip_paths = _extract_string_literals(
            _gate_path, "SKIP_PREFIXES"
        )
        _verifier_skip_paths = _extract_string_literals(
            _verifier_path, "CLAIM_SCAN_SKIP_ARCHIVE_PATHS"
        )
        if not _gate_skip_paths:
            _c28_fails.append(
                "could not extract SKIP_PREFIXES literals from gate"
            )
        if not _verifier_skip_paths:
            _c28_fails.append(
                "could not extract CLAIM_SCAN_SKIP_ARCHIVE_PATHS "
                "literals from verifier"
            )
        for _src, _dst in _bundle_doc_pairs:
            if _gate_skip_paths and _src not in _gate_skip_paths:
                _c28_fails.append(
                    f"gate SKIP_PREFIXES missing bundle doc "
                    f"source path: {_src}"
                )
            if _verifier_skip_paths and _dst not in _verifier_skip_paths:
                _c28_fails.append(
                    f"verifier CLAIM_SCAN_SKIP_ARCHIVE_PATHS missing "
                    f"archive-root path: {_dst}"
                )
    if _c28_fails:
        for _f in _c28_fails:
            failures.append(f"C28 FAIL: {_f}")
    else:
        print(
            f"  C28 PASS: bundle-doc skip-lists in sync across packer + "
            f"gate + verifier ({len(_bundle_doc_pairs)} docs)"
        )

    # C29: negative contract. docs/cerebras-evidence-bundle-pointer.md
    # must NOT appear in packer INCLUDE_FILES. The prep script writes
    # the pointer AFTER pack, so including it would always ship a
    # stale-lag copy with the previous build's archive hash. Comment
    # at packer line ~77 records this intent; C29 enforces it.
    # Walk the INCLUDE_FILES AST subtree for any Constant whose value
    # is the pointer path — catches both bare-string entries and
    # tuple-form (src, dst) entries without a scan of the raw text.
    _pointer_src = "docs/cerebras-evidence-bundle-pointer.md"
    _pointer_in_packer_literal = False
    _packer_tree2 = _ast_c28.parse(_packer_path.read_text(encoding="utf-8"))
    for _n in _ast_c28.walk(_packer_tree2):
        _tv = None
        if isinstance(_n, _ast_c28.AnnAssign) and isinstance(
            _n.target, _ast_c28.Name
        ) and _n.target.id == "INCLUDE_FILES":
            _tv = _n.value
        elif isinstance(_n, _ast_c28.Assign):
            for _t in _n.targets:
                if isinstance(_t, _ast_c28.Name) and _t.id == "INCLUDE_FILES":
                    _tv = _n.value
                    break
        if _tv is not None:
            for _const in _ast_c28.walk(_tv):
                if (isinstance(_const, _ast_c28.Constant)
                        and _const.value == _pointer_src):
                    _pointer_in_packer_literal = True
                    break
    if _pointer_in_packer_literal:
        failures.append(
            f"C29 FAIL: {_pointer_src} is in packer INCLUDE_FILES — "
            "bundling the pointer doc always ships stale-lag hashes "
            "(prep script writes it AFTER pack). Remove it from "
            "INCLUDE_FILES; BUNDLE_META.json inside the archive is "
            "the authoritative reference."
        )
    else:
        print(
            f"  C29 PASS: {_pointer_src} is NOT in packer "
            "INCLUDE_FILES (stale-lag guard holds)"
        )

    # C30: prep-script stage ordering is load-bearing. The shell script
    # chains gates -> pack -> verify -> pointer-write. `set -euo
    # pipefail` means any failing earlier stage aborts the chain, so
    # the pointer is never written from an unverified bundle -- but
    # only if the pointer-write block is AFTER verify in file order.
    # If someone refactors the script and moves the pointer block up
    # (before verify), a bundle that fails verify still mints a
    # pointer doc that lies about what was built. Regression-lock the
    # ordering by substring position.
    _prep_path = REPO_ROOT / "bench/tools/prepare_cerebras_validation_bundle.sh"
    _c30_fails: list[str] = []
    if not _prep_path.is_file():
        _c30_fails.append("prep script missing")
    else:
        _prep_src = _prep_path.read_text(encoding="utf-8")
        _gates_idx = _prep_src.find("run_cerebras_evidence_bundle.py")
        _pack_idx = _prep_src.find("pack_cerebras_validation_archive.py")
        _verify_idx = _prep_src.find("verify_cerebras_validation_archive.py")
        _pointer_write_idx = _prep_src.find('cat > "$POINTER"')
        if _gates_idx < 0:
            _c30_fails.append("prep script no longer invokes gates stage")
        if _pack_idx < 0:
            _c30_fails.append("prep script no longer invokes pack stage")
        if _verify_idx < 0:
            _c30_fails.append("prep script no longer invokes verify stage")
        if _pointer_write_idx < 0:
            _c30_fails.append(
                'prep script no longer writes pointer '
                '(cat > "$POINTER" missing)'
            )
        if not _c30_fails:
            # Use the step-label strings ("1/3  gates:", "2/3  pack:",
            # "3/3  verify:") as unique anchors — the script names
            # themselves appear in docstrings and heredocs too.
            _step_gates = _prep_src.find('"1/3  gates:')
            _step_pack = _prep_src.find('"2/3  pack:')
            _step_verify = _prep_src.find('"3/3  verify:')
            if _step_gates < 0 or _step_pack < 0 or _step_verify < 0:
                _c30_fails.append(
                    "prep script step labels drifted; expected "
                    '"1/3  gates:", "2/3  pack:", "3/3  verify:"'
                )
            elif not (_step_gates < _step_pack < _step_verify):
                _c30_fails.append(
                    "prep script stage order drifted from "
                    "gates -> pack -> verify"
                )
            elif _pointer_write_idx < _step_verify:
                _c30_fails.append(
                    "prep script writes pointer doc BEFORE verify "
                    "stage — a failing verify would still produce "
                    "a pointer that lies about what was built"
                )
    if _c30_fails:
        for _f in _c30_fails:
            failures.append(f"C30 FAIL: {_f}")
    else:
        print(
            "  C30 PASS: prep-script ordering holds "
            "(gates -> pack -> verify -> pointer-write)"
        )

    # C31: cerebras-evidence-bundle-tools.md lists every on-disk
    # cerebras-* tool in bench/tools/. Catches drift when a new tool
    # is added without being documented, or when a tool is renamed
    # without updating the index. Narrow by design: only scans
    # bench/tools/*cerebras* (the scope the index doc claims).
    _tools_dir = REPO_ROOT / "bench/tools"
    _index_path = _tools_dir / "cerebras-evidence-bundle-tools.md"
    _c31_fails: list[str] = []
    if not _index_path.is_file():
        _c31_fails.append("bundle tools index missing")
    else:
        _tool_files = sorted(
            p.name for p in _tools_dir.iterdir()
            if p.is_file()
            and "cerebras" in p.name.lower()
            and p.name != _index_path.name
        )
        if not _tool_files:
            _c31_fails.append(
                "no bench/tools/*cerebras* files found — did the "
                "tool directory move?"
            )
        else:
            _index_src = _index_path.read_text(encoding="utf-8")
            _missing = [t for t in _tool_files if t not in _index_src]
            if _missing:
                _c31_fails.append(
                    "bundle tools index does not mention "
                    + ", ".join(_missing)
                )
    if _c31_fails:
        for _f in _c31_fails:
            failures.append(f"C31 FAIL: {_f}")
    else:
        print(
            f"  C31 PASS: bundle tools index lists all {len(_tool_files)} "
            f"cerebras-* tools in bench/tools/"
        )

    # C33: every error-to-preview path in the E2B demo must pipe
    # through stripAnsi(). cs_python's stderr preserves ANSI escape
    # codes that render as literal garbage in the browser; an earlier
    # tick added stripAnsi() but a refactor could silently drop the
    # wrapper. Structural lock: (1) stripAnsi function exists, (2)
    # every `el("<lane>-preview").textContent = String(err...)` call
    # is wrapped. If a new lane's error path forgets stripAnsi, C33
    # fires.
    _main_js_c33 = REPO_ROOT / "demos/gemma4-e2b-csl-sim/main.js"
    _c33_fails: list[str] = []
    if not _main_js_c33.is_file():
        _c33_fails.append("demo main.js missing")
    else:
        _js_c33 = _main_js_c33.read_text(encoding="utf-8")
        if "function stripAnsi(" not in _js_c33:
            _c33_fails.append(
                "stripAnsi() function missing from main.js — ANSI "
                "codes will leak back into the error preview panes"
            )
        if "function formatRunnerError(" not in _js_c33:
            _c33_fails.append(
                "formatRunnerError() function missing from main.js — "
                "runner-failure JSON will render as raw text with \\n "
                "literals instead of unescaped stderr"
            )
        if not _c33_fails:
            import re as _re_c33
            # Find every `.textContent = ...err...` assignment. If the
            # RHS doesn't contain stripAnsi, that's a bypass.
            _leaks = []
            for _m in _re_c33.finditer(
                r'\.textContent\s*=\s*([^;]*err[^;]*);',
                _js_c33,
            ):
                _rhs = _m.group(1)
                if "stripAnsi" not in _rhs:
                    _leaks.append(_rhs.strip()[:80])
            if _leaks:
                _c33_fails.append(
                    "error-to-preview assignment(s) bypass "
                    f"stripAnsi: {_leaks}"
                )
    if _c33_fails:
        for _f in _c33_fails:
            failures.append(f"C33 FAIL: {_f}")
    else:
        print(
            "  C33 PASS: demo error-to-preview paths all pipe "
            "through stripAnsi (no ANSI leak)"
        )

    # C26: summarize_cerebras_evidence_archive.sh succeeds against
    # the most recent archive. Integration-lock: catches a format drift
    # in BUNDLE_META / MANIFEST / lane-status that would break the jq
    # one-liner before a reviewer tries to run it on their copy.
    # Skips cleanly when no archive exists yet.
    import subprocess as _subprocess_c26
    import glob as _glob_c26
    _archives = sorted(
        _glob_c26.glob(str(REPO_ROOT / "bench/out/doe-cerebras-evidence-*.tar.gz")),
        key=lambda p: Path(p).stat().st_mtime if Path(p).is_file() else 0,
        reverse=True,
    )
    if not _archives:
        print(
            "  C26 SKIP: no doe-cerebras-evidence-*.tar.gz archive "
            "present; run prepare_cerebras_validation_bundle.sh to "
            "produce one"
        )
    else:
        _latest = _archives[0]
        _c26_proc = _subprocess_c26.run(
            ["bash",
             str(REPO_ROOT / "bench/tools/summarize_cerebras_evidence_archive.sh"),
             _latest],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if _c26_proc.returncode != 0:
            failures.append(
                f"C26 FAIL: summarize script returned "
                f"{_c26_proc.returncode} on {Path(_latest).name}: "
                f"{_c26_proc.stderr.strip()[:200]}"
            )
        elif "BUNDLE META" not in _c26_proc.stdout:
            failures.append(
                "C26 FAIL: summarize output missing expected "
                "'BUNDLE META' section header — format drift?"
            )
        else:
            print(
                f"  C26 PASS: summarize script runs cleanly on "
                f"{Path(_latest).name} and emits expected sections"
            )

    # C25: every data-copy-for attribute in the SDK-GUI viewer HTML
    # points at an element with matching id in the same file. Catches
    # the class of bug where a copy button references a source id
    # that was renamed or removed — the button would silently do
    # nothing at runtime.
    _viewer_html = REPO_ROOT / "demos/doe-sdk-gui-viewer/index.html"
    if _viewer_html.is_file():
        import re as _re_c25
        _html = _viewer_html.read_text(encoding="utf-8")
        _copy_for_ids = _re_c25.findall(r'data-copy-for="([^"]+)"', _html)
        _element_ids = set(_re_c25.findall(r'\bid="([^"]+)"', _html))
        _missing_targets = [
            tid for tid in _copy_for_ids if tid not in _element_ids
        ]
        if _missing_targets:
            for _m in _missing_targets:
                failures.append(
                    f"C25 FAIL: data-copy-for={_m!r} has no matching id in "
                    f"demos/doe-sdk-gui-viewer/index.html — copy button "
                    f"would silently no-op"
                )
        else:
            print(
                f"  C25 PASS: all {len(_copy_for_ids)} data-copy-for "
                f"targets in SDK-GUI viewer resolve to real element ids"
            )

    # C24: bash -n syntax check on the bundle shell scripts. Catches
    # shell syntax errors (unclosed if, missing fi, stray backticks,
    # malformed heredocs) without executing the pipeline. Fast — it
    # parses only, does not invoke bash subshells.
    _shell_scripts = [
        "bench/tools/prepare_cerebras_validation_bundle.sh",
        "bench/tools/summarize_cerebras_evidence_archive.sh",
    ]
    _c24_fails = []
    for _rel in _shell_scripts:
        _p = REPO_ROOT / _rel
        if not _p.is_file():
            _c24_fails.append(f"{_rel}: missing")
            continue
        import subprocess as _subprocess_c24
        _c24_proc = _subprocess_c24.run(
            ["bash", "-n", str(_p)],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if _c24_proc.returncode != 0:
            _c24_fails.append(
                f"{_rel}: bash -n failed (rc={_c24_proc.returncode}): "
                f"{_c24_proc.stderr.strip()[:200]}"
            )
    if _c24_fails:
        for _f in _c24_fails:
            failures.append(f"C24 FAIL: {_f}")
    else:
        print(
            f"  C24 PASS: {len(_shell_scripts)} bundle shell scripts "
            "parse with bash -n"
        )

    # C23: packer's extension deny-list matches verifier's
    # FORBIDDEN_EXTENSIONS. Both protect against SDK binaries, tensor
    # bytes, and log content. They're maintained in separate files
    # and drift between them is a real risk — e.g. the packer blocks
    # `.f32` but if the verifier didn't, a hand-edited archive could
    # slip those in. Lock the intersection here.
    _packer_py_c23 = REPO_ROOT / "bench/tools/pack_cerebras_validation_archive.py"
    _verifier_py_c23 = REPO_ROOT / "bench/tools/verify_cerebras_validation_archive.py"
    if _packer_py_c23.is_file() and _verifier_py_c23.is_file():
        try:
            import importlib.util as _ilu_c23
            _p_spec = _ilu_c23.spec_from_file_location("_p_c23", str(_packer_py_c23))
            _p_mod = _ilu_c23.module_from_spec(_p_spec)
            _p_spec.loader.exec_module(_p_mod)  # type: ignore[union-attr]
            _v_spec = _ilu_c23.spec_from_file_location("_v_c23", str(_verifier_py_c23))
            _v_mod = _ilu_c23.module_from_spec(_v_spec)
            _v_spec.loader.exec_module(_v_mod)  # type: ignore[union-attr]
            # Packer stores path-fragment denials; extract the subset
            # that are extensions (start with '.' and have no '/').
            _packer_exts = {
                _s for _s in _p_mod.EXCLUDE_SUBSTRINGS
                if _s.startswith(".") and "/" not in _s
            }
            _verifier_exts = set(_v_mod.FORBIDDEN_EXTENSIONS)
            _c23_fails = []
            _only_in_packer = _packer_exts - _verifier_exts
            _only_in_verifier = _verifier_exts - _packer_exts
            if _only_in_packer:
                _c23_fails.append(
                    f"extensions in packer deny-list but not verifier's "
                    f"FORBIDDEN_EXTENSIONS: {sorted(_only_in_packer)}"
                )
            if _only_in_verifier:
                _c23_fails.append(
                    f"extensions in verifier FORBIDDEN_EXTENSIONS but not "
                    f"packer deny-list: {sorted(_only_in_verifier)}"
                )
            if _c23_fails:
                for _f in _c23_fails:
                    failures.append(f"C23 FAIL: {_f}")
            else:
                print(
                    f"  C23 PASS: packer deny-list extensions and "
                    f"verifier FORBIDDEN_EXTENSIONS in sync "
                    f"({len(_packer_exts)} extensions)"
                )

            # C32: path-substring deny-list sync. Mirrors C23 for
            # non-extension entries: packer's EXCLUDE_SUBSTRINGS has
            # path fragments like '/scratch/', '/compile/',
            # 'simulator.log' that would slip past an extension-only
            # verifier check. Sync with verifier FORBIDDEN_PATH_SUBSTRINGS.
            _packer_path_substrs = {
                _s for _s in _p_mod.EXCLUDE_SUBSTRINGS
                if not (_s.startswith(".") and "/" not in _s)
            }
            _verifier_path_substrs = set(
                getattr(_v_mod, "FORBIDDEN_PATH_SUBSTRINGS", set())
            )
            _c32_fails = []
            _only_in_pack_substrs = _packer_path_substrs - _verifier_path_substrs
            _only_in_ver_substrs = _verifier_path_substrs - _packer_path_substrs
            if _only_in_pack_substrs:
                _c32_fails.append(
                    f"path substrings in packer deny-list but not "
                    f"verifier FORBIDDEN_PATH_SUBSTRINGS: "
                    f"{sorted(_only_in_pack_substrs)}"
                )
            if _only_in_ver_substrs:
                _c32_fails.append(
                    f"path substrings in verifier "
                    f"FORBIDDEN_PATH_SUBSTRINGS but not packer "
                    f"deny-list: {sorted(_only_in_ver_substrs)}"
                )
            if _c32_fails:
                for _f in _c32_fails:
                    failures.append(f"C32 FAIL: {_f}")
            else:
                print(
                    f"  C32 PASS: packer path-substring deny-list and "
                    f"verifier FORBIDDEN_PATH_SUBSTRINGS in sync "
                    f"({len(_packer_path_substrs)} substrings)"
                )
        except (OSError, ImportError, AttributeError) as _e23:
            failures.append(f"C23 FAIL: cannot import packer/verifier: {_e23}")

    # C34: four governance docs name both hardware-validation paths
    # (Path A = endpoint access, Path B = Cerebras-assisted bundle run).
    # Matches the ask in the external email so the bundle's story
    # doesn't drift from what we told Cerebras. Each doc is checked
    # independently — if any one silently drops Path B, C34 fires with
    # a distinct message pointing at the specific doc.
    _two_path_docs = [
        "docs/cerebras-evidence-bundle-ask.md",
        "docs/cerebras-evidence-bundle-readme.md",
        "docs/cerebras-evidence-bundle-claim-scope.md",
        "docs/hardware-validation-appendix.md",
    ]
    _c34_fails: list[str] = []
    for _rel in _two_path_docs:
        _p = REPO_ROOT / _rel
        if not _p.is_file():
            _c34_fails.append(f"governance doc missing: {_rel}")
            continue
        _body = _p.read_text(encoding="utf-8").lower()
        # Path A marker: endpoint access / --cmaddr. Path B marker:
        # "cerebras-assisted" or "bundle run" phrasing. Both must be
        # mentioned somewhere in the body for the doc to reflect the
        # external ask correctly.
        _has_path_a = ("endpoint" in _body and
                       ("--cmaddr" in _body or "access" in _body))
        _has_path_b = "cerebras-assisted" in _body or "bundle run" in _body
        if not _has_path_a:
            _c34_fails.append(
                f"{_rel} no longer mentions Path A (endpoint access "
                "or --cmaddr)"
            )
        if not _has_path_b:
            _c34_fails.append(
                f"{_rel} no longer mentions Path B "
                "(Cerebras-assisted bundle run)"
            )
    if _c34_fails:
        for _f in _c34_fails:
            failures.append(f"C34 FAIL: {_f}")
    else:
        print(
            f"  C34 PASS: {len(_two_path_docs)} governance docs all "
            "name both hardware-validation paths (A endpoint / B "
            "Cerebras-assisted)"
        )

    # C35: emit_depth_coverage_matrix.DECLARED_DEPTHS must match the
    # cockpit HTML's num-layers-select options. Drift here lies to the
    # viewer: either the tool enumerates depths the UI doesn't offer,
    # or the UI offers depths the tool never evaluates. The honest
    # labeling depends on one source of truth; the check locks them.
    _c35_fails: list[str] = []
    _c35_tool = REPO_ROOT / "bench/tools/emit_depth_coverage_matrix.py"
    _c35_html = REPO_ROOT / "demos/gemma4-e2b-csl-sim/index.html"
    if not _c35_tool.is_file():
        _c35_fails.append(
            "emit_depth_coverage_matrix.py missing — required for C35"
        )
    if not _c35_html.is_file():
        _c35_fails.append(
            "demos/gemma4-e2b-csl-sim/index.html missing — required for C35"
        )
    if not _c35_fails:
        try:
            import importlib.util as _ilu_c35
            _spec35 = _ilu_c35.spec_from_file_location(
                "_doe_depth_tool", str(_c35_tool)
            )
            _mod35 = _ilu_c35.module_from_spec(_spec35)
            _spec35.loader.exec_module(_mod35)  # type: ignore[union-attr]
            _tool_depths = tuple(_mod35.DECLARED_DEPTHS)
        except (OSError, AttributeError, ImportError) as _e35:
            _tool_depths = None
            _c35_fails.append(
                "could not import DECLARED_DEPTHS from "
                f"emit_depth_coverage_matrix.py: {_e35}"
            )
        if _tool_depths is not None:
            _html = _c35_html.read_text(encoding="utf-8")
            # Narrow scan to the num-layers-select <select>...</select>
            # block so other unrelated <option> tags on the page cannot
            # accidentally satisfy the contract.
            _sel_start = _html.find('id="num-layers-select"')
            _sel_end = _html.find("</select>", _sel_start) if _sel_start >= 0 else -1
            if _sel_start < 0 or _sel_end < 0:
                _c35_fails.append(
                    "num-layers-select <select> block not found in "
                    "cockpit index.html"
                )
            else:
                _block = _html[_sel_start:_sel_end]
                import re as _re_c35
                _html_depths = tuple(
                    int(_m) for _m in _re_c35.findall(
                        r'value="(\d+)"', _block
                    )
                )
                if _tool_depths != _html_depths:
                    _c35_fails.append(
                        f"depth drift: tool={list(_tool_depths)} "
                        f"cockpit={list(_html_depths)} "
                        "(order and membership both matter — the cockpit "
                        "selector order is user-visible)"
                    )
    if _c35_fails:
        for _f in _c35_fails:
            failures.append(f"C35 FAIL: {_f}")
    else:
        print(
            "  C35 PASS: DECLARED_DEPTHS in emit_depth_coverage_matrix.py "
            "matches cockpit num-layers-select options (order + "
            f"membership) — {list(_tool_depths)}"
        )

    # C22: packager's INCLUDE_FILES and CLAIM_ROLE dict stay in sync.
    # Every archive path in INCLUDE_FILES must have a CLAIM_ROLE entry
    # (otherwise MANIFEST.txt shows 'UNLABELED'); every CLAIM_ROLE key
    # must appear in INCLUDE_FILES (otherwise the label is dead code).
    # Imports the packager module to read the live tuples.
    _packer_py = REPO_ROOT / "bench/tools/pack_cerebras_validation_archive.py"
    if _packer_py.is_file():
        try:
            import importlib.util as _ilu_c22
            _pspec = _ilu_c22.spec_from_file_location(
                "_doe_packer", str(_packer_py)
            )
            _pmod = _ilu_c22.module_from_spec(_pspec)
            _pspec.loader.exec_module(_pmod)  # type: ignore[union-attr]
            _archive_paths = set()
            for _entry in _pmod.INCLUDE_FILES:
                if isinstance(_entry, tuple):
                    _archive_paths.add(_entry[1])
                else:
                    _archive_paths.add(_entry)
            _role_keys = set(_pmod.CLAIM_ROLE.keys())
            _c22_fails = []
            _unlabeled = _archive_paths - _role_keys
            if _unlabeled:
                _c22_fails.append(
                    f"INCLUDE_FILES without CLAIM_ROLE entry: "
                    f"{sorted(_unlabeled)}"
                )
            _dead = _role_keys - _archive_paths
            if _dead:
                _c22_fails.append(
                    f"CLAIM_ROLE entries without INCLUDE_FILES match "
                    f"(dead code): {sorted(_dead)}"
                )
            if _c22_fails:
                for _f in _c22_fails:
                    failures.append(f"C22 FAIL: {_f}")
            else:
                print(
                    f"  C22 PASS: packager INCLUDE_FILES and CLAIM_ROLE "
                    f"in sync ({len(_archive_paths)} archive paths, "
                    f"{len(_role_keys)} claim-role entries)"
                )
        except (OSError, ImportError, AttributeError) as _e22:
            failures.append(f"C22 FAIL: cannot import packer: {_e22}")
    else:
        failures.append(
            f"C22 FAIL: packer missing at "
            f"{_packer_py.relative_to(REPO_ROOT)}"
        )

    # C21: MoE TODO receipts use artifactKind=doe_moe_<component>_todo,
    # NOT ...*_receipt. If a TODO were renamed to end in _receipt, the
    # claim-discipline gate's find_moe_receipt() would false-unlock
    # the MoE-claim gate. Lock the 6 TODOs' artifactKind shape here
    # so a rename is caught at self-check time, not at claim-leak time.
    _moe_todo_expected = {
        "bench/out/26b-moe-lane/router-todo.json":
            "doe_moe_router_todo",
        "bench/out/26b-moe-lane/topk-selection-todo.json":
            "doe_moe_topk_selection_todo",
        "bench/out/26b-moe-lane/token-dispatch-todo.json":
            "doe_moe_token_dispatch_todo",
        "bench/out/26b-moe-lane/shared-expert-todo.json":
            "doe_moe_shared_expert_todo",
        "bench/out/26b-moe-lane/output-combine-todo.json":
            "doe_moe_output_combine_todo",
        "bench/out/26b-moe-lane/per-expert-batching-todo.json":
            "doe_moe_per_expert_batching_todo",
    }
    _c21_fails = []
    for _rel, _expected in _moe_todo_expected.items():
        _p = REPO_ROOT / _rel
        if not _p.is_file():
            _c21_fails.append(f"{_rel}: missing")
            continue
        try:
            _d = json.loads(_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as _e21:
            _c21_fails.append(f"{_rel}: unreadable: {_e21}")
            continue
        _ak = _d.get("artifactKind") or ""
        if _ak != _expected:
            _c21_fails.append(
                f"{_rel}: artifactKind={_ak!r}, expected {_expected!r}"
            )
        if _ak.endswith("_receipt"):
            _c21_fails.append(
                f"{_rel}: artifactKind ends in '_receipt' — this "
                f"would false-unlock the MoE claim-discipline gate"
            )
    if _c21_fails:
        for _f in _c21_fails:
            failures.append(f"C21 FAIL: {_f}")
    else:
        print(
            "  C21 PASS: 6 MoE TODO files use _todo artifactKinds "
            "(none ends in _receipt so the MoE claim gate stays ACTIVE)"
        )

    # C20: lane-label consistency across fixtures + MoE lane-status.
    # The three lane labels express the target-ordering commitment
    # (E2B=primary_correctness_target, 31B=dense_scale_target,
    # 26B/A4B MoE=blocked_efficiency_lane) recorded in the
    # hardware-validation appendix. Regression-lock by file so a
    # rename in one place without the others is caught immediately.
    _lane_label_checks = [
        (
            "config/gemma-4-e2b-real-weight-fixture.json",
            "laneLabel",
            "primary_correctness_target",
        ),
        (
            "config/gemma-4-31b-real-weight-fixture.json",
            "laneLabel",
            "dense_scale_target",
        ),
        (
            "bench/out/26b-moe-lane/lane-status.json",
            "laneLabel",
            "blocked_efficiency_lane",
        ),
    ]
    _c20_fails = []
    for _rel, _field, _expected in _lane_label_checks:
        _p = REPO_ROOT / _rel
        if not _p.is_file():
            _c20_fails.append(f"{_rel}: missing")
            continue
        try:
            _d = json.loads(_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as _e20:
            _c20_fails.append(f"{_rel}: unreadable JSON: {_e20}")
            continue
        _actual = _d.get(_field)
        if _actual != _expected:
            _c20_fails.append(
                f"{_rel}: {_field}={_actual!r}, expected {_expected!r}"
            )
    if _c20_fails:
        for _f in _c20_fails:
            failures.append(f"C20 FAIL: {_f}")
    else:
        print(
            "  C20 PASS: lane labels consistent across E2B fixture "
            "(primary_correctness_target), 31B fixture "
            "(dense_scale_target), 26B/A4B lane-status "
            "(blocked_efficiency_lane)"
        )

    # C19: evidence-bundle summary shape. Reads
    # bench/out/cerebras-evidence-bundle/summary.json and asserts the
    # shape every downstream consumer depends on: verdict in
    # {passed, failed}, totalSteps == len(steps), each step carries
    # (step, status, returnCode, elapsedMs). Regression-locks the
    # bundle runner's output so the jq summary script, the verifier,
    # and the packager's inclusion of summary.json all continue to
    # see a stable contract.
    _bundle_summary = REPO_ROOT / "bench/out/cerebras-evidence-bundle/summary.json"
    if _bundle_summary.is_file():
        try:
            _bs = json.loads(_bundle_summary.read_text(encoding="utf-8"))
            _c19_fails = []
            if _bs.get("artifactKind") != "doe_cerebras_evidence_bundle_summary":
                _c19_fails.append(
                    f"artifactKind={_bs.get('artifactKind')!r}, "
                    "expected 'doe_cerebras_evidence_bundle_summary'"
                )
            if _bs.get("verdict") not in ("passed", "failed"):
                _c19_fails.append(
                    f"verdict={_bs.get('verdict')!r}, "
                    "expected one of passed/failed"
                )
            _steps = _bs.get("steps") or []
            if _bs.get("totalSteps") != len(_steps):
                _c19_fails.append(
                    f"totalSteps={_bs.get('totalSteps')} but "
                    f"len(steps)={len(_steps)}"
                )
            _required_step_keys = {"step", "status", "returnCode", "elapsedMs"}
            _any_failed_step = False
            for _i, _step in enumerate(_steps):
                if not isinstance(_step, dict):
                    _c19_fails.append(f"steps[{_i}] not a dict")
                    continue
                _missing = _required_step_keys - set(_step.keys())
                if _missing:
                    _c19_fails.append(
                        f"steps[{_i}] missing keys: {sorted(_missing)}"
                    )
                # Explicit None rejection for elapsedMs (user #14): a
                # key-present-but-null slipped past the set-difference
                # check. Require a numeric value.
                if not isinstance(_step.get("elapsedMs"), (int, float)):
                    _c19_fails.append(
                        f"steps[{_i}] elapsedMs="
                        f"{_step.get('elapsedMs')!r} (must be numeric)"
                    )
                if _step.get("status") == "failed":
                    _any_failed_step = True
            # verdict/steps consistency (user #13): verdict=passed
            # with any failed step inside is a category-1 lie — the
            # summary claims success while individual steps disagree.
            if _bs.get("verdict") == "passed" and _any_failed_step:
                _c19_fails.append(
                    "verdict='passed' but at least one step has "
                    "status='failed' — inconsistent summary"
                )
            if _c19_fails:
                for _f in _c19_fails:
                    failures.append(f"C19 FAIL: {_f}")
            else:
                print(
                    "  C19 PASS: evidence-bundle summary has "
                    f"{len(_steps)} steps with stable shape"
                )
        except (OSError, json.JSONDecodeError) as _e19:
            failures.append(f"C19 FAIL: summary unreadable: {_e19}")
    else:
        # Fresh clone / never-run state: summary hasn't been produced
        # yet. Skip cleanly rather than forcing the self-check to
        # invoke the 15s+ bundle runner. C16 covers pack/verify; C19
        # only validates the shape when a summary exists.
        print(
            "  C19 SKIP: evidence-bundle summary not yet produced "
            "(run bench/tools/run_cerebras_evidence_bundle.py to "
            "generate)"
        )

    # C18: demo HTML structural sanity. Confirms the three Gemma-4-
    # facing demo pages exist with balanced <main> tags, at least one
    # <script> reference, and cross-link anchors to the sibling two.
    # Catches accidental deletion, major HTML breakage, or nav
    # regression. Purely string-level — no HTML parser dependency.
    _demo_checks = [
        (
            "demos/doe-status-dashboard/index.html",
            ["../gemma4-e2b-csl-sim/", "../doe-sdk-gui-viewer/"],
        ),
        (
            "demos/gemma4-e2b-csl-sim/index.html",
            ["../doe-status-dashboard/", "../doe-sdk-gui-viewer/"],
        ),
        (
            "demos/doe-sdk-gui-viewer/index.html",
            ["../doe-status-dashboard/", "../gemma4-e2b-csl-sim/"],
        ),
    ]
    _c18_fails = []
    for _rel, _expected_links in _demo_checks:
        _p = REPO_ROOT / _rel
        if not _p.is_file():
            _c18_fails.append(f"{_rel}: missing")
            continue
        _html = _p.read_text(encoding="utf-8", errors="replace")
        if _html.count("<main") < 1 or _html.count("</main>") < 1:
            _c18_fails.append(f"{_rel}: missing balanced <main> tags")
        if "<script" not in _html:
            _c18_fails.append(f"{_rel}: missing <script> reference")
        for _link in _expected_links:
            if _link not in _html:
                _c18_fails.append(f"{_rel}: missing cross-link to {_link}")
        if _rel == "demos/doe-sdk-gui-viewer/index.html":
            for _needle in [
                "sdk-command-copy",
                "bundle-runner-command-copy",
                "archive-pack-command-copy",
                "archive-verify-command-copy",
                "color-list",
                "fabric-grid",
                "pe-coordinate-input",
                "timeline-controls",
                "timeline-rows",
                "data-copy-for=\"sdk-command\"",
                "data-copy-for=\"archive-verify-command\"",
            ]:
                if _needle not in _html:
                    _c18_fails.append(
                        f"{_rel}: missing command control {_needle}"
                    )
    if _c18_fails:
        for _f in _c18_fails:
            failures.append(f"C18 FAIL: {_f}")
    else:
        print(
            "  C18 PASS: 3 demo HTML pages have balanced <main>, "
            "<script> reference, sibling cross-links, and SDK-GUI "
            "fabric/timeline/command controls"
        )

    # C17: SDK-GUI viewer server routes regression lock. Imports
    # DemoHandler from demos/gemma4-e2b-csl-sim/server.py and calls
    # its inspection methods directly (passing None as self — the
    # methods don't use self). Positive path: a known compile dir +
    # known trace path return ok=True with expected keys. Negative:
    # traversal + missing both return ok=False with clear errors.
    # Without this, the /api routes can silently break and the
    # viewer goes dark without self-check noticing.
    _server_py = REPO_ROOT / "demos/gemma4-e2b-csl-sim/server.py"
    if _server_py.is_file():
        try:
            import importlib.util as _ilu_c17
            _spec = _ilu_c17.spec_from_file_location(
                "_doe_demo_server", str(_server_py)
            )
            _mod = _ilu_c17.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            _inspect_dir = _mod.DemoHandler.inspect_artifact_dir
            _inspect_trace = _mod.DemoHandler.inspect_trace_host_io
            _inspect_bundle = _mod.DemoHandler.inspect_bundle_summary
            _inspect_commands = _mod.DemoHandler.inspect_evidence_commands

            _positive_dir = _inspect_dir(
                None, "bench/out/scratch/gemma4-e2b-csl-sim/compile-L1"
            )
            _positive_trace = _inspect_trace(
                None, "bench/out/scratch/gemma4-e2b-csl-sim/csl-L1-live-trace.json"
            )
            _positive_commands = _inspect_commands(None)
            _neg_traversal = _inspect_dir(None, "../../etc")
            _neg_absolute = _inspect_trace(None, "/tmp")
            _neg_missing = _inspect_trace(None, "bench/out/nonexistent-trace.json")

            # Bundle-summary route: shape-check only; the absent path
            # case is exercised elsewhere. Here we just assert that
            # when a summary exists it's reported with verdict and
            # step counts, and when absent the route returns
            # {ok: false, hint} (fail-closed).
            _positive_bundle = _inspect_bundle(None)
            _c17_problems = []
            if not (_positive_dir.get("ok") and _positive_dir.get("numSdkArtifacts", 0) > 0):
                _c17_problems.append(
                    f"positive artifact-dir path did not return SDK artifacts: "
                    f"{_positive_dir}"
                )
            if not (_positive_trace.get("ok") and _positive_trace.get("hostIoLayout")):
                _c17_problems.append(
                    f"positive trace path did not return hostIoLayout"
                )
            _commands = _positive_commands.get("commands") or {}
            _copyable = _positive_commands.get("copyable") or {}
            for _cmd_key, _substring in [
                ("bundleRunner", "run_cerebras_evidence_bundle.py"),
                ("archivePack", "pack_cerebras_validation_archive.py"),
                ("archiveVerify", "verify_cerebras_validation_archive.py"),
            ]:
                if _substring not in (_commands.get(_cmd_key) or ""):
                    _c17_problems.append(
                        f"evidence-commands missing {_substring} "
                        f"in {_cmd_key}: {_positive_commands}"
                    )
            if _copyable.get("bundleRunner") is not True:
                _c17_problems.append(
                    "evidence-commands bundleRunner must be copyable"
                )
            if _copyable.get("archivePack") is not True:
                _c17_problems.append(
                    "evidence-commands archivePack must be copyable"
                )
            # bundle-summary: either ok=true with verdict+totalSteps,
            # OR ok=false with a hint string — both are valid fail-
            # closed shapes; silent bad shape (e.g. ok=true but no
            # verdict) is the regression we lock against.
            if _positive_bundle.get("ok") is True:
                if _positive_bundle.get("verdict") not in ("passed", "failed"):
                    _c17_problems.append(
                        f"bundle-summary ok=true but "
                        f"verdict={_positive_bundle.get('verdict')!r}"
                    )
                if not isinstance(_positive_bundle.get("totalSteps"), int):
                    _c17_problems.append(
                        f"bundle-summary ok=true but totalSteps not int"
                    )
            else:
                # ok=false must carry a hint string so the cockpit
                # can surface it honestly rather than show a spinner.
                if not _positive_bundle.get("hint"):
                    _c17_problems.append(
                        f"bundle-summary ok=false but no hint — "
                        f"cockpit has nothing to tell the reviewer"
                    )
            for tag, result in [
                ("traversal", _neg_traversal),
                ("absolute", _neg_absolute),
                ("missing", _neg_missing),
            ]:
                if result.get("ok") is not False:
                    _c17_problems.append(
                        f"negative {tag} path unexpectedly returned ok=True: {result}"
                    )

            if _c17_problems:
                for p in _c17_problems:
                    failures.append(f"C17 FAIL: {p}")
            else:
                print(
                    "  C17 PASS: SDK-GUI viewer /api routes respond "
                    "correctly on positive + negative paths, including "
                    "evidence command metadata"
                )
        except (OSError, ImportError, AttributeError) as _e17:
            failures.append(f"C17 FAIL: cannot import server inspection functions: {_e17}")
    else:
        failures.append(
            f"C17 FAIL: server.py missing at {_server_py.relative_to(REPO_ROOT)}"
        )

    # C16: Cerebras evidence bundle pack + verify round-trip. Packs a
    # fresh archive to a scratch location, runs the verifier against
    # it, asserts both exit 0. Catches: missing governance doc (any
    # of CLAIM_SCOPE/README/CEREBRAS_ASK/LOCAL_INSPECTION) dropping
    # out of INCLUDE_FILES, claim-discipline drift inside packed
    # archive docs, manifest sha integrity regression, BUNDLE_META
    # schema drift. This is the end-to-end lock on the whole
    # Cerebras-facing bundle pipeline.
    try:
        import subprocess as _subprocess_c16
        import tempfile as _tempfile_c16
        with _tempfile_c16.TemporaryDirectory() as _scratch:
            _scratch_archive = (
                Path(_scratch) / "doe-cerebras-evidence-selfcheck.tar.gz"
            )
            _c16_pack = _subprocess_c16.run(
                ["python3", "bench/tools/pack_cerebras_validation_archive.py",
                 "--out", str(_scratch_archive)],
                cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=60, check=False,
            )
            if _c16_pack.returncode != 0:
                failures.append(
                    f"C16 FAIL: pack_cerebras_validation_archive.py "
                    f"returned {_c16_pack.returncode}: "
                    f"{_c16_pack.stderr[-200:]}"
                )
            elif not _scratch_archive.is_file():
                failures.append(
                    "C16 FAIL: packer reported success but archive "
                    "was not written"
                )
            else:
                _c16_verify = _subprocess_c16.run(
                    ["python3",
                     "bench/tools/verify_cerebras_validation_archive.py",
                     "--archive", str(_scratch_archive)],
                    cwd=REPO_ROOT, capture_output=True, text=True,
                    timeout=60, check=False,
                )
                if _c16_verify.returncode != 0:
                    failures.append(
                        f"C16 FAIL: verifier returned "
                        f"{_c16_verify.returncode} on freshly packed "
                        f"archive: {_c16_verify.stdout[-300:]}"
                    )
                else:
                    print(
                        "  C16 PASS: Cerebras evidence bundle "
                        "pack+verify round-trip clean"
                    )
    except (OSError, subprocess.TimeoutExpired) as _e16:
        failures.append(
            f"C16 FAIL: bundle round-trip error: {_e16}"
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
