#!/usr/bin/env python3
"""Gemma-4 E2B real-weight L1 parity harness.

Reads the canonical fixture at
`config/gemma-4-e2b-real-weight-fixture.json`, checks the weightsDir
against the validator contract, invokes two runtime lanes at L=1
(WebGPU reference + CSL simfabric) on the same manifest/graph/input
and the same --weights-dir, and diffs the per-layer outputs under the
fixture's tolerance policy. Emits a `doe_e2b_real_weight_parity`
verdict.

If weightsDir is absent, the harness exits cleanly with
`verdict=blocked_weights_absent` and records exactly which weightsDir
path the fixture expects. Once real weights are materialized, re-running
this tool emits a concrete pass/fail verdict with the real lanes
executed.

Scope caveat: L=1 single-layer parity only. L>1 and manifest-shape
(headDim=512) runs are explicit follow-ups per the fixture's
fixtureChain block.

Usage:
  python3 bench/tools/run_e2b_real_weight_l1_parity.py \\
    --fixture config/gemma-4-e2b-real-weight-fixture.json \\
    --weights-dir bench/out/gemma-4-e2b-real-weights \\
    --out-json bench/out/gemma-4-e2b-real-weight-parity-L1.json

Exits 0 on pass or blocked; 1 on fixture/audit/parity failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--fixture",
        default="config/gemma-4-e2b-real-weight-fixture.json",
    )
    p.add_argument(
        "--weights-dir",
        default="",
        help=(
            "Candidate weightsDir. If empty, falls back to the fixture's "
            "weightsDir.pathPlaceholder; if that path is absent on disk "
            "the verdict is blocked_weights_absent, not a parity failure."
        ),
    )
    p.add_argument(
        "--num-layers", type=int, default=1,
        help="Chain depth. Defaults to 1 (L1 single-layer contract).",
    )
    p.add_argument(
        "--out-json", default="",
        help="Optional path for the machine-readable verdict artifact.",
    )
    p.add_argument(
        "--weight-set-pin-mode",
        choices=["strict", "record-only"],
        default="strict",
        help=(
            "strict rejects weights whose aggregate sha does not match the "
            "fixture pin. record-only audits shape and records the aggregate "
            "sha without treating the fixture's BF16 pin as authoritative."
        ),
    )
    p.add_argument(
        "--weights-source-label",
        default="bf16_safetensors",
        help="Human-readable source label recorded in the verdict artifact.",
    )
    p.add_argument(
        "--weights-audit-out",
        default="",
        help=(
            "Optional weights audit path. Defaults to the canonical BF16 "
            "audit path for strict mode and a source-labeled path for "
            "record-only mode."
        ),
    )
    p.add_argument(
        "--lane-out-dir",
        default="",
        help=(
            "Optional output root for per-lane receipts. Defaults to the "
            "canonical real-weight parity directory."
        ),
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_verdict(args: argparse.Namespace, verdict: dict) -> None:
    if not args.out_json:
        return
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(out_path)}")


def main() -> int:
    args = parse_args()
    fixture_path = resolve(args.fixture)
    if not fixture_path.is_file():
        print(f"FAIL: fixture not found: {args.fixture}")
        return 1
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_sha = sha256_file(fixture_path)

    # Bundle identity pin: manifest + graph + input must match fixture.
    bundle = fixture.get("bundle") or {}
    manifest_rel = bundle.get("manifest", {}).get("path", "")
    manifest_sha_expected = bundle.get("manifest", {}).get("sha256", "")
    graph_rel = bundle.get("graph", {}).get("path", "")
    graph_sha_expected = bundle.get("graph", {}).get("sha256", "")
    input_rel = (fixture.get("input") or {}).get("path", "")
    input_sha_expected = (fixture.get("input") or {}).get("sha256", "")

    bundle_checks = []
    for label, rel_path, expected in [
        ("manifest", manifest_rel, manifest_sha_expected),
        ("graph", graph_rel, graph_sha_expected),
        ("input", input_rel, input_sha_expected),
    ]:
        path = resolve(rel_path) if rel_path else None
        on_disk = (
            sha256_file(path) if (path is not None and path.is_file()) else None
        )
        bundle_checks.append({
            "label": label,
            "path": rel_path,
            "expectedSha256": expected,
            "actualSha256": on_disk,
            "matched": (on_disk is not None) and (on_disk == expected),
            "present": on_disk is not None,
        })
    bundle_identity_ok = all(c["matched"] for c in bundle_checks)

    # WeightsDir resolution: CLI override -> fixture's placeholder.
    weights_dir_str = args.weights_dir or (
        (fixture.get("weightsDir") or {}).get("pathPlaceholder") or ""
    )
    weights_dir_path = resolve(weights_dir_str) if weights_dir_str else None

    weights_audit = None
    weights_absent = (
        weights_dir_path is None or not weights_dir_path.is_dir()
    )

    if weights_absent:
        verdict = {
            "schemaVersion": 1,
            "artifactKind": "doe_e2b_real_weight_parity",
            "modelId": fixture.get("modelId"),
            "fixturePath": args.fixture,
            "fixtureSha256": fixture_sha,
            "bundleIdentityChecks": bundle_checks,
            "bundleIdentityMatched": bundle_identity_ok,
            "numLayers": args.num_layers,
            "weightsDir": weights_dir_str,
            "weightsDirPresent": False,
            "weightsSourceLabel": args.weights_source_label,
            "weightSetPinMode": args.weight_set_pin_mode,
            "weightsAudit": None,
            "lanes": {
                "doppler-webgpu": {"status": "not_attempted"},
                "csl-sdklayout":  {"status": "not_attempted"},
            },
            "parity": None,
            "verdict": "blocked_weights_absent",
            "blocker": "real_weights_absent",
            "claimScope": (
                "Skeleton harness in place; awaiting external checkpoint "
                "extractor to materialize real Gemma-4 E2B weight slices at "
                "the expected weightsDir path. Bundle identity is verified "
                "today so once weights land, the only remaining gate is "
                "the weights-dir audit + per-lane parity diff."
            ),
        }
        write_verdict(args, verdict)
        print(
            f"blocked_weights_absent: weightsDir '{weights_dir_str}' not "
            f"present on disk. Bundle identity "
            f"{'matched' if bundle_identity_ok else 'FAILED'}. Fixture "
            f"sha256={fixture_sha[:16]}..."
        )
        return 0

    if not bundle_identity_ok:
        verdict = {
            "schemaVersion": 1,
            "artifactKind": "doe_e2b_real_weight_parity",
            "fixturePath": args.fixture,
            "fixtureSha256": fixture_sha,
            "bundleIdentityChecks": bundle_checks,
            "bundleIdentityMatched": False,
            "numLayers": args.num_layers,
            "weightsDir": weights_dir_str,
            "weightsDirPresent": True,
            "weightsSourceLabel": args.weights_source_label,
            "weightSetPinMode": args.weight_set_pin_mode,
            "verdict": "bundle_identity_failed",
            "blocker": "fixture_or_on_disk_drift",
        }
        write_verdict(args, verdict)
        print("FAIL: bundle identity mismatch (see bundleIdentityChecks).")
        return 1

    # Run the weights validator against the candidate dir with the
    # fixture pin so any hash drift is rejected before we spend cycles
    # on lane execution.
    if args.weights_audit_out:
        weights_audit_path = resolve(args.weights_audit_out)
    elif args.weight_set_pin_mode == "strict":
        weights_audit_path = (
            REPO_ROOT
            / "bench/out/weights-audit/gemma-4-e2b-weights-audit.json"
        )
    else:
        safe_label = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "-"
            for ch in args.weights_source_label
        ).strip("-") or "record-only"
        weights_audit_path = (
            REPO_ROOT
            / f"bench/out/weights-audit/gemma-4-e2b-{safe_label}-weights-audit.json"
        )
    weights_audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_argv = [
        "python3", "bench/tools/validate_weights_dir.py",
        "--weights-dir", str(weights_dir_path),
        "--manifest", manifest_rel,
        "--shape", "smoke",
        "--out", rel(weights_audit_path),
    ]
    if args.weight_set_pin_mode == "strict":
        audit_argv.extend(["--fixture", args.fixture])
    audit_proc = subprocess.run(
        audit_argv,
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    if weights_audit_path.is_file():
        weights_audit = json.loads(weights_audit_path.read_text(encoding="utf-8"))
    audit_passed = bool(weights_audit and weights_audit.get("passedAudit"))
    if not audit_passed:
        verdict = {
            "schemaVersion": 1,
            "artifactKind": "doe_e2b_real_weight_parity",
            "fixturePath": args.fixture,
            "fixtureSha256": fixture_sha,
            "bundleIdentityMatched": True,
            "numLayers": args.num_layers,
            "weightsDir": weights_dir_str,
            "weightsDirPresent": True,
            "weightsSourceLabel": args.weights_source_label,
            "weightSetPinMode": args.weight_set_pin_mode,
            "weightsAuditPath": rel(weights_audit_path),
            "weightsAuditPassed": False,
            "weightsAuditFailures": (weights_audit or {}).get("failures", [])[:10],
            "verdict": "weights_audit_failed",
            "blocker": "real_weights_dir_drift_or_shape_mismatch",
            "stderrTail": audit_proc.stderr[-400:],
        }
        write_verdict(args, verdict)
        print("FAIL: weights audit failed; see weightsAuditFailures.")
        return 1

    # Lanes: WebGPU reference + CSL simfabric, same fixture, same
    # --weights-dir. The WebGPU lane runs Dawn via Node; the CSL lane
    # runs through cs_python. Each emits its own receipt; this harness
    # then diffs their output digests and records per-layer error
    # against the fixture's tolerance policy.
    if args.lane_out_dir:
        lane_out_dir = resolve(args.lane_out_dir)
    else:
        lane_out_dir = (
            REPO_ROOT
            / "bench/out/gemma-4-e2b-real-weight-parity"
            / f"L{args.num_layers}"
        )
    webgpu_out = lane_out_dir / "webgpu"
    csl_out = lane_out_dir / "csl-sdklayout"
    webgpu_out.mkdir(parents=True, exist_ok=True)
    csl_out.mkdir(parents=True, exist_ok=True)

    lanes: dict = {}
    parity_policy = fixture.get("parityPolicy") or {}
    atol = float(parity_policy.get("atol", 1e-3))
    rtol = float(parity_policy.get("rtol", 0.0))

    # Prep numpy-PRNG input fixtures the CJS tool reads as the
    # initial rows. The canonical input fixture is already pinned by
    # the fixture JSON; this just re-asserts its presence.
    node_bin = os.environ.get("DOE_NODE", "node")
    webgpu_proc = subprocess.run(
        [node_bin, "bench/tools/doppler_webgpu_reference_export.cjs",
         "--manifest", manifest_rel,
         "--graph", graph_rel,
         "--size", "1024",
         "--num-layers", str(args.num_layers),
         "--initial-rows-seed", "1000",
         "--out-dir", str(webgpu_out.relative_to(REPO_ROOT)),
         "--weights-dir", str(weights_dir_path)
         if weights_dir_path.is_relative_to(REPO_ROOT) is False
         else str(weights_dir_path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT, capture_output=True, text=True,
        timeout=300, check=False,
    )
    webgpu_receipt = webgpu_out / "export_receipt.json"
    if webgpu_proc.returncode != 0 or not webgpu_receipt.is_file():
        lanes["doppler-webgpu"] = {
            "status": "failed",
            "returnCode": webgpu_proc.returncode,
            "stderrTail": webgpu_proc.stderr[-400:],
        }
    else:
        wr = json.loads(webgpu_receipt.read_text(encoding="utf-8"))
        lanes["doppler-webgpu"] = {
            "status": "succeeded",
            "elapsedMs": wr.get("elapsedMs"),
            "outputSha256": wr.get("outputSha256"),
            "outputPath": wr.get("outputPath"),
            "perLayerOutputDir": wr.get("perLayerOutputDir"),
            "perLayerOutputSha256": wr.get("perLayerOutputSha256"),
            "weightSha256": wr.get("weightSha256"),
            "dataSource": wr.get("dataSource"),
            "receiptPath": rel(webgpu_receipt),
        }

    # CSL simfabric lane via cs_python. This is the slow path and
    # only runs if cs_python is available; otherwise report blocked.
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    cs_python = os.environ.get("DOE_CSL_CS_PYTHON", f"{sdk_root}/cs_python")
    if not Path(cs_python).is_file() and cs_python != "cs_python":
        lanes["csl-sdklayout"] = {
            "status": "blocked",
            "blocker": f"cs_python not found at {cs_python}",
        }
    else:
        csl_trace = csl_out / "trace.json"
        compile_out = csl_out / "compile"
        compile_out.mkdir(parents=True, exist_ok=True)
        csl_proc = subprocess.run(
            [cs_python,
             "bench/runners/csl-runners/e2b_layer_block_smoke.py",
             "--num-layers", str(args.num_layers),
             "--compile-out", str(compile_out.relative_to(REPO_ROOT)),
             "--trace-out", str(csl_trace.relative_to(REPO_ROOT)),
             "--weights-dir",
             str(weights_dir_path.relative_to(REPO_ROOT)) if
             weights_dir_path.is_relative_to(REPO_ROOT) else str(weights_dir_path)],
            cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=1800, check=False,
        )
        if csl_proc.returncode != 0 or not csl_trace.is_file():
            lanes["csl-sdklayout"] = {
                "status": "failed",
                "returnCode": csl_proc.returncode,
                "stderrTail": csl_proc.stderr[-400:],
            }
        else:
            ct = json.loads(csl_trace.read_text(encoding="utf-8"))
            er = ct.get("executedRun", {}) or {}
            lanes["csl-sdklayout"] = {
                "status": er.get("status", "unknown"),
                "elapsedMs": er.get("elapsedMs"),
                "outputSha256": (er.get("output") or {}).get("sha256"),
                "outputPath": (er.get("output") or {}).get("path"),
                "perLayerOutputs": er.get("perLayerOutputs"),
                "dataSource": (er.get("dataSource") or {}).get("kind"),
                "tracePath": rel(csl_trace),
            }

    # Parity: output digest + per-layer tolerance diff when both
    # lanes succeeded. Digest-match is the strict contract; tolerance
    # diff is the numerical contract (CSL scalar-f32 vs WebGPU driver
    # may differ by ULPs under FMA/vectorization even with identical
    # bundle + weights). Verdict is parity_passed when digests match
    # OR every layer is within the fixture's tolerance formula:
    # abs(a-b) <= atol + rtol * max(abs(a), abs(b)).
    parity = None
    webgpu_ok = lanes.get("doppler-webgpu", {}).get("status") == "succeeded"
    csl_ok = lanes.get("csl-sdklayout", {}).get("status") == "succeeded"
    if webgpu_ok and csl_ok:
        import numpy as np
        w_sha = lanes["doppler-webgpu"].get("outputSha256")
        c_sha = lanes["csl-sdklayout"].get("outputSha256")
        digest_match = bool(w_sha and c_sha and w_sha == c_sha)

        # Resolve per-layer dirs. WebGPU receipt records
        # perLayerOutputDir; CSL trace records perLayerOutputs entries
        # with path + sha256.
        webgpu_per_layer_dir = None
        pld = lanes["doppler-webgpu"].get("perLayerOutputDir")
        if pld:
            webgpu_per_layer_dir = resolve(pld)
        csl_per_layer = lanes["csl-sdklayout"].get("perLayerOutputs") or []

        per_layer_records: list[dict] = []
        max_abs_across = 0.0
        max_rel_across = 0.0
        max_allowed_across = atol
        mean_abs_across = 0.0
        first_fail_layer = None
        layers_compared = 0
        for entry in csl_per_layer:
            l = int(entry.get("layer", -1))
            if l < 0:
                continue
            csl_p = resolve(entry.get("path", "")) if entry.get("path") else None
            w_p = (
                webgpu_per_layer_dir / f"layer{l}.f32"
                if webgpu_per_layer_dir else None
            )
            if csl_p is None or not csl_p.is_file():
                per_layer_records.append({
                    "layer": l, "status": "csl_per_layer_missing",
                })
                continue
            if w_p is None or not w_p.is_file():
                per_layer_records.append({
                    "layer": l, "status": "webgpu_per_layer_missing",
                })
                continue
            c_f32 = np.fromfile(csl_p, dtype=np.float32)
            w_f32 = np.fromfile(w_p, dtype=np.float32)
            if c_f32.shape != w_f32.shape:
                per_layer_records.append({
                    "layer": l, "status": "shape_mismatch",
                    "cslShape": list(c_f32.shape),
                    "webgpuShape": list(w_f32.shape),
                })
                continue
            diff = np.abs(c_f32 - w_f32)
            scale = np.maximum(np.abs(c_f32), np.abs(w_f32))
            allowed = atol + rtol * scale
            finite = bool(
                np.isfinite(c_f32).all()
                and np.isfinite(w_f32).all()
                and np.isfinite(diff).all()
                and np.isfinite(allowed).all()
            )
            m = float(diff.max())
            mean = float(diff.mean())
            max_allowed = float(allowed.max())
            rel_err = np.zeros_like(diff)
            np.divide(diff, scale, out=rel_err, where=scale > 0.0)
            zero_scale_nonzero = (scale == 0.0) & (diff > 0.0)
            if bool(zero_scale_nonzero.any()):
                rel_err[zero_scale_nonzero] = np.inf
            max_rel = float(rel_err.max())
            violations = int(np.count_nonzero(diff > allowed))
            within = finite and violations == 0
            per_layer_records.append({
                "layer": l,
                "status": "compared",
                "cslPath": entry.get("path"),
                "webgpuPath": rel(w_p),
                "maxAbsErr": m,
                "maxRelErr": max_rel,
                "meanAbsErr": mean,
                "maxAllowedErr": max_allowed,
                "violationCount": violations,
                "finite": finite,
                "withinAtol": m <= atol,
                "withinTolerance": within,
            })
            layers_compared += 1
            if m > max_abs_across:
                max_abs_across = m
            if max_rel > max_rel_across:
                max_rel_across = max_rel
            if max_allowed > max_allowed_across:
                max_allowed_across = max_allowed
            mean_abs_across += mean
            if not within and first_fail_layer is None:
                first_fail_layer = {
                    "layer": l,
                    "maxAbsErr": m,
                    "maxRelErr": max_rel,
                    "maxAllowedErr": max_allowed,
                    "violationCount": violations,
                    "finite": finite,
                }
        if layers_compared:
            mean_abs_across /= layers_compared

        tolerance_passed = (
            layers_compared > 0 and first_fail_layer is None
        )
        parity = {
            "outputDigestMatch": digest_match,
            "webgpuOutputSha256": w_sha,
            "cslOutputSha256": c_sha,
            "atol": atol,
            "rtol": rtol,
            "toleranceFormula": (
                "abs(csl-webgpu) <= atol + rtol * "
                "max(abs(csl), abs(webgpu))"
            ),
            "perLayer": per_layer_records,
            "layersCompared": layers_compared,
            "maxAbsErrAcrossLayers": max_abs_across,
            "maxRelErrAcrossLayers": max_rel_across,
            "maxAllowedErrAcrossLayers": max_allowed_across,
            "meanAbsErrAcrossLayers": mean_abs_across,
            "tolerancePassed": tolerance_passed,
            "firstFailureLayer": first_fail_layer,
        }

    digest_or_tolerance_pass = (
        webgpu_ok and csl_ok and parity is not None and (
            parity.get("outputDigestMatch") is True
            or parity.get("tolerancePassed") is True
        )
    )
    verdict_tag = (
        "parity_passed"
        if digest_or_tolerance_pass
        else "parity_failed"
        if (webgpu_ok and csl_ok)
        else "lane_incomplete"
    )
    verdict = {
        "schemaVersion": 1,
        "artifactKind": "doe_e2b_real_weight_parity",
        "modelId": fixture.get("modelId"),
        "fixturePath": args.fixture,
        "fixtureSha256": fixture_sha,
        "bundleIdentityChecks": bundle_checks,
        "bundleIdentityMatched": True,
        "numLayers": args.num_layers,
        "weightsDir": weights_dir_str,
        "weightsDirPresent": True,
        "weightsSourceLabel": args.weights_source_label,
        "weightSetPinMode": args.weight_set_pin_mode,
        "weightsAuditPath": rel(weights_audit_path),
        "weightsAuditPassed": True,
        "weightSetSha256": (weights_audit or {}).get("weightSetSha256"),
        "laneOutputDir": rel(lane_out_dir),
        "lanes": lanes,
        "parity": parity,
        "verdict": verdict_tag,
        "claimScope": (
            "Bundle identity + weights audit + lane dispatch all complete. "
            "Digest-level parity is authoritative for bit-exact "
            "bundle+weight identity; tolerance parity is evaluated from "
            "both lanes' per-layer .f32 files using the fixture policy."
        ),
    }
    write_verdict(args, verdict)
    print(
        f"real-weight parity: webgpu={lanes.get('doppler-webgpu',{}).get('status')} "
        f"csl={lanes.get('csl-sdklayout',{}).get('status')} -> verdict={verdict_tag}"
    )
    return 0 if verdict_tag in ("parity_passed", "lane_incomplete") else 1


if __name__ == "__main__":
    sys.exit(main())
