from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORT_RUNNER = REPO_ROOT / "browser" / "chromium" / "scripts" / "webgpu-playwright-ort-bench.mjs"


def test_ort_runner_records_runtime_selector_identity() -> None:
    source = ORT_RUNNER.read_text(encoding="utf-8")

    assert "const RUNTIME_SELECTOR_VERSION = \"browser-runtime-selector-v1\";" in source
    assert "function buildRuntimeSelection(mode, args, launchArgs)" in source
    assert "const browserExecutableSha256 = fileHashHex(args.chromePath);" in source
    assert "browserExecutableSha256," in source
    assert "dawnRuntimeSha256: browserExecutableSha256" in source
    assert "doeLibSha256: mode === \"doe\" ? fileHashHex(args.doeLibPath) : null" in source
    assert "function shaderCompilerIdentity(mode, args)" in source
    assert "shaderCompilerIdentity: shaderCompilerIdentity(mode, args)" in source
    assert "function adapterIdentityFromSummary(summary)" in source
    assert "adapterIdentity: adapterIdentityFromSummary(result.adapterSummary)" in source
    assert "function attachHashChain(entries)" in source
    assert "const modeResultsWithHashes = attachHashChain(modeResults)" in source
    assert "workloadIdentity: {" in source
    assert "taskConfigHash: hashHex(taskDefinition(args.task))" in source
    assert "runtimeSelection: buildRuntimeSelection(mode, args, launchArgs)" in source
    assert "runtimeSelections: modeResultsWithHashes.map((entry) => entry.runtimeSelection)" in source
