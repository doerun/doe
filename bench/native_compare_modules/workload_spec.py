"""Product-neutral workload spec and per-product run config.

These dataclasses decouple workload identity from product-specific execution
parameters, enabling independent product runs and post-hoc comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkloadSpec:
    """Product-neutral workload definition."""

    id: str
    name: str
    description: str
    domain: str
    commands_path: str
    quirks_path: str
    vendor: str
    api: str
    family: str
    driver: str
    extra_args: list[str]
    comparable: bool
    benchmark_class: str
    comparability_notes: str
    directional_reason: str
    path_asymmetry: bool
    path_asymmetry_note: str
    strict_normalization_unit: str
    include_by_default: bool = True
    comparability_candidate_enabled: bool = False
    comparability_candidate_tier: str = ""
    comparability_candidate_notes: str = ""
    cohorts: list[str] = field(default_factory=lambda: ["exploration"])
    claim_eligible: bool = True
    runner_type: str = "zig-runtime"
    ir_path: str = ""
    plan_path: str = ""
    shader_path: str = ""
    compilation_target: str = ""
    async_diagnostics_mode: str = ""


@dataclass(frozen=True)
class ProductRunConfig:
    """Per-product execution parameters for a workload."""

    product: str
    command_repeat: int = 1
    ignore_first_ops: int = 0
    upload_buffer_usage: str = "copy-dst-copy-src"
    upload_submit_every: int = 1
    timing_divisor: float = 1.0
    allow_no_execution: bool = False
    dawn_filter: str = ""
    timing_normalization_note: str = ""
