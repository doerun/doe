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
    audit_fails = []
    for _csl in REPO_ROOT.rglob("*.csl"):
        if _csl.name.endswith(production_probe_suffixes):
            continue
        try:
            _text = _csl.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "math.sqrt(" in _text and "fn sqrt_nr(" not in _text:
            audit_fails.append(str(_csl.relative_to(REPO_ROOT)))
    if not audit_fails:
        print(
            "  C12 PASS: no CSL production kernel uses raw math.sqrt "
            "outside the sqrt_nr NR-refined wrapper "
            f"(scanned {sum(1 for _ in REPO_ROOT.rglob('*.csl'))} "
            "CSL files)"
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

    # C15: parity harness skeleton exits 0 today with
    # verdict=blocked_weights_absent AND bundleIdentityMatched=true.
    # This catches: (a) harness regression, (b) fixture drift that
    # would flip bundle identity to failed, (c) accidental promotion
    # of the verdict before real weights materialize.
            import subprocess as _subprocess_c15
            _c15_out = REPO_ROOT / "bench/out/gemma-4-e2b-real-weight-parity-L1.json"
            _c15_out.parent.mkdir(parents=True, exist_ok=True)
            _c15 = _subprocess_c15.run(
                ["python3", "bench/tools/run_e2b_real_weight_l1_parity.py",
                 "--out-json", str(_c15_out.relative_to(REPO_ROOT))],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
            )
            if _c15.returncode != 0:
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
                if _verdict == "blocked_weights_absent" and _bundle_ok is True:
                    print(
                        "  C15 PASS: parity harness skeleton exits "
                        "blocked_weights_absent with bundleIdentityMatched=true"
                    )
                else:
                    failures.append(
                        f"C15 FAIL: parity harness verdict={_verdict!r} "
                        f"bundleIdentityMatched={_bundle_ok!r}; expected "
                        "blocked_weights_absent + bundleIdentityMatched=true "
                        "(did real weights land without updating the fixture, "
                        "or did the harness regress?)"
                    )
        except (OSError, ValueError, json.JSONDecodeError) as _e:
            failures.append(f"C14/C15 FAIL: fixture evaluation error: {_e}")
    else:
        failures.append(
            f"C14 FAIL: fixture missing at {_fixture_path.relative_to(REPO_ROOT)}"
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
    if _c18_fails:
        for _f in _c18_fails:
            failures.append(f"C18 FAIL: {_f}")
    else:
        print(
            "  C18 PASS: 3 demo HTML pages have balanced <main>, "
            "<script> reference, and sibling cross-links"
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

            _positive_dir = _inspect_dir(
                None, "bench/out/scratch/gemma4-e2b-csl-sim/compile-L1"
            )
            _positive_trace = _inspect_trace(
                None, "bench/out/scratch/gemma4-e2b-csl-sim/csl-L1-live-trace.json"
            )
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
                    "correctly on positive + negative paths"
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
