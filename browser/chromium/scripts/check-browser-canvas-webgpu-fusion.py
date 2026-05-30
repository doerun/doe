#!/usr/bin/env python3
"""Validate browser canvas/WebGPU fusion probe structure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from browser_runtime_identity_reference import check_runtime_identity_reference


REQUIRED_SURFACE_KINDS = {"canvas_2d", "webgpu", "image_filter", "presentation"}
EXPECTED_KIND = "browser_canvas_webgpu_fusion_probe"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, help="Fusion probe JSON artifact.")
    parser.add_argument(
        "--runtime-identity-root",
        default="",
        help="Optional repository root used to resolve runtimeIdentity.runtimeIdentityPath.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def check_unique_ids(
    rows: Any,
    *,
    field: str,
    path: str,
    code: str,
    label: str,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(rows, list):
        return failures
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        value = row.get(field)
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            failures.append(failure(code, f"{path}[{index}].{field}", f"duplicate {label} {value}"))
        seen.add(value)
    return failures


def check_probe(
    payload: dict[str, Any],
    runtime_identity_root: Path | None = None,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        failures.append({
            "code": "invalid_schema_version",
            "path": "schemaVersion",
            "message": f"schemaVersion must be {EXPECTED_SCHEMA_VERSION}",
        })
    if payload.get("artifactKind") != EXPECTED_KIND:
        failures.append({
            "code": "invalid_artifact_kind",
            "path": "artifactKind",
            "message": f"artifactKind must be {EXPECTED_KIND}",
        })
    if runtime_identity_root is not None:
        failures.extend(check_runtime_identity_reference(payload, runtime_identity_root))
    surfaces = payload.get("surfaces", [])
    failures.extend(
        check_unique_ids(
            surfaces,
            field="surfaceId",
            path="surfaces",
            code="duplicate_surface_id",
            label="surfaceId",
        )
    )
    surface_ids = {surface.get("surfaceId") for surface in surfaces if isinstance(surface, dict)}
    surface_kinds = {surface.get("kind") for surface in surfaces if isinstance(surface, dict)}
    missing_kinds = sorted(REQUIRED_SURFACE_KINDS - surface_kinds)
    for kind in missing_kinds:
        failures.append({
            "code": "missing_surface_kind",
            "path": "surfaces",
            "message": f"missing required surface kind {kind}",
        })

    graph = payload.get("graph", {})
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    failures.extend(
        check_unique_ids(
            nodes,
            field="nodeId",
            path="graph.nodes",
            code="duplicate_node_id",
            label="nodeId",
        )
    )
    node_ids = {node.get("nodeId") for node in nodes if isinstance(node, dict)}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        if node.get("surfaceId") not in surface_ids:
            failures.append({
                "code": "missing_surface_reference",
                "path": f"graph.nodes[{index}].surfaceId",
                "message": f"node references unknown surface {node.get('surfaceId')!r}",
            })

    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        for endpoint in ("fromNodeId", "toNodeId"):
            if edge.get(endpoint) not in node_ids:
                failures.append({
                    "code": "missing_node_reference",
                    "path": f"graph.edges[{index}].{endpoint}",
                    "message": f"edge references unknown node {edge.get(endpoint)!r}",
                })

    output_surface_ids = {
        item.get("surfaceId")
        for item in payload.get("outputHashes", [])
        if isinstance(item, dict)
    }
    if "surface:present" not in output_surface_ids:
        failures.append({
            "code": "missing_output_hash",
            "path": "outputHashes",
            "message": "presentation surface must carry an output hash",
        })

    timing_surface_ids = {
        item.get("surfaceId")
        for item in payload.get("timingScopes", [])
        if isinstance(item, dict)
    }
    missing_timing = sorted(surface_ids - timing_surface_ids)
    for surface_id in missing_timing:
        failures.append({
            "code": "missing_timing_scope",
            "path": "timingScopes",
            "message": f"surface {surface_id!r} has no timing scope",
        })

    privacy = payload.get("privacy", {})
    if not isinstance(privacy, dict) or privacy.get("originScoped") is not True or privacy.get("rawPageDataIncluded") is not False:
        failures.append({
            "code": "unsafe_privacy_policy",
            "path": "privacy",
            "message": "fusion probe must be origin-scoped and exclude raw page data",
        })

    return failures


def main() -> int:
    args = parse_args()
    payload = load_json(Path(args.probe))
    runtime_identity_root = (
        Path(args.runtime_identity_root).resolve()
        if args.runtime_identity_root.strip()
        else None
    )
    failures = check_probe(payload, runtime_identity_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_canvas_webgpu_fusion_check",
        "probePath": args.probe,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser canvas/WebGPU fusion probe")
        for failure in failures:
            print(f"- {failure['code']}: {failure['path']}: {failure['message']}")
    else:
        print("PASS: browser canvas/WebGPU fusion probe")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
