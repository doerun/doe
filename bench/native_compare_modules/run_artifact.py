"""Build and load standalone run artifacts for product-based benchmarking.

A run artifact captures the result of running one product on one workload.
It is the unit of input for post-hoc comparison.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_compare_modules.workload_spec import ProductRunConfig, WorkloadSpec
from native_compare_modules.runner import file_sha256

RUN_ARTIFACT_SCHEMA_VERSION = 2
SUPPORTED_RUN_ARTIFACT_SCHEMA_VERSIONS = {1, 2}


def _contract_ref(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if isinstance(path, str) and not path.strip():
        return None
    contract_path = Path(path)
    if not contract_path.exists():
        return None
    return {
        "path": str(contract_path),
        "sha256": file_sha256(contract_path),
    }


def build_run_artifact(
    *,
    run_result: dict[str, Any],
    product: str,
    executor_id: str,
    workload_spec: WorkloadSpec,
    run_config: ProductRunConfig,
    iterations: int,
    warmup: int,
    resource_probe: str = "none",
    resource_sample_ms: int = 100,
    resource_sample_target_count: int = 0,
    workload_contract_path: str | Path | None = None,
    benchmark_policy_path: str | Path | None = None,
    comparability_mode: str = "",
    required_timing_class: str = "",
) -> dict[str, Any]:
    """Wrap a run_workload result dict into a standalone run artifact."""
    artifact = {
        "schemaVersion": RUN_ARTIFACT_SCHEMA_VERSION,
        "artifactKind": "run",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "product": product,
        "executorId": executor_id,
        "workloadContract": _contract_ref(workload_contract_path),
        "workload": {
            "id": workload_spec.id,
            "name": workload_spec.name,
            "description": workload_spec.description,
            "domain": workload_spec.domain,
            "commandsPath": workload_spec.commands_path,
            "quirksPath": workload_spec.quirks_path,
            "vendor": workload_spec.vendor,
            "api": workload_spec.api,
            "family": workload_spec.family,
            "driver": workload_spec.driver,
            "comparable": workload_spec.comparable,
            "benchmarkClass": workload_spec.benchmark_class,
            "comparabilityNotes": workload_spec.comparability_notes,
            "directionalReason": workload_spec.directional_reason,
            "pathAsymmetry": workload_spec.path_asymmetry,
            "pathAsymmetryNote": workload_spec.path_asymmetry_note,
            "includeByDefault": workload_spec.include_by_default,
            "asyncDiagnosticsMode": workload_spec.async_diagnostics_mode,
            "strictNormalizationUnit": workload_spec.strict_normalization_unit,
            "comparabilityCandidate": {
                "enabled": workload_spec.comparability_candidate_enabled,
                "tier": workload_spec.comparability_candidate_tier,
                "notes": workload_spec.comparability_candidate_notes,
            },
            "claimEligible": workload_spec.claim_eligible,
            "cohorts": list(workload_spec.cohorts),
        },
        "runParameters": {
            "iterations": iterations,
            "warmup": warmup,
            "commandRepeat": run_config.command_repeat,
            "ignoreFirstOps": run_config.ignore_first_ops,
            "timingDivisor": run_config.timing_divisor,
            "uploadBufferUsage": run_config.upload_buffer_usage,
            "uploadSubmitEvery": run_config.upload_submit_every,
            "allowNoExecution": run_config.allow_no_execution,
            "timingNormalizationNote": run_config.timing_normalization_note,
            "resourceProbe": resource_probe,
            "resourceSampleMs": resource_sample_ms,
            "resourceSampleTargetCount": resource_sample_target_count,
            "comparabilityMode": comparability_mode,
            "requiredTimingClass": required_timing_class,
        },
        "host": {
            "os": platform.system().lower(),
            "arch": platform.machine(),
        },
        "commandSamples": run_result.get("commandSamples", []),
        "stats": run_result.get("stats", {}),
        "timingsMs": run_result.get("timingsMs", []),
        "timingSources": run_result.get("timingSources", []),
        "timingClasses": run_result.get("timingClasses", []),
        "lastMeta": run_result.get("lastMeta", {}),
        "resourceStats": run_result.get("resourceStats", {}),
        "timingMetricsRawStatsMs": run_result.get("timingMetricsRawStatsMs", {}),
        "timingMetricsNormalizedStatsMs": run_result.get(
            "timingMetricsNormalizedStatsMs", {}
        ),
    }
    if artifact["workloadContract"] is None:
        raise ValueError(
            "run artifacts require workloadContract metadata; "
            "pass workload_contract_path when building the artifact"
        )
    benchmark_policy_contract = _contract_ref(benchmark_policy_path)
    if benchmark_policy_path and benchmark_policy_contract is None:
        raise ValueError(
            "run artifacts received a benchmark_policy_path that could not be "
            f"resolved: {benchmark_policy_path}"
        )
    if benchmark_policy_contract is not None:
        benchmark_policy_contract["schemaVersion"] = 1
        artifact["benchmarkPolicy"] = benchmark_policy_contract
    return artifact


def write_run_artifact(artifact: dict[str, Any], path: Path) -> Path:
    """Write a run artifact to disk. Returns the written path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_run_artifact(path: str | Path) -> dict[str, Any]:
    """Load and validate a run artifact from disk."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"run artifact not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"run artifact must be a JSON object: {p}")
    if data.get("artifactKind") != "run":
        raise ValueError(
            f"expected artifactKind=run, got {data.get('artifactKind')!r}: {p}"
        )
    version = data.get("schemaVersion")
    if version not in SUPPORTED_RUN_ARTIFACT_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported run artifact schemaVersion={version}, "
            f"expected one of {sorted(SUPPORTED_RUN_ARTIFACT_SCHEMA_VERSIONS)}: {p}"
        )
    for key in ("product", "executorId", "workload", "commandSamples", "stats"):
        if key not in data:
            raise ValueError(f"run artifact missing required field {key!r}: {p}")
    if version == 1:
        data.setdefault("workloadContract", None)
        workload = data.setdefault("workload", {})
        workload.setdefault("directionalReason", "")
        workload.setdefault("includeByDefault", True)
        workload.setdefault("asyncDiagnosticsMode", "")
        workload.setdefault("strictNormalizationUnit", "")
        workload.setdefault(
            "comparabilityCandidate",
            {"enabled": False, "tier": "", "notes": ""},
        )
        run_parameters = data.setdefault("runParameters", {})
        run_parameters.setdefault("allowNoExecution", False)
        run_parameters.setdefault("timingNormalizationNote", "")
        run_parameters.setdefault("comparabilityMode", "")
        run_parameters.setdefault("requiredTimingClass", "")
    return data


def artifact_filename(product: str, workload_id: str, timestamp: str) -> str:
    """Generate a conventional run artifact filename."""
    return f"{product}-{workload_id}-{timestamp}.run.json"
