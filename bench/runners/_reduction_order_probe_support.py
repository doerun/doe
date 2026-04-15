"""Shared scaffolding for receipted reduction-order probes.

Used by run_reduction_order_counterexample and run_reduction_order_logit_flip.
The per-probe summarization and claim logic is injected via callbacks so
shared argparse, fixture validation, run_lane orchestration, and artifact
emission live in one place.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners.run_determinism_probe import annotate_commands
from bench.runners.run_determinism_probe import build_runtime
from bench.runners.run_determinism_probe import compare_lanes
from bench.runners.run_determinism_probe import load_json
from bench.runners.run_determinism_probe import resolve_repo_path
from bench.runners.run_determinism_probe import run_lane
from bench.runners.run_determinism_probe import sha256_bytes


LaneSummarizer = Callable[
    [str, dict[str, dict[str, Any]], dict[str, Any]],
    dict[str, Any],
]
ClaimBuilder = Callable[[dict[str, Any], dict[str, dict[str, Any]]], dict[str, Any]]
FixtureValidator = Callable[[dict[str, Any]], None]


def build_shared_parser(
    *,
    description: str,
    default_fixture: Path,
    default_output_root: Path,
    fixture_help: str,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--fixture", default=str(default_fixture), help=fixture_help)
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Override repeat count from the fixture.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="UTC timestamp label (default: current UTC time).",
    )
    parser.add_argument(
        "--output-root",
        default=str(default_output_root),
        help="Output root for artifacts.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build doe-zig-runtime before running.",
    )
    return parser


def timestamp_label(raw: str | None) -> str:
    if raw:
        return raw
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


BASE_REQUIRED_FIXTURE_FIELDS = (
    "scenarioId",
    "kernelRoot",
    "profile",
    "backendLanes",
    "defaultRunCount",
    "captures",
    "variants",
)


def ensure_fixture_shape(
    fixture: dict[str, Any],
    *,
    extra_required_fields: tuple[str, ...] = (),
    validate_variants: bool = False,
) -> None:
    required = list(BASE_REQUIRED_FIXTURE_FIELDS) + list(extra_required_fields)
    missing = [field for field in required if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")
    if not fixture["backendLanes"]:
        raise ValueError("fixture must define at least one backend lane")
    if not fixture["captures"]:
        raise ValueError("fixture must define at least one capture")
    if not fixture["variants"]:
        raise ValueError("fixture must define at least one variant")
    if validate_variants:
        for index, variant in enumerate(fixture["variants"]):
            for field in ("id", "policyId", "commandsPath"):
                if not isinstance(variant.get(field), str) or not variant[field]:
                    raise ValueError(
                        f"variants[{index}].{field} must be a non-empty string"
                    )


def run_variant_lanes(
    fixture: dict[str, Any],
    *,
    output_dir: Path,
    kernel_root: Path,
    run_count: int,
) -> dict[str, dict[str, Any]]:
    captures = fixture["captures"]
    variant_reports: dict[str, dict[str, Any]] = {}
    for variant in fixture["variants"]:
        variant_id = variant["id"]
        base_commands_path = resolve_repo_path(variant["commandsPath"])
        base_commands = load_json(base_commands_path)
        if not isinstance(base_commands, list):
            raise SystemExit(f"commands file must contain a list: {base_commands_path}")
        base_commands_sha256 = sha256_bytes(base_commands_path.read_bytes())
        annotated_commands = annotate_commands(
            base_commands,
            captures,
            execution_plan_hash=base_commands_sha256,
        )
        annotated_bytes = (json.dumps(annotated_commands, indent=2) + "\n").encode("utf-8")
        annotated_sha256 = sha256_bytes(annotated_bytes)
        annotated_commands_path = (
            output_dir / f"{fixture['scenarioId']}.{variant_id}.commands.annotated.json"
        )
        annotated_commands_path.write_bytes(annotated_bytes)

        lane_summaries: dict[str, dict[str, Any]] = {}
        for lane in fixture["backendLanes"]:
            lane_summaries[lane["id"]] = run_lane(
                lane_id=lane["id"],
                backend_lane=lane["backendLane"],
                run_count=run_count,
                commands_path=annotated_commands_path,
                output_dir=output_dir / variant_id,
                profile=fixture["profile"],
                kernel_root=kernel_root,
                queue_wait_mode=fixture.get("queueWaitMode", "process-events"),
                queue_sync_mode=fixture.get("queueSyncMode", "per-command"),
                captures=captures,
            )

        variant_reports[variant_id] = {
            "id": variant_id,
            "policyId": variant["policyId"],
            "commandsPath": str(base_commands_path),
            "baseCommandsSha256": base_commands_sha256,
            "annotatedCommandsPath": str(annotated_commands_path),
            "annotatedCommandsSha256": annotated_sha256,
            "lanes": lane_summaries,
            "crossLane": compare_lanes(lane_summaries, captures),
        }
    return variant_reports


def run_probe(
    args: argparse.Namespace,
    *,
    report_filename_suffix: str,
    validate_fixture: FixtureValidator,
    summarize_lane: LaneSummarizer,
    build_claim: ClaimBuilder,
) -> Path:
    if args.build:
        build_runtime()

    fixture_path = resolve_repo_path(args.fixture)
    fixture = load_json(fixture_path)
    validate_fixture(fixture)

    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    kernel_root = resolve_repo_path(fixture["kernelRoot"])
    run_count = args.runs or fixture["defaultRunCount"]

    variant_reports = run_variant_lanes(
        fixture,
        output_dir=output_dir,
        kernel_root=kernel_root,
        run_count=run_count,
    )

    lane_variant_summaries = {
        lane["id"]: summarize_lane(lane["id"], variant_reports, fixture)
        for lane in fixture["backendLanes"]
    }

    report = {
        "schemaVersion": 1,
        "scenarioId": fixture["scenarioId"],
        "description": fixture.get("description"),
        "fixturePath": str(fixture_path),
        "timestamp": stamp,
        "runCount": run_count,
        "profile": fixture["profile"],
        "captures": fixture["captures"],
        "variants": variant_reports,
        "laneVariantSummary": lane_variant_summaries,
        "claim": build_claim(fixture, lane_variant_summaries),
    }

    report_path = output_dir / f"{fixture['scenarioId']}.{report_filename_suffix}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path
