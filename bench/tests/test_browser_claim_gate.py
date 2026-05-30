#!/usr/bin/env python3
"""Tests for browser claim gate artifact preservation."""

from __future__ import annotations

from pathlib import Path

from bench.browser.browser_claim_gate import chromium_patch_manifest_failures, reuse_window_artifacts


def test_reuse_window_artifacts_preserves_capability_artifact_paths(tmp_path: Path) -> None:
    for name in (
        "dawn-vs-doe.browser.playwright-smoke.diagnostic.json",
        "browser-cts-subset.json",
        "browser-recovery-parity.json",
        "browser-canvas-webgpu-fusion.json",
        "browser-media-path-probe.json",
        "browser-gpu-scheduler.json",
        "browser-webgpu-effect-experiment.json",
        "browser-gpu-flight-recorder.json",
        "browser-gpu-flight-replay.json",
        "browser-shader-links.json",
        "browser-local-ai-workloads.json",
        "browser-pipeline-cache-receipts.json",
        "browser-fallback-explanations.json",
        "dawn-vs-doe.browser-layered.superset.diagnostic.json",
        "dawn-vs-doe.browser-layered.superset.summary.json",
        "dawn-vs-doe.browser-layered.superset.check.json",
    ):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")

    artifacts = reuse_window_artifacts(tmp_path)

    assert "smokeReport" in artifacts
    assert "ctsSubsetReport" in artifacts
    assert "recoveryParityReport" in artifacts
    assert "canvasWebgpuFusionReport" in artifacts
    assert "mediaPathProbeReport" in artifacts
    assert "gpuSchedulerReport" in artifacts
    assert "webgpuEffectExperimentReport" in artifacts
    assert "flightRecorderReport" in artifacts
    assert "flightReplayReport" in artifacts
    assert "shaderLinksReport" in artifacts
    assert "localAiWorkloadsReport" in artifacts
    assert "pipelineCacheReceiptsReport" in artifacts
    assert "fallbackExplanationsReport" in artifacts
    assert "layeredReport" in artifacts
    assert "summaryReport" in artifacts
    assert "checkReport" in artifacts


def test_chromium_patch_manifest_resolution_rejects_policy_path_escape(tmp_path: Path) -> None:
    policy_path = tmp_path / "chromium-fork-maintenance-policy.json"
    policy_path.write_text(
        '{"patchIsolation": {"patchManifestPath": "../outside/manifest.json"}}\n',
        encoding="utf-8",
    )

    assert chromium_patch_manifest_failures(policy_path, tmp_path) == [
        "chromium-patch-manifest: failed to resolve manifest path: "
        "patchIsolation.patchManifestPath must be repo-relative: ../outside/manifest.json"
    ]
