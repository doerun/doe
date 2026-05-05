#!/usr/bin/env python3
"""Run a Doppler-to-CSL Gemma 4 31B af16 splice attempt."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "bench/runners/csl-runners"
for entry in (REPO_ROOT, RUNNER_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from bench.tools.build_doppler_to_csl_splice_receipt import (  # noqa: E402
    build_receipt,
    validate_schema,
    write_json,
)
from bench.tools._receipt_hash_guard import enforce_receipt_hash_spine  # noqa: E402
from gemma4_31b_af16_hostplan_streaming_runner import (  # noqa: E402
    DEFAULT_COMPILE_ROOT,
    DEFAULT_HOST_PLAN,
    DEFAULT_RUNTIME_CONFIG,
    DEFAULT_SIMULATOR_PLAN,
    DEFAULT_SMOKE_CONFIG,
    DEFAULT_SOURCE_MANIFEST,
    LANE_KEY,
    MODEL_ID,
    build_dispatch_plan,
    build_weight_staging_plan,
    load_json,
    rel,
    resolve,
)
from gemma4_31b_af16_session_runtime import (  # noqa: E402
    build_real_session_scheduler,
    build_reference_request,
    build_runtime_weight_mappings,
    normalize_smoke_execution,
)
from int4ple_compile_target_sim_runner import (  # noqa: E402
    execute_hostplan_runtime,
    execute_hostplan_runtime_bootstrap,
)
from int4ple_hostplan_execution_plan import build_hostplan_execution_plan  # noqa: E402
from int4ple_hostplan_executor_validator import validate_hostplan_executor  # noqa: E402


DEFAULT_FIXTURE_ROOT = REPO_ROOT / "bench/fixtures/r3-1-31b-doppler-frozen-af16"
DEFAULT_OUT_DIR = REPO_ROOT / "bench/out/r3-1-31b-af16-doppler-csl-splice"
DEFAULT_REFERENCE_EXPORT = (
    REPO_ROOT
    / "bench/out/doppler-reference/"
    "gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/"
    "doppler_int4ple_reference_export.json"
)
DEFAULT_SPLICE_LAUNCH_BOUND = 240


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["single_block_hidden", "last_layer_tail_token"], default="single_block_hidden")
    parser.add_argument("--layer-index", type=int, default=59)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--source-doppler-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--smoke-config", type=Path, default=DEFAULT_SMOKE_CONFIG)
    parser.add_argument("--host-plan", type=Path, default=DEFAULT_HOST_PLAN)
    parser.add_argument("--simulator-plan", type=Path, default=DEFAULT_SIMULATOR_PLAN)
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--compile-root", type=Path, default=DEFAULT_COMPILE_ROOT)
    parser.add_argument("--reference-export", type=Path, default=DEFAULT_REFERENCE_EXPORT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--execute", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--cmaddr", default="")
    parser.add_argument(
        "--launch-timeout-seconds",
        type=int,
        default=DEFAULT_SPLICE_LAUNCH_BOUND,
    )
    parser.add_argument("--q4k-output-pe-rows", type=int, default=4)
    parser.add_argument("--q4k-tile-dispatch-budget", type=int, default=0)
    parser.add_argument("--atol", type=float, default=2e-2)
    parser.add_argument("--rtol", type=float, default=2e-2)
    return parser.parse_args()


def fixture_tensor_path(
    *,
    fixture_root: Path,
    fixture_manifest: dict[str, Any],
    layer_index: int,
    probe: str,
) -> Path:
    layer = (fixture_manifest.get("activations") or {}).get(str(layer_index))
    if not isinstance(layer, dict):
        raise ValueError(f"fixture_layer_absent:{layer_index}")
    spec = layer.get(probe)
    if not isinstance(spec, dict):
        raise ValueError(f"fixture_probe_absent:{layer_index}:{probe}")
    path = fixture_root / str(spec.get("path") or "")
    if not path.is_file():
        raise ValueError(f"fixture_tensor_missing:{path}")
    return path


def prompt_token_count(reference_report: dict[str, Any]) -> int:
    metrics = reference_report.get("metrics") or {}
    value = metrics.get("prefillTokens")
    if isinstance(value, int) and value > 0:
        return value
    raise ValueError("reference_prefill_token_count_missing")


def select_prefill_steps(
    *,
    dispatch_plan: dict[str, Any],
    layer_index: int,
    kind: str,
) -> list[dict[str, Any]]:
    selected = [
        step for step in dispatch_plan.get("prefillSteps") or []
        if isinstance(step, dict) and step.get("layer") == layer_index
    ]
    if not selected:
        raise ValueError(f"layer_steps_absent:{layer_index}")
    if kind == "last_layer_tail_token":
        selected.extend(
            step for step in dispatch_plan.get("prefillSteps") or []
            if isinstance(step, dict)
            and step.get("layer") is None
            and str(step.get("name") or "") in {
                "final_norm_prefill",
                "lm_head_prefill",
                "sample_prefill",
            }
        )
    return selected


def receipt_args(
    *,
    args: argparse.Namespace,
    reference_export: Path,
    csl_output_tensor: Path | None,
    csl_output_token_id: int | None,
    csl_command: str,
    receipt_out: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        kind=args.kind,
        layer_index=args.layer_index,
        model_id=MODEL_ID,
        manifest=resolve(args.source_doppler_manifest),
        reference_export=reference_export,
        frozen_fixture_root=resolve(args.fixture_root),
        input_probe="pre_layer_input",
        expected_probe="post_ffn",
        csl_output_tensor=csl_output_tensor,
        csl_output_token_id=csl_output_token_id,
        csl_command=csl_command,
        allow_blocked=True,
        out=receipt_out,
        atol=args.atol,
        rtol=args.rtol,
    )


def write_splice_receipt(
    *,
    args: argparse.Namespace,
    reference_export: Path,
    csl_output_tensor: Path | None,
    csl_output_token_id: int | None,
    csl_command: str,
    receipt_out: Path,
) -> dict[str, Any]:
    receipt = build_receipt(
        receipt_args(
            args=args,
            reference_export=reference_export,
            csl_output_tensor=csl_output_tensor,
            csl_output_token_id=csl_output_token_id,
            csl_command=csl_command,
            receipt_out=receipt_out,
        )
    )
    enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    validate_schema(receipt)
    write_json(receipt_out, receipt)
    return receipt


def runtime_blocker(runtime: dict[str, Any]) -> str:
    blockers = [
        str(item)
        for item in runtime.get("blockers") or []
        if isinstance(item, str) and item
    ]
    return blockers[0] if blockers else "runtime_not_succeeded"


def blocked_launch_summary(session_dir: Path) -> dict[str, Any] | None:
    receipt_dir = session_dir / "hostplan-runtime" / "launch-receipts"
    if not receipt_dir.is_dir():
        return None
    for path in sorted(receipt_dir.glob("launch-*.json")):
        receipt = load_json(path)
        if receipt.get("status") != "blocked":
            continue
        tile_dispatches = [
            item
            for item in receipt.get("tileDispatches") or []
            if isinstance(item, dict)
        ]
        first_blocked_tile = next(
            (
                item
                for item in tile_dispatches
                if item.get("timedOut")
                or str(item.get("outputStatus") or "") not in {"", "ready"}
                or int(item.get("exitCode") or 0) != 0
            ),
            None,
        )
        batch_runtime = receipt.get("batchRuntime") or {}
        tile_coverage = receipt.get("tileCoverage") or {}
        return {
            "path": rel(path),
            "status": receipt.get("status"),
            "blockers": receipt.get("blockers") or [],
            "launchIndex": receipt.get("launchIndex"),
            "targetName": receipt.get("targetName"),
            "kernelPattern": receipt.get("kernelPattern"),
            "compileIdentity": receipt.get("compileIdentity"),
            "tileCoverage": {
                key: tile_coverage.get(key)
                for key in (
                    "rows",
                    "sourceCols",
                    "outputCols",
                    "outputReadElements",
                    "outputReadDtype",
                    "tileCount",
                    "batchStepCount",
                    "d2hElementCountLimit",
                )
            },
            "batchRuntime": {
                key: batch_runtime.get(key)
                for key in (
                    "timedOut",
                    "exitCode",
                    "pendingStepCount",
                    "shardCount",
                    "adapterStepBudget",
                    "splitD2HRows",
                )
            },
            "firstBlockedTile": first_blocked_tile,
        }
    return None


def main() -> int:
    args = parse_args()
    fixture_root = resolve(args.fixture_root)
    out_dir = resolve(args.out_dir)
    session_dir = out_dir / f"session-{args.kind}"
    if session_dir.exists():
        shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    fixture_manifest_path = fixture_root / "frozen-reference.manifest.json"
    fixture_manifest = load_json(fixture_manifest_path)
    reference_report_path = fixture_root / "reference-report.json"
    reference_report = load_json(reference_report_path)
    input_tensor = fixture_tensor_path(
        fixture_root=fixture_root,
        fixture_manifest=fixture_manifest,
        layer_index=args.layer_index,
        probe="pre_layer_input",
    )
    prefill_count = prompt_token_count(reference_report)

    weight_plan = build_weight_staging_plan(
        manifest_path=args.source_doppler_manifest,
        smoke_config_path=args.smoke_config,
        expected_model_id=MODEL_ID,
        lane_key=LANE_KEY,
    )
    full_dispatch = build_dispatch_plan(
        smoke_config_path=args.smoke_config,
        host_plan_path=args.host_plan,
        prefill_token_count=prefill_count,
        decode_token_count=1 if args.kind == "last_layer_tail_token" else 0,
        model_layer_count=int(weight_plan.get("modelLayerCount") or 0),
        linear_attention_layers=list(weight_plan.get("linearAttentionLayers") or []),
        self_attention_layers=list(weight_plan.get("selfAttentionLayers") or []),
    )
    dispatch_plan = {
        **full_dispatch,
        "kind": "doppler_csl_splice_dispatch_plan",
        "prefillStepCount": 0,
        "decodeStepCount": 0,
        "prefillSteps": select_prefill_steps(
            dispatch_plan=full_dispatch,
            layer_index=args.layer_index,
            kind=args.kind,
        ),
        "decodeByToken": [],
        "splice": {
            "layerIndex": args.layer_index,
            "inputTensor": rel(input_tensor),
            "kind": args.kind,
        },
    }
    dispatch_plan["prefillStepCount"] = len(dispatch_plan["prefillSteps"])

    runtime_config = load_json(args.runtime_config)
    runtime_config["mode"] = "sdk-runtime-command"
    runtime_config["modelConfig"] = {
        **(runtime_config.get("modelConfig") or {}),
        "numLayers": int(weight_plan.get("modelLayerCount") or 0),
    }
    state_buffers = runtime_config.setdefault("stateBuffers", [])
    existing_state_names = {
        str(item.get("name") or "")
        for item in state_buffers
        if isinstance(item, dict)
    }
    for name, role in (
        ("linear_attention", "linear_attention_state"),
        ("sliding_window", "position"),
    ):
        if name not in existing_state_names:
            state_buffers.append({"name": name, "role": role})
    mappings = build_runtime_weight_mappings(
        manifest_path=args.source_doppler_manifest,
        weight_plan=weight_plan,
        runtime_config=runtime_config,
    )
    runtime_config["weightMappings"] = mappings["mappings"]
    runtime_config["weightIdentity"] = mappings["identity"]
    runner_args = argparse.Namespace(
        source_doppler_manifest=args.source_doppler_manifest,
        expected_model_id=MODEL_ID,
        session_artifact_prefix="gemma4_31b_af16_doppler_csl_splice",
        prefill_token_count=prefill_count,
        decode_token_count=1 if args.kind == "last_layer_tail_token" else 0,
        prompt_token_id=[],
    )
    normalized = normalize_smoke_execution(
        smoke_config_path=args.smoke_config,
        out_dir=session_dir,
        model_layer_count=int(weight_plan.get("modelLayerCount") or 0),
    )
    reference = build_reference_request(args=runner_args, session_dir=session_dir)
    initial_buffer = f"input:doppler:layer{args.layer_index}:pre_layer_input"
    scheduler = build_real_session_scheduler(
        dispatch_plan=dispatch_plan,
        runtime_config=runtime_config,
        architecture_disabled_weight_keys=[
            str(item)
            for item in weight_plan.get("architectureDisabledWeightKeys") or []
        ],
        per_layer_input_block_enabled=bool(
            (weight_plan.get("perLayerInputBlock") or {}).get("enabled", True)
        ),
        initial_activation_buffer=initial_buffer,
    )
    scheduler_record = {
        "path": str(args.host_plan),
        "present": True,
        "runtimeScheduler": scheduler,
        "launchesCarrySymbolDataflow": bool(scheduler.get("launches")),
    }
    manifest_preflight = {
        "status": "passed",
        "blockers": [],
        "source": "gemma4_31b_af16_doppler_csl_splice",
    }
    plan = load_json(args.simulator_plan)
    validator = validate_hostplan_executor(
        plan=plan,
        compile_root=resolve(args.compile_root),
        runtime_config=runtime_config,
        scheduler={"hostPlan": scheduler_record},
        manifest_preflight=manifest_preflight,
    )
    execution_plan = build_hostplan_execution_plan(
        plan=plan,
        compile_root=resolve(args.compile_root),
        runtime_config=runtime_config,
        scheduler={"hostPlan": scheduler_record},
        executor_validator=validator,
    )

    runtime_config_path = session_dir / "runtime-config.json"
    scheduler_path = session_dir / "runtime-scheduler.json"
    dispatch_path = session_dir / "dispatch-plan.json"
    execution_plan_path = session_dir / "hostplan-execution-plan.json"
    write_json(runtime_config_path, runtime_config)
    write_json(scheduler_path, scheduler)
    write_json(dispatch_path, dispatch_plan)
    write_json(execution_plan_path, execution_plan)

    run_receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_doppler_csl_splice_run",
        "modelId": MODEL_ID,
        "kind": args.kind,
        "layerIndex": args.layer_index,
        "promptText": fixture_manifest.get("promptText"),
        "prefillTokenCount": prefill_count,
        "inputTensor": rel(input_tensor),
        "fixtureManifest": rel(fixture_manifest_path),
        "normalizedExecution": normalized,
        "runtimeConfigPath": rel(runtime_config_path),
        "runtimeSchedulerPath": rel(scheduler_path),
        "executionPlanPath": rel(execution_plan_path),
        "schedulerStatus": scheduler.get("status"),
        "schedulerBlockers": scheduler.get("blockers") or [],
        "executorValidatorStatus": validator.get("status"),
        "executorValidatorBlockers": validator.get("blockers") or [],
        "executionPlanStatus": execution_plan.get("status"),
        "executionPlanBlockers": execution_plan.get("blockers") or [],
        "requestedExecution": bool(args.execute),
    }
    csl_output_tensor: Path | None = None
    csl_output_token_id: int | None = None
    blocker: str | None = None

    if (
        scheduler.get("status") != "bound"
        or validator.get("status") != "passed"
        or execution_plan.get("status") != "planned"
    ):
        blocker = "splice_plan_not_executable"
    elif args.execute:
        progress_path = session_dir / "progress.jsonl"
        bootstrap = execute_hostplan_runtime_bootstrap(
            execution_plan=execution_plan,
            progress_path=progress_path,
            cmaddr=args.cmaddr.strip() or None,
        )
        run_receipt["bootstrap"] = bootstrap
        if bootstrap.get("status") != "ready_for_tensor_movement":
            blocker = "bootstrap_not_ready"
        else:
            launch_timeout = int(args.launch_timeout_seconds)
            runtime = execute_hostplan_runtime(
                bootstrap=bootstrap,
                export=reference,
                progress_path=progress_path,
                cmaddr=args.cmaddr.strip() or None,
                trace_path=session_dir / "trace.json",
                initial_buffer_files={initial_buffer: input_tensor},
                launch_timeout_seconds=(
                    launch_timeout if launch_timeout > 0 else None
                ),
                session_ple_proj_dispatch_mode="compact_summa_session",
                session_attention_prefill_dispatch_mode="compact_width_session",
                session_prefill_q4k_gemv_jobs=1,
                session_prefill_q4k_gemv_output_pe_rows=max(
                    1,
                    int(args.q4k_output_pe_rows),
                ),
                session_prefill_q4k_gemv_adapter_step_budget=1,
                session_prefill_q4k_gemv_tile_dispatch_budget=max(
                    0,
                    int(args.q4k_tile_dispatch_budget),
                ),
            )
            run_receipt["runtime"] = runtime
            if runtime.get("status") != "succeeded":
                blocker = runtime_blocker(runtime)
                launch_summary = blocked_launch_summary(session_dir)
                if launch_summary:
                    run_receipt["blockedLaunch"] = launch_summary
            else:
                last = (runtime.get("launches") or [])[-1]
                output = last.get("output") or {}
                if output.get("path"):
                    csl_output_tensor = Path(str(output["path"]))
                    run_receipt["cslOutputTensor"] = {
                        "path": rel(csl_output_tensor),
                        "sha256": output.get("sha256"),
                        "dtype": output.get("dtype"),
                        "shape": output.get("shape"),
                    }
                else:
                    blocker = "csl_output_tensor_missing"
    else:
        blocker = "execution_not_requested"

    receipt_name = (
        "last-layer-tail-token.json"
        if args.kind == "last_layer_tail_token"
        else "single-block-hidden.json"
    )
    splice_receipt_path = out_dir / receipt_name
    splice_receipt = write_splice_receipt(
        args=args,
        reference_export=resolve(args.reference_export),
        csl_output_tensor=csl_output_tensor,
        csl_output_token_id=csl_output_token_id,
        csl_command=" ".join(sys.argv),
        receipt_out=splice_receipt_path,
    )
    run_receipt["spliceReceipt"] = {
        "path": rel(splice_receipt_path),
        "verdict": splice_receipt.get("verdict"),
        "blocker": splice_receipt.get("blocker"),
    }
    run_receipt["status"] = (
        "succeeded"
        if blocker is None and splice_receipt.get("verdict") == "bound"
        else "blocked"
    )
    run_receipt["blocker"] = blocker or splice_receipt.get("blocker")
    run_receipt_path = out_dir / f"{args.kind}-run.json"
    write_json(run_receipt_path, run_receipt)
    print(
        f"wrote {rel(run_receipt_path)} "
        f"(status={run_receipt['status']}, blocker={run_receipt['blocker']})"
    )
    print(
        f"wrote {rel(splice_receipt_path)} "
        f"(verdict={splice_receipt['verdict']}, blocker={splice_receipt['blocker']})"
    )
    if run_receipt["status"] == "succeeded" or args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
