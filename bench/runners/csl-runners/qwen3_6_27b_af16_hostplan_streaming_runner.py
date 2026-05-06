#!/usr/bin/env python3
"""Qwen 3.6 27B af16 HostPlan streaming-runner front door."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REPO_ROOT.parent

GEMMA_RUNNER = (
    REPO_ROOT
    / "bench/runners/csl-runners/gemma4_31b_af16_hostplan_streaming_runner.py"
)

DEFAULT_SOURCE_MANIFEST = (
    WORKSPACE_ROOT
    / "doppler/models/local/qwen-3-6-27b-q4k-eaf16/manifest.json"
)
DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT / "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json"
)
DEFAULT_HOSTPLAN_ROOT = (
    REPO_ROOT / "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16"
)
DEFAULT_PER_KERNEL_SUMMARY = (
    REPO_ROOT / "bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/summary.json"
)
DEFAULT_REFRESH_OUT_DIR = (
    REPO_ROOT / "bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel"
)
DEFAULT_SESSION_OUT_DIR = REPO_ROOT / "bench/out/r3-2-27b-af16-hostplan-session"
DEFAULT_OUT = REPO_ROOT / "bench/out/r3-2-27b-af16-hostplan-streaming/trace.json"


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str]) -> int:
    defaults = [
        "--expected-model-id",
        "qwen-3-6-27b-q4k-eaf16",
        "--lane-key",
        "q4k-eaf16",
        "--trace-artifact-kind",
        "doe_qwen3_6_27b_af16_hostplan_streaming_trace",
        "--session-artifact-prefix",
        "qwen3_6_27b_af16",
        "--claim-scope",
        (
            "Qwen 3.6 27B af16 hardware runner front door, weight staging "
            "plan, hybrid dispatch expansion, and HostPlan session contract "
            "are materialized."
        ),
        "--claim-not-what",
        (
            "Not a Qwen hardware transcript until status is output_ready and "
            "blockers is empty."
        ),
        "--claim-summary",
        (
            "Qwen now has the same operator-runner surface as Gemma, with "
            "returned hardware traces as the closure artifact."
        ),
        "--source-doppler-manifest",
        str(DEFAULT_SOURCE_MANIFEST),
        "--smoke-config",
        rel(DEFAULT_SMOKE_CONFIG),
        "--host-plan",
        rel(DEFAULT_HOSTPLAN_ROOT / "host-plan.json"),
        "--simulator-plan",
        rel(DEFAULT_HOSTPLAN_ROOT / "simulator-plan.json"),
        "--runtime-config",
        rel(DEFAULT_HOSTPLAN_ROOT / "runtime-config.json"),
        "--compile-root",
        rel(DEFAULT_HOSTPLAN_ROOT / "compile"),
        "--per-kernel-summary",
        rel(DEFAULT_PER_KERNEL_SUMMARY),
        "--refresh-out-dir",
        rel(DEFAULT_REFRESH_OUT_DIR),
        "--session-out-dir",
        rel(DEFAULT_SESSION_OUT_DIR),
        "--out",
        rel(DEFAULT_OUT),
    ]
    spec = importlib.util.spec_from_file_location(
        "gemma4_31b_af16_hostplan_streaming_runner",
        GEMMA_RUNNER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {GEMMA_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    sys.argv = [Path(__file__).name, *defaults, *argv]
    return int(module.main())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
