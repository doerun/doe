#!/usr/bin/env python3
"""Build a Doe-side digest for Doppler vendor benchmark artifacts.

The source artifacts live in the sibling Doppler repo. This tool keeps the
Doe cockpit from serving those full logs directly while preserving provenance
through source paths and SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SOURCES = (
    "../doppler/benchmarks/vendors/results/compare_20260421T132112.json",
    "../doppler/benchmarks/vendors/results/compare_20260421T134458.json",
    "../doppler/benchmarks/vendors/results/compare_20260421T132340.json",
    "../doppler/benchmarks/vendors/results/compare_20260421T135045.json",
)
DEFAULT_OUT = (
    "config/generated/doppler-vs-tjs-20260421-digest.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Doppler compare artifact to summarize. May repeat.",
    )
    parser.add_argument("--out-json", default=DEFAULT_OUT)
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object JSON at {path}")
    return value


def metric_number(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def speedup(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or right <= 0:
        return None
    return left / right


def classify_tjs_blocker(error: dict[str, Any] | None) -> dict[str, Any] | None:
    if not error:
        return None
    text = "\n".join(
        str(error.get(key) or "")
        for key in ("message", "stderrTail")
    )
    if (
        "Failed to load external data file" in text
        and "embed_tokens_q4f16.onnx_data" in text
    ):
        return {
            "code": "transformersjs_ort_webgpu_external_data_load_failed",
            "summary": (
                "Transformers.js/ONNX Runtime WebGPU failed while loading "
                "Gemma q4f16 external data for embed_tokens_q4f16.onnx_data."
            ),
        }
    return {
        "code": "transformersjs_benchmark_failed",
        "summary": "Transformers.js benchmark failed; see source artifact.",
    }


def load_mode_resolution(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("loadModeResolution")
    if not isinstance(value, dict):
        return {}
    keys = (
        "sharedOverride",
        "sharedOverrideSource",
        "profileDefault",
        "profileDefaultReason",
        "warm",
        "cold",
    )
    return {key: value[key] for key in keys if key in value}


def build_row(path: Path, source_ref: str) -> dict[str, Any]:
    raw = load_json(path)
    parity = ((raw.get("sections") or {}).get("compute") or {}).get("parity") or {}
    doppler = ((parity.get("doppler") or {}).get("result") or {}).get("metrics") or {}
    tjs_block = parity.get("transformersjs") or {}
    tjs_metrics = tjs_block.get("metrics") or {}
    tjs_error = tjs_block.get("error")
    blocker = classify_tjs_blocker(tjs_error if isinstance(tjs_error, dict) else None)

    doppler_decode = metric_number(doppler, "decodeTokensPerSec")
    tjs_decode = metric_number(tjs_metrics, "decodeTokensPerSec")
    doppler_prompt = metric_number(doppler, "medianPrefillTokensPerSecTtft")
    tjs_prompt = metric_number(tjs_metrics, "promptTokensPerSecToFirstToken")
    exact_match = (raw.get("correctness") or {}).get("exactMatch")
    tjs_ran = tjs_decode is not None and blocker is None
    claimable = (
        raw.get("compareLane", {}).get("declared") == "performance_comparable"
        and tjs_ran
        and exact_match is True
        and doppler_decode is not None
        and tjs_decode is not None
        and doppler_decode > tjs_decode
    )
    if claimable:
        claim_status = "claimable_doppler_faster"
    elif blocker is not None:
        claim_status = "blocked_transformersjs_load"
    else:
        claim_status = "diagnostic_only"

    return {
        "artifact": {
            "path": source_ref,
            "sha256": sha256_file(path),
            "timestamp": raw.get("timestamp"),
        },
        "benchmarkLaneId": path.stem,
        "claimStatus": claim_status,
        "compareLane": raw.get("compareLane") or {},
        "correctness": {
            "status": (raw.get("correctness") or {}).get("status"),
            "exactMatch": exact_match,
            "normalizedMatch": (
                (raw.get("correctness") or {}).get("normalizedMatch")
            ),
        },
        "dopplerArtifactIdentity": raw.get("dopplerArtifactIdentity") or {},
        "dopplerModelId": raw.get("dopplerModelId"),
        "loadModeResolution": load_mode_resolution(raw),
        "metrics": {
            "decodeTokensPerSec": {
                "doppler": doppler_decode,
                "transformersjs": tjs_decode,
                "speedup": speedup(doppler_decode, tjs_decode),
            },
            "promptTokensPerSecToFirstToken": {
                "doppler": doppler_prompt,
                "transformersjs": tjs_prompt,
                "speedup": speedup(doppler_prompt, tjs_prompt),
            },
        },
        "sourceCheckpointId": (
            (raw.get("dopplerArtifactIdentity") or {}).get("sourceCheckpointId")
        ),
        "transformersjsBlocker": blocker,
        "transformersjsModelId": raw.get("tjsModelId"),
    }


def build_digest(sources: list[tuple[str, Path]]) -> dict[str, Any]:
    rows = [build_row(path, source_ref) for source_ref, path in sources]
    qwen_claims = [
        row for row in rows
        if row["claimStatus"] == "claimable_doppler_faster"
        and str(row.get("sourceCheckpointId", "")).startswith("Qwen/")
    ]
    gemma_blocked = [
        row for row in rows
        if str(row.get("sourceCheckpointId")) == "google/gemma-4-E2B-it"
        and row["claimStatus"] == "blocked_transformersjs_load"
    ]
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_doppler_vendor_benchmark_digest",
        "digestId": "doppler-vs-tjs-20260421",
        "source": {
            "sourceRepo": "../doppler",
            "sourceKind": "doppler_vendor_compare_artifacts",
        },
        "rows": rows,
        "rollup": {
            "claimableQwenComparisons": len(qwen_claims),
            "gemmaE2bTransformersjsBlocked": len(gemma_blocked),
            "gemmaE2bBlockerCode": (
                gemma_blocked[0]["transformersjsBlocker"]["code"]
                if gemma_blocked else None
            ),
            "performanceClaimBoundary": (
                "Qwen rows with exact-match correctness and comparable "
                "Doppler/TJS WebGPU metrics are claimable. Gemma 4 E2B "
                "rows are blocked because Transformers.js/ORT WebGPU did "
                "not load the ONNX external-data artifact on this host."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    raw_sources = args.source or list(DEFAULT_SOURCES)
    sources = [(raw, resolve(raw)) for raw in raw_sources]
    missing = [source_ref for source_ref, path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing source artifacts: {missing}")
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    digest = build_digest(sources)
    out_path.write_text(
        json.dumps(digest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
