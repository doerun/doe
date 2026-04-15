"""apply_config_defaults: expand compare config values into argparse namespace.

Extracted from config_support.py to keep both files under the 1200-line cap.
Depends on the DEFAULT_* constants and coerce helpers that remain in
config_support.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from native_compare_modules.config_support import (
    DEFAULT_BASELINE_COMMAND_TEMPLATE,
    DEFAULT_BASELINE_EXECUTOR_ID,
    DEFAULT_BASELINE_NAME,
    DEFAULT_BENCHMARK_POLICY_PATH,
    DEFAULT_CLAIM_MIN_TIMED_SAMPLES,
    DEFAULT_CLAIMABILITY_MODE,
    DEFAULT_COMPARABILITY_MODE,
    DEFAULT_COMPARISON_EXECUTOR_ID,
    DEFAULT_COMPARISON_NAME,
    DEFAULT_ITERATIONS,
    DEFAULT_OUT_PATH,
    DEFAULT_REQUIRED_TIMING_CLASS,
    DEFAULT_RESOURCE_PROBE,
    DEFAULT_RESOURCE_SAMPLE_MS,
    DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT,
    DEFAULT_WARMUP,
    DEFAULT_WORKLOAD_COHORT,
    DEFAULT_WORKLOAD_COOLDOWN_MS,
    DEFAULT_WORKLOAD_FILTER,
    DEFAULT_WORKLOADS_PATH,
    DEFAULT_WORKSPACE_PATH,
    VALID_CLAIMABILITY_MODES,
    VALID_COMPARABILITY_MODES,
    VALID_REQUIRED_TIMING_CLASSES,
    VALID_RESOURCE_PROBES,
    VALID_WORKLOAD_COHORTS,
    as_bool,
    as_int,
    as_str,
    first_config_value,
    load_json,
)


def apply_config_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if not args.config:
        return args

    cli_args = set(sys.argv[1:])

    config_path = Path(args.config)
    payload = load_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid config: expected top-level object in {config_path}")

    if args.workloads == DEFAULT_WORKLOADS_PATH:
        value = first_config_value(payload, ["workloads"])
        if value is not None:
            args.workloads = as_str(value, field="workloads")

    if not args.boundary:
        value = first_config_value(payload, ["comparison.boundary", "comparisonAxes.boundary"])
        if value is not None:
            args.boundary = as_str(value, field="comparison.boundary")
    if not args.runtime_host:
        value = first_config_value(
            payload,
            ["comparison.runtimeHost", "comparisonAxes.runtimeHost"],
        )
        if value is not None:
            args.runtime_host = as_str(value, field="comparison.runtimeHost")
    if not args.temperature:
        value = first_config_value(
            payload,
            ["comparison.temperature", "comparisonAxes.temperature"],
        )
        if value is not None:
            args.temperature = as_str(value, field="comparison.temperature")
    if not args.comparison_view:
        value = first_config_value(
            payload,
            ["comparison.view", "comparison.comparisonView", "comparisonAxes.comparisonView"],
        )
        if value is not None:
            args.comparison_view = as_str(value, field="comparison.view")
    if not args.provider_set:
        value = first_config_value(
            payload,
            ["comparison.providerSet", "comparisonAxes.providerSet"],
        )
        if value is not None:
            args.provider_set = as_str(value, field="comparison.providerSet")
    if not args.baseline_provider_id:
        value = first_config_value(
            payload,
            ["comparison.baselineProviderId", "comparison.participants.baseline.id"],
        )
        if value is not None:
            args.baseline_provider_id = as_str(value, field="comparison.baselineProviderId")
    if not args.comparison_provider_id:
        value = first_config_value(
            payload,
            [
                "comparison.comparisonProviderId",
                "comparison.participants.comparison.id",
            ],
        )
        if value is not None:
            args.comparison_provider_id = as_str(value, field="comparison.comparisonProviderId")

    if args.baseline_name == DEFAULT_BASELINE_NAME:
        value = first_config_value(payload, ["baseline.name", "baselineName"])
        if value is not None:
            args.baseline_name = as_str(value, field="baseline.name")
    if args.baseline_executor_id == DEFAULT_BASELINE_EXECUTOR_ID:
        value = first_config_value(payload, ["baseline.executorId", "baselineExecutorId"])
        if value is not None:
            args.baseline_executor_id = as_str(value, field="baseline.executorId")
    if args.comparison_name == DEFAULT_COMPARISON_NAME:
        value = first_config_value(payload, ["comparison.name", "comparisonName"])
        if value is not None:
            args.comparison_name = as_str(value, field="comparison.name")
    if args.comparison_executor_id == DEFAULT_COMPARISON_EXECUTOR_ID:
        value = first_config_value(payload, ["comparison.executorId", "comparisonExecutorId"])
        if value is not None:
            args.comparison_executor_id = as_str(value, field="comparison.executorId")

    if args.baseline_command_template == DEFAULT_BASELINE_COMMAND_TEMPLATE:
        value = first_config_value(
            payload,
            ["baseline.commandTemplate", "baselineCommandTemplate"],
        )
        if value is not None:
            args.baseline_command_template = as_str(
                value,
                field="baseline.commandTemplate",
            )
    if args.comparison_command_template == "":
        value = first_config_value(
            payload,
            ["comparison.commandTemplate", "comparisonCommandTemplate"],
        )
        if value is not None:
            args.comparison_command_template = as_str(
                value,
                field="comparison.commandTemplate",
            )

    if args.iterations == DEFAULT_ITERATIONS:
        value = first_config_value(payload, ["run.iterations", "iterations"])
        if value is not None:
            args.iterations = as_int(value, field="run.iterations")
    if args.warmup == DEFAULT_WARMUP:
        value = first_config_value(payload, ["run.warmup", "warmup"])
        if value is not None:
            args.warmup = as_int(value, field="run.warmup")
    if args.out == DEFAULT_OUT_PATH:
        value = first_config_value(payload, ["run.out", "out"])
        if value is not None:
            args.out = as_str(value, field="run.out")
    if args.workspace == DEFAULT_WORKSPACE_PATH:
        value = first_config_value(payload, ["run.workspace", "workspace"])
        if value is not None:
            args.workspace = as_str(value, field="run.workspace")
    if args.workload_filter == DEFAULT_WORKLOAD_FILTER:
        value = first_config_value(payload, ["run.workloadFilter", "workloadFilter"])
        if value is not None:
            args.workload_filter = as_str(value, field="run.workloadFilter")
    if args.workload_cohort == DEFAULT_WORKLOAD_COHORT:
        value = first_config_value(payload, ["run.workloadCohort", "workloadCohort"])
        if value is not None:
            candidate = as_str(value, field="run.workloadCohort")
            if candidate not in VALID_WORKLOAD_COHORTS:
                raise ValueError(
                    "invalid config run.workloadCohort="
                    f"{candidate}, expected one of {sorted(VALID_WORKLOAD_COHORTS)}"
                )
            args.workload_cohort = candidate

    if args.include_extended_workloads is False:
        value = first_config_value(
            payload,
            ["run.includeExtendedWorkloads", "includeExtendedWorkloads"],
        )
        if value is not None:
            args.include_extended_workloads = as_bool(
                value,
                field="run.includeExtendedWorkloads",
            )
    if args.include_noncomparable_workloads is False:
        value = first_config_value(
            payload,
            ["run.includeNoncomparableWorkloads", "includeNoncomparableWorkloads"],
        )
        if value is not None:
            args.include_noncomparable_workloads = as_bool(
                value,
                field="run.includeNoncomparableWorkloads",
            )

    if args.comparability == DEFAULT_COMPARABILITY_MODE:
        value = first_config_value(payload, ["comparability.mode", "comparabilityMode"])
        if value is not None:
            candidate = as_str(value, field="comparability.mode")
            if candidate not in VALID_COMPARABILITY_MODES:
                raise ValueError(
                    f"invalid config comparability.mode={candidate}, expected one of {sorted(VALID_COMPARABILITY_MODES)}"
                )
            args.comparability = candidate
    if args.require_timing_class == DEFAULT_REQUIRED_TIMING_CLASS:
        value = first_config_value(
            payload,
            ["comparability.requireTimingClass", "requireTimingClass"],
        )
        if value is not None:
            candidate = as_str(value, field="comparability.requireTimingClass")
            if candidate not in VALID_REQUIRED_TIMING_CLASSES:
                raise ValueError(
                    "invalid config comparability.requireTimingClass="
                    f"{candidate}, expected one of {sorted(VALID_REQUIRED_TIMING_CLASSES)}"
                )
            args.require_timing_class = candidate
    if args.allow_baseline_no_execution is False:
        value = first_config_value(
            payload,
            ["comparability.allowBaselineNoExecution", "allowBaselineNoExecution"],
        )
        if value is not None:
            args.allow_baseline_no_execution = as_bool(
                value,
                field="comparability.allowBaselineNoExecution",
            )

    if args.resource_probe == DEFAULT_RESOURCE_PROBE:
        value = first_config_value(payload, ["resource.probe", "resourceProbe"])
        if value is not None:
            candidate = as_str(value, field="resource.probe")
            if candidate not in VALID_RESOURCE_PROBES:
                raise ValueError(
                    f"invalid config resource.probe={candidate}, expected one of {sorted(VALID_RESOURCE_PROBES)}"
                )
            args.resource_probe = candidate
    if args.resource_sample_ms == DEFAULT_RESOURCE_SAMPLE_MS:
        value = first_config_value(payload, ["resource.sampleMs", "resourceSampleMs"])
        if value is not None:
            args.resource_sample_ms = as_int(value, field="resource.sampleMs")
    if args.resource_sample_target_count == DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT:
        value = first_config_value(
            payload,
            ["resource.sampleTargetCount", "resourceSampleTargetCount"],
        )
        if value is not None:
            args.resource_sample_target_count = as_int(
                value,
                field="resource.sampleTargetCount",
            )
    if args.workload_cooldown_ms == DEFAULT_WORKLOAD_COOLDOWN_MS:
        value = first_config_value(
            payload,
            ["run.workloadCooldownMs", "workloadCooldownMs"],
        )
        if value is not None:
            args.workload_cooldown_ms = as_int(
                value,
                field="run.workloadCooldownMs",
            )
    if args.claimability == DEFAULT_CLAIMABILITY_MODE and "--claimability" not in cli_args:
        value = first_config_value(
            payload,
            ["claimability.mode", "claimabilityMode"],
        )
        if value is not None:
            candidate = as_str(value, field="claimability.mode")
            if candidate not in VALID_CLAIMABILITY_MODES:
                raise ValueError(
                    f"invalid config claimability.mode={candidate}, expected one of {sorted(VALID_CLAIMABILITY_MODES)}"
                )
            args.claimability = candidate
    if args.claim_min_timed_samples == DEFAULT_CLAIM_MIN_TIMED_SAMPLES:
        value = first_config_value(
            payload,
            ["claimability.minTimedSamples", "claimMinTimedSamples"],
        )
        if value is not None:
            args.claim_min_timed_samples = as_int(
                value,
                field="claimability.minTimedSamples",
            )
    if args.benchmark_policy == DEFAULT_BENCHMARK_POLICY_PATH:
        value = first_config_value(
            payload,
            ["benchmarkPolicy.path", "benchmarkPolicyPath"],
        )
        if value is not None:
            args.benchmark_policy = as_str(value, field="benchmarkPolicy.path")

    if args.emit_shell is False:
        value = first_config_value(payload, ["run.emitShell", "emitShell"])
        if value is not None:
            args.emit_shell = as_bool(value, field="run.emitShell")

    if not getattr(args, "selector", None):
        value = first_config_value(payload, ["selector"])
        if isinstance(value, dict):
            args.selector = value

    return args


