#!/usr/bin/env python3
"""Structurally replay a browser GPU flight-recorder artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = REPO_ROOT / "examples" / "browser-gpu-flight-recorder.sample.json"
CAPTURE_POLICY_PATH = REPO_ROOT / "config" / "browser-capture-policy.json"
FLIGHT_REPLAY_SURFACE_ID = "flight_replay"
EXPECTED_SOURCE_SCHEMA_VERSION = 1
EXPECTED_SOURCE_KIND = "browser_gpu_flight_recorder"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flight-recorder",
        default=str(DEFAULT_SOURCE),
        help="Path to browser_gpu_flight_recorder JSON artifact.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path for browser_gpu_flight_replay JSON report.",
    )
    parser.add_argument(
        "--capture-policy",
        default=str(CAPTURE_POLICY_PATH),
        help="Browser capture policy JSON path.",
    )
    parser.add_argument(
        "--responsibility-map-root",
        default=str(REPO_ROOT),
        help="Repository root used to resolve the flight recorder responsibilityMap.path.",
    )
    parser.add_argument(
        "--allow-fail",
        action="store_true",
        help="Exit 0 after writing a failed replay report.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Print the replay report JSON to stdout.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def fail(code: str, path: str, message: str, severity: str = "error") -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "source": "flight_recorder_replay",
        "message": message,
        "path": path,
    }


def policy_fail(code: str, path: str, message: str, severity: str = "error") -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "source": "browser_policy",
        "message": message,
        "path": path,
    }


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_repo_path(root: Path, path_text: str) -> Path | None:
    if not safe_repo_path(path_text):
        return None
    resolved = root.joinpath(*PurePosixPath(path_text).parts).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def load_capture_surface_policy(policy_path: Path, surface_id: str = FLIGHT_REPLAY_SURFACE_ID) -> dict[str, Any]:
    payload = load_json(policy_path)
    for row in payload.get("surfaces", []):
        if isinstance(row, dict) and row.get("surfaceId") == surface_id:
            return row
    raise ValueError(f"capture policy missing surface {surface_id!r}: {policy_path}")


def replay_policy_failures(surface_policy: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if surface_policy.get("replayAllowed") is not True:
        failures.append(
            policy_fail(
                "replay_surface_disabled",
                "surfaces.flight_replay.replayAllowed",
                "flight replay surface must allow replay",
            )
        )
    if surface_policy.get("permissionGate") != "secure_context_devtools_opt_in":
        failures.append(
            policy_fail(
                "replay_without_secure_gate",
                "surfaces.flight_replay.permissionGate",
                "flight replay requires secure-context devtools opt-in",
            )
        )
    if surface_policy.get("developerVisible") is not True:
        failures.append(
            policy_fail(
                "replay_not_developer_visible",
                "surfaces.flight_replay.developerVisible",
                "flight replay must be declared developer-visible",
            )
        )
    return failures


def responsibility_map_failures(payload: dict[str, Any], root: Path) -> list[dict[str, str]]:
    responsibility_map = payload.get("responsibilityMap")
    if not isinstance(responsibility_map, dict):
        return [
            fail(
                "missing_responsibility_map",
                "responsibilityMap",
                "flight recorder must declare responsibilityMap",
                "fatal",
            )
        ]

    path_text = responsibility_map.get("path")
    if not isinstance(path_text, str) or not path_text:
        return [
            fail(
                "missing_responsibility_map_path",
                "responsibilityMap.path",
                "responsibilityMap.path is required",
            )
        ]
    resolved = resolve_repo_path(root, path_text)
    if resolved is None:
        return [
            fail(
                "unsafe_responsibility_map_path",
                "responsibilityMap.path",
                "responsibilityMap.path must be repo-relative",
            )
        ]
    if not resolved.is_file():
        return [
            fail(
                "missing_responsibility_map_file",
                "responsibilityMap.path",
                f"responsibility map not found: {path_text}",
            )
        ]

    try:
        map_payload = load_json(resolved)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [
            fail(
                "invalid_responsibility_map",
                "responsibilityMap.path",
                f"responsibility map is not valid JSON object: {exc}",
            )
        ]

    if responsibility_map.get("mapVersion") != map_payload.get("mapVersion"):
        return [
            fail(
                "responsibility_map_version_mismatch",
                "responsibilityMap.mapVersion",
                "flight recorder responsibilityMap.mapVersion must match referenced map",
            )
        ]
    return []


def replay_flight_recorder(
    payload: dict[str, Any],
    source_path: str,
    policy_path: str = "config/browser-capture-policy.json",
    capture_surface_policy: dict[str, Any] | None = None,
    responsibility_map_root: Path | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    if capture_surface_policy is None:
        capture_surface_policy = load_capture_surface_policy(REPO_ROOT / policy_path)
    failures.extend(replay_policy_failures(capture_surface_policy))
    failures.extend(responsibility_map_failures(payload, responsibility_map_root or REPO_ROOT))
    if payload.get("schemaVersion") != EXPECTED_SOURCE_SCHEMA_VERSION:
        failures.append(
            fail(
                "invalid_schema_version",
                "schemaVersion",
                f"schemaVersion must be {EXPECTED_SOURCE_SCHEMA_VERSION}",
                "fatal",
            )
        )
    if payload.get("artifactKind") != EXPECTED_SOURCE_KIND:
        failures.append(
            fail(
                "invalid_artifact_kind",
                "artifactKind",
                f"artifactKind must be {EXPECTED_SOURCE_KIND}",
                "fatal",
            )
        )

    shader_ids = {
        shader.get("shaderId")
        for shader in payload.get("shaders", [])
        if isinstance(shader, dict)
    }
    shader_ids.discard(None)

    buffer_ids = {
        buffer.get("bufferId")
        for buffer in payload.get("buffers", [])
        if isinstance(buffer, dict)
    }
    texture_ids = {
        texture.get("textureId")
        for texture in payload.get("textures", [])
        if isinstance(texture, dict)
    }
    bind_group_ids = {
        bind_group.get("bindGroupId")
        for bind_group in payload.get("bindGroups", [])
        if isinstance(bind_group, dict)
    }
    resource_ids = (buffer_ids | texture_ids | bind_group_ids) - {None}

    for bind_group_index, bind_group in enumerate(payload.get("bindGroups", [])):
        if not isinstance(bind_group, dict):
            continue
        for binding_index, binding in enumerate(bind_group.get("bindings", [])):
            resource_id = binding.get("resourceId") if isinstance(binding, dict) else None
            if resource_id not in resource_ids:
                failures.append(
                    fail(
                        "missing_bind_group_resource",
                        f"bindGroups[{bind_group_index}].bindings[{binding_index}].resourceId",
                        f"bind group references unknown resource {resource_id!r}",
                    )
                )

    command_graph = payload.get("commandGraph")
    if not isinstance(command_graph, dict):
        command_graph = {}
        failures.append(fail("missing_command_graph", "commandGraph", "missing commandGraph", "fatal"))

    nodes = command_graph.get("nodes", [])
    if not isinstance(nodes, list):
        nodes = []
        failures.append(fail("invalid_nodes", "commandGraph.nodes", "nodes must be an array", "fatal"))

    node_order: list[str] = []
    node_ops: dict[str, str] = {}
    seen_node_ids: set[str] = set()
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            failures.append(
                fail("invalid_node", f"commandGraph.nodes[{node_index}]", "node must be an object")
            )
            continue
        node_id = node.get("nodeId")
        if not isinstance(node_id, str) or not node_id:
            failures.append(
                fail("invalid_node_id", f"commandGraph.nodes[{node_index}].nodeId", "missing node id")
            )
            continue
        if node_id in seen_node_ids:
            failures.append(
                fail(
                    "duplicate_node_id",
                    f"commandGraph.nodes[{node_index}].nodeId",
                    f"duplicate command node id {node_id!r}",
                )
            )
            continue
        seen_node_ids.add(node_id)
        node_order.append(node_id)
        node_ops[node_id] = str(node.get("op", ""))

        for shader_index, shader_id in enumerate(node.get("shaderIds", [])):
            if shader_id not in shader_ids:
                failures.append(
                    fail(
                        "missing_shader",
                        f"commandGraph.nodes[{node_index}].shaderIds[{shader_index}]",
                        f"node references unknown shader {shader_id!r}",
                    )
                )

        for resource_index, resource_id in enumerate(node.get("resourceIds", [])):
            if resource_id not in resource_ids:
                failures.append(
                    fail(
                        "missing_resource",
                        f"commandGraph.nodes[{node_index}].resourceIds[{resource_index}]",
                        f"node references unknown resource {resource_id!r}",
                    )
                )

    node_ids = set(node_order)
    node_positions = {node_id: index for index, node_id in enumerate(node_order)}
    submit_ids = command_graph.get("submitIds", [])
    if not isinstance(submit_ids, list) or not submit_ids:
        failures.append(fail("missing_submit_ids", "commandGraph.submitIds", "commandGraph must declare submitIds"))
    else:
        seen_submit_ids: set[str] = set()
        for submit_index, submit_id in enumerate(submit_ids):
            if not isinstance(submit_id, str) or not submit_id:
                failures.append(
                    fail(
                        "invalid_submit_id",
                        f"commandGraph.submitIds[{submit_index}]",
                        "submitId must be non-empty string",
                    )
                )
                continue
            if submit_id in seen_submit_ids:
                failures.append(
                    fail(
                        "duplicate_submit_id",
                        f"commandGraph.submitIds[{submit_index}]",
                        f"duplicate submit id {submit_id!r}",
                    )
                )
            seen_submit_ids.add(submit_id)

    for edge_index, edge in enumerate(command_graph.get("edges", [])):
        if not isinstance(edge, dict):
            failures.append(
                fail("invalid_edge", f"commandGraph.edges[{edge_index}]", "edge must be an object")
            )
            continue
        for endpoint in ("fromNodeId", "toNodeId"):
            if edge.get(endpoint) not in node_ids:
                failures.append(
                    fail(
                        "missing_edge_node",
                        f"commandGraph.edges[{edge_index}].{endpoint}",
                        f"edge references unknown node {edge.get(endpoint)!r}",
                    )
                )
        from_node = edge.get("fromNodeId")
        to_node = edge.get("toNodeId")
        if (
            edge.get("edgeKind") in {"orders_before", "presents"}
            and from_node in node_positions
            and to_node in node_positions
            and node_positions[from_node] >= node_positions[to_node]
        ):
            failures.append(
                fail(
                    "edge_order_not_forward",
                    f"commandGraph.edges[{edge_index}]",
                    f"edge {from_node!r}->{to_node!r} does not follow node order",
                )
            )

    for timing_index, timing in enumerate(payload.get("timings", [])):
        if not isinstance(timing, dict):
            continue
        node_id = timing.get("nodeId")
        if node_id is not None and node_id not in node_ids:
            failures.append(
                fail(
                    "missing_timing_node",
                    f"timings[{timing_index}].nodeId",
                    f"timing references unknown node {node_id!r}",
                )
            )

    for frame_index, frame in enumerate(payload.get("frames", [])):
        if not isinstance(frame, dict):
            continue
        present_node_id = frame.get("presentNodeId")
        if present_node_id is None:
            continue
        if present_node_id not in node_ids:
            failures.append(
                fail(
                    "missing_frame_present_node",
                    f"frames[{frame_index}].presentNodeId",
                    f"frame references unknown present node {present_node_id!r}",
                )
            )
        elif node_ops.get(present_node_id) != "present":
            failures.append(
                fail(
                    "frame_node_not_present",
                    f"frames[{frame_index}].presentNodeId",
                    f"frame present node {present_node_id!r} has op {node_ops.get(present_node_id)!r}",
                )
            )

    replay_status = "fail" if any(item["severity"] in {"error", "fatal"} for item in failures) else "pass"
    return {
        "schemaVersion": 1,
        "artifactKind": "browser_gpu_flight_replay",
        "captureId": str(payload.get("captureId", "")),
        "sourcePath": source_path,
        "sourceArtifactKind": str(payload.get("artifactKind", "")),
        "policyPath": policy_path,
        "graphSha256": str(command_graph.get("graphSha256", "")),
        "replayStatus": replay_status,
        "nodeOrder": node_order,
        "failureCodes": failures,
    }


def main() -> int:
    args = parse_args()
    source_path = Path(args.flight_recorder)
    if not source_path.is_absolute():
        source_path = (Path.cwd() / source_path).resolve()

    try:
        payload = load_json(source_path)
        policy_path = Path(args.capture_policy)
        if not policy_path.is_absolute():
            policy_path = (Path.cwd() / policy_path).resolve()
        report = replay_flight_recorder(
            payload,
            display_path(source_path),
            display_path(policy_path),
            load_capture_surface_policy(policy_path),
            Path(args.responsibility_map_root).resolve(),
        )
    except Exception as exc:
        report = {
            "schemaVersion": 1,
            "artifactKind": "browser_gpu_flight_replay",
            "captureId": "",
            "sourcePath": str(source_path),
            "sourceArtifactKind": "",
            "policyPath": str(Path(args.capture_policy)),
            "graphSha256": "0" * 64,
            "replayStatus": "fail",
            "nodeOrder": [],
            "failureCodes": [
                fail("replay_exception", "flightRecorder", str(exc), "fatal")
            ],
        }

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif report["replayStatus"] == "pass":
        print("PASS: browser GPU flight recorder replay")
    else:
        print("FAIL: browser GPU flight recorder replay")
        for failure in report["failureCodes"]:
            print(f"- {failure['code']}: {failure['path']}: {failure['message']}")

    if report["replayStatus"] == "fail" and not args.allow_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
