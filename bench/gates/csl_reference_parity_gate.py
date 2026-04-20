#!/usr/bin/env python3
"""Validate CSL-vs-reference parity receipts for Gemma/Doppler demos."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--schema",
        default="config/doe-csl-reference-parity.schema.json",
    )
    parser.add_argument("--require-trace-success", action="store_true")
    parser.add_argument("--require-output-parity", action="store_true")
    parser.add_argument(
        "--require-tolerance-parity",
        action="store_true",
        help="Compare referenceRun.output and cslRun.output element-"
             "wise with atol from comparison.atol instead of sha256 "
             "equality. Needed when the reference producer is non-bit-"
             "exact to scalar f32 (e.g. Doppler WebGPU: driver FMA, "
             "vectorized reductions, platform sqrt round differently). "
             "Mutually exclusive with --require-output-parity.",
    )
    parser.add_argument("--require-promotion-ready", action="store_true")
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_path_hash(
    label: str,
    path_text: str,
    expected: str,
    failures: list[str],
) -> None:
    path = resolve(path_text)
    if not path.is_file():
        failures.append(f"{label}.path missing: {path_text}")
        return
    actual = sha256_file(path)
    if actual != expected:
        failures.append(f"{label}.sha256={expected!r}, actual {actual!r}")


def check_tensor_digest(
    label: str,
    digest: dict[str, Any],
    failures: list[str],
) -> None:
    path_text = digest.get("path", "")
    expected = digest.get("sha256", "")
    if path_text:
        check_path_hash(label, path_text, expected, failures)


def main() -> int:
    args = parse_args()
    try:
        receipt = load_json(resolve(args.receipt))
        schema = load_json(resolve(args.schema))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: CSL reference parity gate: {exc}")
        return 1

    failures = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(receipt),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    ]

    source = receipt.get("sourceProgram", {})
    check_path_hash(
        "sourceProgram.manifest",
        source.get("manifestPath", ""),
        source.get("manifestSha256", ""),
        failures,
    )
    check_path_hash(
        "sourceProgram.graph",
        source.get("graphPath", ""),
        source.get("graphSha256", ""),
        failures,
    )

    csl_run = receipt.get("cslRun", {})
    trace_path_text = csl_run.get("tracePath", "")
    check_path_hash(
        "cslRun.trace",
        trace_path_text,
        csl_run.get("traceSha256", ""),
        failures,
    )

    trace: dict[str, Any] = {}
    trace_path = resolve(trace_path_text) if trace_path_text else None
    if trace_path and trace_path.is_file():
        try:
            trace = load_json(trace_path)
        except json.JSONDecodeError as exc:
            failures.append(f"cslRun.trace invalid JSON: {exc}")

    if trace:
        executed = trace.get("executedRun", {})
        layer = trace.get("layerBlockSmoke", {})
        if csl_run.get("status") != executed.get("status"):
            failures.append(
                f"cslRun.status={csl_run.get('status')!r}, "
                f"trace status={executed.get('status')!r}"
            )
        if csl_run.get("kernelStage") != layer.get("kernelStage"):
            failures.append(
                "cslRun.kernelStage does not match "
                "trace layerBlockSmoke.kernelStage"
            )
        if csl_run.get("kernelIsStub") != layer.get("kernelIsStub"):
            failures.append(
                "cslRun.kernelIsStub does not match "
                "trace layerBlockSmoke.kernelIsStub"
            )
        if args.require_trace_success:
            parity = executed.get("numericalParity", {})
            if executed.get("status") != "succeeded":
                failures.append(
                    "trace executedRun.status="
                    f"{executed.get('status')!r}, expected 'succeeded'"
                )
            if not parity.get("passed", False):
                failures.append(
                    "trace numericalParity.passed="
                    f"{parity.get('passed')!r}, expected true"
                )
            if layer.get("kernelIsStub", True):
                failures.append("trace layerBlockSmoke.kernelIsStub=true")

    comparison = receipt.get("comparison", {})
    if not comparison.get("sameManifestHash", False):
        failures.append("comparison.sameManifestHash=false")
    if not comparison.get("sameGraphHash", False):
        failures.append("comparison.sameGraphHash=false")

    if args.require_output_parity and args.require_tolerance_parity:
        failures.append(
            "--require-output-parity and --require-tolerance-parity "
            "are mutually exclusive; pick one"
        )

    if args.require_output_parity:
        ref_output = receipt.get("referenceRun", {}).get("output", {})
        csl_output = csl_run.get("output", {})
        if comparison.get("status") != "passed":
            failures.append(
                f"comparison.status={comparison.get('status')!r}, "
                "expected 'passed'"
            )
        check_tensor_digest("referenceRun.output", ref_output, failures)
        check_tensor_digest("cslRun.output", csl_output, failures)
        if not ref_output.get("sha256") or not csl_output.get("sha256"):
            failures.append(
                "referenceRun.output.sha256 and cslRun.output.sha256 "
                "are required"
            )
        elif ref_output.get("sha256") != csl_output.get("sha256"):
            failures.append(
                "referenceRun.output.sha256 does not match "
                "cslRun.output.sha256"
            )
        if comparison.get("outputHashMatch") is not True:
            failures.append("comparison.outputHashMatch is not true")

    if args.require_tolerance_parity:
        ref_output = receipt.get("referenceRun", {}).get("output", {})
        csl_output = csl_run.get("output", {})
        atol = comparison.get("atol")
        if atol is None:
            failures.append(
                "--require-tolerance-parity needs comparison.atol "
                "to be set in the receipt"
            )
        if comparison.get("status") != "passed":
            failures.append(
                f"comparison.status={comparison.get('status')!r}, "
                "expected 'passed'"
            )
        ref_path_text = ref_output.get("path", "")
        csl_path_text = csl_output.get("path", "")
        if not ref_path_text or not csl_path_text:
            failures.append(
                "referenceRun.output.path and cslRun.output.path "
                "are required for tolerance parity"
            )
        else:
            import numpy as _np  # local to avoid top-level dep
            ref_path = resolve(ref_path_text)
            csl_path = resolve(csl_path_text)
            if not ref_path.is_file():
                failures.append(
                    f"referenceRun.output.path missing: {ref_path_text}"
                )
            if not csl_path.is_file():
                failures.append(f"cslRun.output.path missing: {csl_path_text}")
            if ref_path.is_file() and csl_path.is_file():
                ref_f32 = _np.fromfile(ref_path, dtype=_np.float32)
                csl_f32 = _np.fromfile(csl_path, dtype=_np.float32)
                if ref_f32.shape != csl_f32.shape:
                    failures.append(
                        "referenceRun.output and cslRun.output shapes "
                        f"differ: {ref_f32.shape} vs {csl_f32.shape}"
                    )
                else:
                    max_abs = float(_np.max(_np.abs(ref_f32 - csl_f32)))
                    recorded = comparison.get("maxAbsErr")
                    if recorded is not None:
                        if abs(float(recorded) - max_abs) > 1e-12:
                            failures.append(
                                f"comparison.maxAbsErr={recorded!r} "
                                f"but recomputed={max_abs:.6e}"
                            )
                    if atol is not None and max_abs > float(atol):
                        failures.append(
                            f"tolerance parity: max_abs={max_abs:.6e} "
                            f"exceeds atol={atol}"
                        )

    if args.require_promotion_ready:
        criteria = receipt.get("promotionCriteria", {})
        for key, value in sorted(criteria.items()):
            if key == "hardwareReceiptRequiredForHardwareClaim":
                continue
            if value is not True:
                failures.append(f"promotionCriteria.{key}={value!r}, expected true")

    if failures:
        print("FAIL: CSL reference parity gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    status = comparison.get("status", "unknown")
    print(
        "PASS: CSL reference parity gate "
        f"(model={receipt.get('modelId', '?')}, comparison={status!r}, "
        f"trace={csl_run.get('status', 'unknown')!r})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
