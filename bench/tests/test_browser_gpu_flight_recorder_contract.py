#!/usr/bin/env python3
"""Tests for the browser GPU flight-recorder artifact contract."""

from __future__ import annotations

import json
import importlib.util
import tempfile
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-gpu-flight-recorder.sample.json"
SCHEMA_PATH = REPO_ROOT / "config" / "browser-gpu-flight-recorder.schema.json"
BUILD_SCRIPT_PATH = (
    REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-gpu-flight-recorder.py"
)
REPLAY_SCRIPT_PATH = (
    REPO_ROOT / "browser" / "chromium" / "scripts" / "replay-browser-gpu-flight-recorder.py"
)

REQUIRED_TOP_LEVEL_FIELDS = {
    "runtimeIdentity",
    "adapterIdentity",
    "responsibilityMap",
    "shaders",
    "bindGroups",
    "buffers",
    "textures",
    "commandGraph",
    "timings",
    "frames",
    "failureCodes",
    "privacy",
}

REQUIRED_SHADER_FIELDS = {
    "sourceSha256",
    "irSha256",
    "loweringReceiptPath",
    "loweringReceiptRowId",
    "backendOutputSha256",
    "backendTarget",
}


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_replay_module():
    spec = importlib.util.spec_from_file_location("browser_gpu_flight_replay", REPLAY_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("browser_gpu_flight_builder", BUILD_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimal_browser_report() -> dict:
    return {
        "generatedAt": "2026-05-26T00:00:00Z",
        "runtimeSelections": [
            {
                "selectedRuntime": "dawn",
                "artifactIdentity": {
                    "browserExecutableSha256": "a" * 64,
                },
            },
            {
                "selectedRuntime": "doe",
                "artifactIdentity": {
                    "browserExecutableSha256": "b" * 64,
                    "doeLibSha256": "c" * 64,
                },
            },
        ],
        "modeResults": [
            {
                "mode": "doe",
                "elapsedMs": 7,
                "runtimeSelection": {
                    "selectedRuntime": "doe",
                    "selectorVersion": "browser-runtime-selector-v1",
                    "fallbackApplied": False,
                    "fallbackReasonCode": "",
                    "artifactIdentity": {
                        "browserExecutableSha256": "b" * 64,
                        "doeLibSha256": "c" * 64,
                    },
                },
                "adapterInfo": {},
                "limits": {"maxBufferSize": 1024},
                "smoke": {},
                "benches": {
                    "writeBuffer64kbUsPerOp": 2.5,
                    "computeDispatchUsPerOp": 3.0,
                    "iterations": {"upload": 4, "dispatch": 5},
                    "errors": [],
                },
                "errors": [],
            }
        ],
    }


def test_flight_recorder_sample_covers_required_capture_sections() -> None:
    sample = _load_sample()

    assert REQUIRED_TOP_LEVEL_FIELDS <= set(sample)
    assert sample["runtimeIdentity"]["selectedRuntime"] in {"dawn", "doe", "auto"}
    assert sample["responsibilityMap"]["path"] == "config/browser-responsibility-map.json"
    assert sample["privacy"]["originScoped"] is True
    assert sample["failureCodes"]


def test_flight_recorder_shader_records_bind_source_ir_and_backend_output() -> None:
    sample = _load_sample()

    assert sample["shaders"]
    for shader in sample["shaders"]:
        assert REQUIRED_SHADER_FIELDS <= set(shader)
        for field in REQUIRED_SHADER_FIELDS:
            assert shader[field]


def test_flight_recorder_command_graph_references_declared_resources() -> None:
    sample = _load_sample()
    shader_ids = {shader["shaderId"] for shader in sample["shaders"]}
    resource_ids = (
        {buffer["bufferId"] for buffer in sample["buffers"]}
        | {texture["textureId"] for texture in sample["textures"]}
        | {bind_group["bindGroupId"] for bind_group in sample["bindGroups"]}
    )
    node_ids = {node["nodeId"] for node in sample["commandGraph"]["nodes"]}

    for node in sample["commandGraph"]["nodes"]:
        assert set(node["shaderIds"]) <= shader_ids
        assert set(node["resourceIds"]) <= resource_ids

    for edge in sample["commandGraph"]["edges"]:
        assert edge["fromNodeId"] in node_ids
        assert edge["toNodeId"] in node_ids

    for timing in sample["timings"]:
        if "nodeId" in timing:
            assert timing["nodeId"] in node_ids

    for frame in sample["frames"]:
        if "presentNodeId" in frame:
            assert frame["presentNodeId"] in node_ids


def test_flight_recorder_replay_accepts_valid_sample() -> None:
    replay = _load_replay_module()

    report = replay.replay_flight_recorder(
        _load_sample(),
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "pass"
    assert report["policyPath"] == "config/browser-capture-policy.json"
    assert report["failureCodes"] == []
    assert report["nodeOrder"] == [
        "node:create_shader",
        "node:dispatch",
        "node:present",
    ]


def test_flight_recorder_replay_accepts_artifact_outside_repo() -> None:
    replay = _load_replay_module()
    with tempfile.TemporaryDirectory(prefix="doe-flight-recorder-") as tmpdir:
        artifact_path = Path(tmpdir) / "flight-recorder.json"
        artifact_path.write_text(json.dumps(_load_sample()) + "\n", encoding="utf-8")

        report = replay.replay_flight_recorder(
            replay.load_json(artifact_path),
            replay.display_path(artifact_path),
        )

    assert report["replayStatus"] == "pass"
    assert report["sourcePath"].endswith("flight-recorder.json")


def test_flight_recorder_replay_reports_typed_missing_resource() -> None:
    replay = _load_replay_module()
    sample = _load_sample()
    sample["commandGraph"]["nodes"][1]["resourceIds"].append("buffer:missing")

    report = replay.replay_flight_recorder(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "missing_resource",
        "severity": "error",
        "source": "flight_recorder_replay",
        "message": "node references unknown resource 'buffer:missing'",
        "path": "commandGraph.nodes[1].resourceIds[2]",
    } in report["failureCodes"]


def test_flight_recorder_replay_rejects_wrong_schema_version() -> None:
    replay = _load_replay_module()
    sample = _load_sample()
    sample["schemaVersion"] = 2

    report = replay.replay_flight_recorder(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "invalid_schema_version",
        "severity": "fatal",
        "source": "flight_recorder_replay",
        "message": "schemaVersion must be 1",
        "path": "schemaVersion",
    } in report["failureCodes"]


def test_flight_recorder_replay_reports_duplicate_node_id() -> None:
    replay = _load_replay_module()
    sample = _load_sample()
    sample["commandGraph"]["nodes"][2]["nodeId"] = "node:dispatch"

    report = replay.replay_flight_recorder(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "duplicate_node_id",
        "severity": "error",
        "source": "flight_recorder_replay",
        "message": "duplicate command node id 'node:dispatch'",
        "path": "commandGraph.nodes[2].nodeId",
    } in report["failureCodes"]


def test_flight_recorder_replay_reports_non_forward_order_edge() -> None:
    replay = _load_replay_module()
    sample = _load_sample()
    sample["commandGraph"]["edges"][0] = {
        "fromNodeId": "node:dispatch",
        "toNodeId": "node:create_shader",
        "edgeKind": "orders_before",
    }

    report = replay.replay_flight_recorder(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "edge_order_not_forward",
        "severity": "error",
        "source": "flight_recorder_replay",
        "message": "edge 'node:dispatch'->'node:create_shader' does not follow node order",
        "path": "commandGraph.edges[0]",
    } in report["failureCodes"]


def test_flight_recorder_replay_reports_policy_failure() -> None:
    replay = _load_replay_module()

    report = replay.replay_flight_recorder(
        _load_sample(),
        "examples/browser-gpu-flight-recorder.sample.json",
        capture_surface_policy={
            "surfaceId": "flight_replay",
            "replayAllowed": False,
            "permissionGate": "devtools_opt_in",
            "developerVisible": False,
        },
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "replay_surface_disabled",
        "severity": "error",
        "source": "browser_policy",
        "message": "flight replay surface must allow replay",
        "path": "surfaces.flight_replay.replayAllowed",
    } in report["failureCodes"]
    assert {
        "code": "replay_without_secure_gate",
        "severity": "error",
        "source": "browser_policy",
        "message": "flight replay requires secure-context devtools opt-in",
        "path": "surfaces.flight_replay.permissionGate",
    } in report["failureCodes"]


def test_flight_recorder_replay_rejects_stale_responsibility_map_version() -> None:
    replay = _load_replay_module()
    sample = _load_sample()
    sample["responsibilityMap"]["mapVersion"] = "stale-map-version"

    report = replay.replay_flight_recorder(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "responsibility_map_version_mismatch",
        "severity": "error",
        "source": "flight_recorder_replay",
        "message": "flight recorder responsibilityMap.mapVersion must match referenced map",
        "path": "responsibilityMap.mapVersion",
    } in report["failureCodes"]


def test_flight_recorder_replay_rejects_unsafe_responsibility_map_path() -> None:
    replay = _load_replay_module()
    sample = _load_sample()
    sample["responsibilityMap"]["path"] = "../browser-responsibility-map.json"

    report = replay.replay_flight_recorder(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert report["replayStatus"] == "fail"
    assert {
        "code": "unsafe_responsibility_map_path",
        "severity": "error",
        "source": "flight_recorder_replay",
        "message": "responsibilityMap.path must be repo-relative",
        "path": "responsibilityMap.path",
    } in report["failureCodes"]


def test_flight_recorder_builder_merges_browser_report_and_component_manifest() -> None:
    builder = _load_builder_module()
    components = _load_sample()
    components.pop("timings")

    artifact = builder.build_flight_recorder(
        report=_minimal_browser_report(),
        components=builder.require_component_manifest(components),
        mode="doe",
        scenario_id="webgpu-smoke",
        workload_id="compute_noop",
        origin="browser-chromium-local",
    )

    assert artifact["artifactKind"] == "browser_gpu_flight_recorder"
    assert artifact["runtimeIdentity"]["selectedRuntime"] == "doe"
    assert artifact["runtimeIdentity"]["doeRuntimeSha256"] == "c" * 64
    assert artifact["runtimeIdentity"]["dawnDelegateSha256"] is None
    assert artifact["adapterIdentity"]["limitsSha256"]
    assert artifact["timings"] == [
        {"phase": "upload", "durationNs": 10000},
        {"phase": "submit_wait", "durationNs": 15000},
    ]


def test_flight_recorder_builder_normalizes_unsafe_privacy_input() -> None:
    builder = _load_builder_module()
    components = _load_sample()
    components["privacy"] = {
        "originScoped": False,
        "pageDataPolicy": "explicit_debug_capture",
        "rawPageDataIncluded": True,
    }

    artifact = builder.build_flight_recorder(
        report=_minimal_browser_report(),
        components=builder.require_component_manifest(components),
        mode="doe",
        scenario_id="webgpu-smoke",
        workload_id="compute_noop",
        origin="browser-chromium-local",
        capture_surface_policy={
            "surfaceId": "gpu_flight_recorder",
            "rawPageDataPolicy": "hash",
        },
    )

    assert artifact["privacy"] == {
        "originScoped": True,
        "pageDataPolicy": "hash_only",
        "rawPageDataIncluded": False,
        "redactionNotes": "unsafe privacy input normalized by capture policy",
    }
    assert {failure["code"] for failure in artifact["failureCodes"]} == {
        "capture_not_origin_scoped",
        "raw_page_data_forbidden",
        "debug_capture_not_allowed",
    }
    jsonschema.validate(artifact, _load_schema())


def test_flight_recorder_builder_rejects_missing_component_sections() -> None:
    builder = _load_builder_module()
    components = _load_sample()
    components.pop("commandGraph")

    try:
        builder.require_component_manifest(components)
    except ValueError as exc:
        assert "component manifest missing fields: commandGraph" in str(exc)
    else:
        raise AssertionError("missing component manifest field should fail")
