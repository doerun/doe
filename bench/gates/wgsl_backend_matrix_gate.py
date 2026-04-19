#!/usr/bin/env python3
"""Validate a WGSL cross-backend matrix report."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


def csl_sdk_detected() -> bool:
    """True when the Cerebras SDK (cslc binary) can be located locally.

    Checks (in order):
      1. DOE_CSL_SDK_ROOT env var pointing at a directory containing `cslc`.
      2. DOE_CSLC_EXECUTABLE env var pointing at an existing file.
      3. `cslc` on PATH.

    Used by --sdk-optional mode so the matrix gate can run in the blocking
    bundle even on machines without the SDK installed: CSL runtime-ready
    thresholds are only enforced when the SDK is present.
    """
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "").strip()
    if sdk_root and (Path(sdk_root) / "cslc").exists():
        return True
    sdk_root_bin = sdk_root and (Path(sdk_root) / "bin" / "cslc").exists()
    if sdk_root_bin:
        return True
    cslc_exe = os.environ.get("DOE_CSLC_EXECUTABLE", "").strip()
    if cslc_exe and Path(cslc_exe).exists():
        return True
    return shutil.which("cslc") is not None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/cross-backend-matrix/wgsl-backend-matrix.json")
    parser.add_argument("--schema", default="config/wgsl-backend-matrix-report.schema.json")
    parser.add_argument("--require-vulkan-ready", action="store_true")
    parser.add_argument("--require-metal-ready", action="store_true")
    parser.add_argument("--require-d3d12-ready", action="store_true")
    parser.add_argument("--min-csl-runtime-ready", type=int, default=0)
    parser.add_argument(
        "--sdk-optional",
        action="store_true",
        help=(
            "When set, --min-csl-runtime-ready is enforced only if the Cerebras "
            "SDK is detected locally (DOE_CSL_SDK_ROOT, DOE_CSLC_EXECUTABLE, or "
            "`cslc` on PATH). Lets the matrix gate run in the blocking bundle "
            "on SDK-absent hosts without weakening checks where SDK is present."
        ),
    )
    return parser.parse_args()


def resolve(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def row_backend_status(row: dict[str, Any], backend_key: str) -> str:
    backend = row.get("backends", {}).get(backend_key, {})
    if not isinstance(backend, dict):
        return "<missing>"
    status = backend.get("status")
    return status if isinstance(status, str) else "<missing>"


def main() -> int:
    args = parse_args()
    try:
        report = load_json_object(resolve(args.report))
        schema = load_json_object(resolve(args.schema))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: WGSL backend matrix gate: {exc}")
        return 1

    failures = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(report),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]

    rows = report.get("rows", [])
    if not isinstance(rows, list):
        rows = []

    required_backends: list[tuple[str, str]] = []
    if args.require_vulkan_ready:
        required_backends.append(("vulkan_spirv", "Vulkan SPIR-V"))
    if args.require_metal_ready:
        required_backends.append(("metal_msl", "Metal MSL"))
    if args.require_d3d12_ready:
        required_backends.extend([("d3d12_hlsl", "D3D12 HLSL"), ("d3d12_dxil", "D3D12 DXIL")])

    for row in rows:
        if not isinstance(row, dict):
            continue
        fixture_id = row.get("fixtureId", "<unknown>")
        for backend_key, backend_label in required_backends:
            status = row_backend_status(row, backend_key)
            if status != "ready":
                failures.append(f"{fixture_id}: {backend_label} status={status!r}, expected 'ready'")

    csl_ready = report.get("summary", {}).get("cslRuntimeReady", 0)
    if not isinstance(csl_ready, int):
        csl_ready = 0
    sdk_present = csl_sdk_detected()
    enforce_csl = args.min_csl_runtime_ready > 0 and (sdk_present or not args.sdk_optional)
    if enforce_csl and csl_ready < args.min_csl_runtime_ready:
        failures.append(f"summary.cslRuntimeReady={csl_ready}, expected >= {args.min_csl_runtime_ready}")

    if failures:
        print("FAIL: WGSL backend matrix gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    csl_note = ""
    if args.min_csl_runtime_ready > 0:
        if sdk_present:
            csl_note = f" (CSL runtime {csl_ready} >= {args.min_csl_runtime_ready}, SDK detected)"
        elif args.sdk_optional:
            csl_note = f" (CSL runtime {csl_ready}, SDK absent — threshold skipped)"
    print(f"PASS: WGSL backend matrix gate{csl_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
