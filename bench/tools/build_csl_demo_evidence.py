#!/usr/bin/env python3
"""Build a dashboard-friendly CSL demo evidence adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-receipt",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    parser.add_argument(
        "--reference-parity",
        default=(
            "examples/"
            "doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json"
        ),
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/csl-demo-evidence/gemma-4-e2b-demo-evidence.json",
    )
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_sha(path_text: str) -> str:
    path = resolve(path_text)
    return sha256_file(path) if path.is_file() else ""


def main() -> int:
    args = parse_args()
    model_path = resolve(args.model_receipt)
    parity_path = resolve(args.reference_parity)
    model = load_json(model_path)
    parity = load_json(parity_path)

    source = parity["sourceProgram"]
    ref_status = parity["referenceRun"]["status"]
    csl_status = parity["cslRun"]["status"]
    csl_parity = parity["cslRun"].get("numericalParity", {})
    model_blocker = model.get("executionBlocker", "unknown")
    model_status = model.get("executionStatus", "unknown")
    end_to_end = model.get("endToEndModelExecution") or {}
    end_to_end_status = end_to_end.get("status", "not_attempted")
    end_to_end_blocker = end_to_end.get(
        "blocker", "full_e2b_end_to_end_receipt_absent"
    )
    model_end_to_end_passed = end_to_end_status == "succeeded"

    rows = [
        {
            "id": "doppler-browser-reference",
            "label": "Doppler browser/WebGPU reference",
            "runtime": "browser_webgpu",
            "status": "pass" if ref_status == "output_ready" else "metadata_bound",
            "summary": (
                "Same manifest and graph are bound; external browser "
                "output vector is still pending."
            ),
            "evidencePath": rel(parity_path),
            "evidenceSha256": sha256_file(parity_path),
            "blocker": parity["comparison"].get("blocker", ""),
        },
        {
            "id": "csl-simfabric-layer-block",
            "label": "Doe CSL simfabric layer-block proof",
            "runtime": "csl_simfabric",
            "status": (
                "pass"
                if csl_status == "succeeded" and csl_parity.get("passed")
                else "blocked"
            ),
            "summary": parity["cslRun"].get("kernelStage", ""),
            "evidencePath": parity["cslRun"]["tracePath"],
            "evidenceSha256": evidence_sha(parity["cslRun"]["tracePath"]),
            "maxAbsErr": float(csl_parity.get("maxAbsErr", 0.0)),
            "parityPassed": bool(csl_parity.get("passed", False)),
        },
        {
            "id": "csl-full-model",
            "label": "Doe CSL end-to-end E2B gate",
            "runtime": "csl_model",
            "status": "pass" if model_end_to_end_passed else "not_attempted",
            "summary": (
                f"modelRuntimeExecutionStatus={model_status}; "
                f"end_to_end={end_to_end_status}; "
                f"blocker={end_to_end_blocker}"
            ),
            "evidencePath": rel(model_path),
            "evidenceSha256": sha256_file(model_path),
            "blocker": end_to_end_blocker,
        },
        {
            "id": "csl-hardware",
            "label": "Doe CSL WSC hardware receipt",
            "runtime": "csl_hardware",
            "status": "pending",
            "summary": (
                "Hardware row is pending a WSC appliance receipt for "
                "the same manifest and graph."
            ),
            "evidencePath": rel(model_path),
            "evidenceSha256": sha256_file(model_path),
            "blocker": "hardware_receipt_not_available",
        },
    ]

    out = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_demo_evidence",
        "modelId": model["modelId"],
        "sourceProgram": {
            "manifestPath": source["manifestPath"],
            "manifestSha256": source["manifestSha256"],
            "graphPath": source["graphPath"],
            "graphSha256": source["graphSha256"],
        },
        "rows": rows,
    }
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
