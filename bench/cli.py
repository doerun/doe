"""Doe benchmark CLI.

Product-based benchmark runner with isolated runs and post-hoc compare reports.

Usage:
    python3 bench/cli.py run     --product doe --executor-id doe_direct_vulkan ...
    python3 bench/cli.py compare <artifact1.run.json> <artifact2.run.json> ...
    python3 bench/cli.py list    --products | --executors | --workloads FILE
"""

from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = Path(__file__).resolve().parent


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_bench_imports() -> None:
    for path in (str(REPO_ROOT), str(BENCH_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)


# ---------------------------------------------------------------------------
# run subcommand
# ---------------------------------------------------------------------------


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product", required=True, help="Product identifier (doe, dawn, tint, ...)")
    parser.add_argument("--executor-id", required=True, help="Executor registry ID")
    parser.add_argument("--workloads", required=True, help="Workload contract JSON path")
    parser.add_argument("--workload-id", default="", help="Single workload ID (omit for all)")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--command-repeat", type=int, default=0, help="Override per-workload commandRepeat (0=use workload default)")
    parser.add_argument("--ignore-first-ops", type=int, default=0)
    parser.add_argument("--timing-divisor", type=float, default=0.0, help="Override per-workload timingDivisor (0=use workload default)")
    parser.add_argument("--upload-buffer-usage", default="", help="Override per-workload uploadBufferUsage")
    parser.add_argument("--upload-submit-every", type=int, default=0, help="Override per-workload uploadSubmitEvery (0=use workload default)")
    parser.add_argument("--resource-probe", default="none", choices=["none", "rocm-smi"])
    parser.add_argument("--resource-sample-ms", type=int, default=100)
    parser.add_argument("--resource-sample-target-count", type=int, default=0)
    parser.add_argument("--comparability-mode", default="strict", choices=["strict", "warn", "off"])
    parser.add_argument("--require-timing-class", default="operation", choices=["any", "operation", "process-wall"])
    parser.add_argument("--benchmark-policy", default="", help="Benchmark methodology policy path")
    parser.add_argument("--cohort", default="all", help="Workload cohort filter")
    parser.add_argument("--benchmark-class", default="", help="Filter by benchmarkClass (comparable, directional)")
    parser.add_argument("--out", default="bench/out/runs", help="Output directory for run artifacts")


def _cmd_run(args: argparse.Namespace) -> int:
    _ensure_bench_imports()
    from native_compare_modules.artifact_benchmarking import run_product_bundle
    from native_compare_modules.config_support import (
        load_benchmark_methodology_policy,
        load_workloads,
    )
    from native_compare_modules.executor_registry import resolve_executor_command_template

    template = resolve_executor_command_template(args.executor_id)
    benchmark_policy = load_benchmark_methodology_policy(args.benchmark_policy)
    workloads_path = Path(args.workloads)
    workloads = load_workloads(
        workloads_path,
        workload_filter=args.workload_id,
        include_noncomparable=True,
        include_extended=True,
        workload_cohort=args.cohort,
    )
    if not workloads:
        print(f"error: no workloads matched", file=sys.stderr)
        return 1

    timestamp = _utc_timestamp()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = run_product_bundle(
        product=args.product,
        display_name=args.product,
        executor_id=args.executor_id,
        template=template,
        workloads=workloads,
        iterations=args.iterations,
        warmup=args.warmup,
        workspace=out_dir,
        workload_contract_path=workloads_path,
        gpu_memory_probe=args.resource_probe,
        resource_sample_ms=args.resource_sample_ms,
        resource_sample_target_count=args.resource_sample_target_count,
        required_timing_class=args.require_timing_class,
        comparability_mode=args.comparability_mode,
        benchmark_policy=benchmark_policy,
        benchmark_policy_path=args.benchmark_policy,
        workload_cooldown_ms=0,
        emit_shell=False,
        timestamp=timestamp,
        command_repeat_override=args.command_repeat,
        ignore_first_ops_override=args.ignore_first_ops,
        timing_divisor_override=args.timing_divisor,
        upload_buffer_usage_override=args.upload_buffer_usage,
        upload_submit_every_override=args.upload_submit_every,
    )
    for artifact_path in written:
        print(f"  {artifact_path}")

    print(f"\n{len(written)} run artifact(s) written under {out_dir}/")
    return 0


# ---------------------------------------------------------------------------
# compare subcommand
# ---------------------------------------------------------------------------


def _add_compare_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("artifacts", nargs="*", help="Run artifact JSON paths")
    parser.add_argument("--config", default="", help="Config-backed compare JSON path")
    parser.add_argument("--catalog", default="config/promoted-compare-catalog.json", help="Promoted compare catalog path")
    parser.add_argument("--profile", default="", help="Exact promoted compare profile id")
    parser.add_argument("--backend", default="", help="Promoted backend id, e.g. apple-metal")
    parser.add_argument("--boundary", default="", choices=["backend_native", "direct_plan", "package_surface"], help="Execution boundary for promoted compare resolution")
    parser.add_argument("--surface", default="", choices=["backend", "plan", "package"], help="Promoted surface selector")
    parser.add_argument("--preset", default="", help="Promoted preset for backend surfaces")
    parser.add_argument("--workload", default="", help="Promoted workload alias")
    parser.add_argument("--runtime-host", default="", choices=["none", "node", "bun", "deno"], help="Promoted runtime host selector")
    parser.add_argument("--package-runtime", default="", choices=["node", "bun", "deno"], help="Promoted package runtime selector")
    parser.add_argument("--temperature", default="", choices=["default", "cold", "warm"], help="Promoted temperature selector")
    parser.add_argument("--mode", default="", choices=["default", "cold", "warm"], help="Temperature alias for promoted compare resolution")
    parser.add_argument("--list-promoted", action="store_true", help="List promoted compare profiles and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved compare command and exit")
    parser.add_argument("--products", default="", help="Comma-separated product pair for inline run + compare report (e.g. doe,dawn)")
    parser.add_argument("--executor-ids", default="", help="Comma-separated executor IDs matching --products")
    parser.add_argument("--workloads", default="", help="Workload contract JSON for inline run + compare report")
    parser.add_argument("--workload-id", default="", help="Single workload ID filter")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--comparability", default="strict", choices=["strict", "warn", "off"])
    parser.add_argument("--require-timing-class", default="operation", choices=["any", "operation", "process-wall"])
    parser.add_argument("--claimability", default="off", choices=["off", "local", "release"])
    parser.add_argument("--claim-min-timed-samples", type=int, default=0)
    parser.add_argument("--resource-probe", default="none", choices=["none", "rocm-smi"])
    parser.add_argument("--resource-sample-ms", type=int, default=100)
    parser.add_argument("--resource-sample-target-count", type=int, default=0)
    parser.add_argument("--benchmark-policy", default="", help="Benchmark methodology policy path")
    parser.add_argument("--baseline-product", default="", help="Explicit baseline product id")
    parser.add_argument("--comparison-product", default="", help="Explicit comparison product id")
    parser.add_argument("--workspace", default="", help="Workspace path override for config-backed compare")
    parser.add_argument("--workload-filter", default="", help="Config-backed workload filter override")
    parser.add_argument("--emit-shell", action="store_true", help="Print commands instead of executing them in config-backed compare")
    parser.add_argument("--no-timestamp-output", action="store_true", help="Disable timestamped config compare outputs")
    parser.add_argument("--include-noncomparable-workloads", action="store_true", help="Include non-comparable workloads in config-backed compare")
    parser.add_argument("--include-extended-workloads", action="store_true", help="Include extended workloads in config-backed compare")
    parser.add_argument("--workload-cohort", default="", help="Config-backed workload cohort filter")
    parser.add_argument("--baseline-provider-id", default="", help="Config-backed baseline provider id")
    parser.add_argument("--comparison-provider-id", default="", help="Config-backed comparison provider id")
    parser.add_argument("--baseline-name", default="", help="Config-backed baseline display name")
    parser.add_argument("--comparison-name", default="", help="Config-backed comparison display name")
    parser.add_argument("--baseline-executor-id", default="", help="Config-backed baseline executor id")
    parser.add_argument("--comparison-executor-id", default="", help="Config-backed comparison executor id")
    parser.add_argument("--comparison-view", default="", help="Config-backed comparison view")
    parser.add_argument("--provider-set", default="", help="Config-backed provider set")
    parser.add_argument("--out", default="bench/out/compare-report.json", help="Output report path")


def _ordered_products(artifacts: list[dict[str, Any]]) -> list[str]:
    products: list[str] = []
    for artifact in artifacts:
        product = str(artifact.get("product", "")).strip()
        if product and product not in products:
            products.append(product)
    return products


def _resolve_compare_policy_path(
    *,
    args: argparse.Namespace,
    artifacts: list[dict[str, Any]],
) -> str:
    if args.benchmark_policy:
        return args.benchmark_policy
    for artifact in artifacts:
        benchmark_policy = artifact.get("benchmarkPolicy")
        if not isinstance(benchmark_policy, dict):
            continue
        path = str(benchmark_policy.get("path", "")).strip()
        if path:
            return path
    return ""


def _legacy_compare_args(
    *,
    args: argparse.Namespace,
    baseline_product: str,
    comparison_product: str,
    baseline_executor_id: str,
    comparison_executor_id: str,
) -> Namespace:
    return Namespace(
        config="",
        iterations=args.iterations,
        warmup=args.warmup,
        workload_cooldown_ms=0,
        boundary="",
        runtime_host="",
        temperature="",
        comparison_view="",
        provider_set="",
        baseline_name=baseline_product,
        baseline_provider_id="",
        baseline_executor_id=baseline_executor_id,
        comparison_name=comparison_product,
        comparison_provider_id="",
        comparison_executor_id=comparison_executor_id,
        comparability=args.comparability,
        require_timing_class=args.require_timing_class,
        allow_baseline_no_execution=False,
        resource_probe=args.resource_probe,
        resource_sample_ms=args.resource_sample_ms,
        resource_sample_target_count=args.resource_sample_target_count,
        workload_cohort="all",
        selector={},
        claimability=args.claimability,
        claim_min_timed_samples=args.claim_min_timed_samples,
        emit_shell=False,
    )


def _cmd_compare(
    args: argparse.Namespace,
    *,
    raw_compare_argv: list[str] | None = None,
) -> int:
    _ensure_bench_imports()
    raw_compare_argv = list(raw_compare_argv or [])

    if args.config:
        from native_compare_modules import config_compare_runner as config_compare_runner_mod

        return config_compare_runner_mod.main(raw_compare_argv)

    if (
        args.list_promoted
        or args.profile
        or args.backend
        or args.surface
        or args.boundary
        or args.preset
        or args.workload
    ):
        from native_compare_modules import promoted_compare as promoted_compare_mod

        catalog_path = Path(args.catalog)
        entries = promoted_compare_mod.load_catalog(catalog_path)
        if args.list_promoted:
            filtered = promoted_compare_mod.filter_entries(
                entries,
                backend=args.backend,
                boundary=args.boundary,
                runtime_host=args.runtime_host,
                temperature=args.temperature,
                surface=args.surface,
                preset=args.preset,
                workload=args.workload,
                mode=args.mode,
                package_runtime=args.package_runtime,
            )
            for entry in sorted(
                filtered,
                key=lambda item: (
                    item.backend,
                    item.boundary,
                    item.runtime_host,
                    item.preset or item.workload,
                    item.temperature,
                    item.id,
                ),
            ):
                print(promoted_compare_mod.format_entry(entry))
            return 0

        entry = promoted_compare_mod.resolve_entry(
            entries,
            profile_id=args.profile,
            backend=args.backend,
            boundary=args.boundary,
            runtime_host=args.runtime_host,
            temperature=args.temperature,
            surface=args.surface,
            preset=args.preset,
            workload=args.workload,
            mode=args.mode,
            package_runtime=args.package_runtime,
        )
        argv_out = promoted_compare_mod.build_compare_argv(
            entry,
            catalog_path=catalog_path,
            passthrough=promoted_compare_mod.filter_selection_passthrough(
                raw_compare_argv
            ),
        )
        if args.dry_run:
            print(" ".join(argv_out))
            return 0
        import subprocess

        result = subprocess.run(argv_out, check=False)
        return result.returncode

    from native_compare_modules.compare_from_artifacts import (
        build_legacy_compare_report_from_artifacts,
    )
    from native_compare_modules.config_support import load_benchmark_methodology_policy
    from native_compare_modules.report_assembly import (
        write_report_and_determine_status,
    )
    from native_compare_modules.run_artifact import load_run_artifact

    artifact_paths = list(args.artifacts)

    # Inline run+compare mode: --products doe,dawn --executor-ids X,Y --workloads FILE
    if args.products and not artifact_paths:
        products = [p.strip() for p in args.products.split(",")]
        executor_ids = [e.strip() for e in args.executor_ids.split(",")]
        if len(products) != 2 or len(executor_ids) != 2:
            print("error: --products and --executor-ids must each have exactly 2 comma-separated values", file=sys.stderr)
            return 1
        if not args.workloads:
            print("error: --workloads is required for inline run+compare", file=sys.stderr)
            return 1

        # Run both products, collect artifact paths
        import subprocess
        timestamp = _utc_timestamp()
        run_dir = Path("bench/out/runs") / timestamp
        for product, executor_id in zip(products, executor_ids):
            cmd = [
                sys.executable, str(Path(__file__)),
                "run",
                "--product", product,
                "--executor-id", executor_id,
                "--workloads", args.workloads,
                "--iterations", str(args.iterations),
                "--warmup", str(args.warmup),
                "--comparability-mode", args.comparability,
                "--require-timing-class", args.require_timing_class,
                "--resource-probe", args.resource_probe,
                "--resource-sample-ms", str(args.resource_sample_ms),
                "--resource-sample-target-count", str(args.resource_sample_target_count),
                "--benchmark-policy", args.benchmark_policy,
                "--out", str(run_dir),
            ]
            if args.workload_id:
                cmd.extend(["--workload-id", args.workload_id])
            print(f"Running {product}...")
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                print(f"error: run for {product} failed with exit code {result.returncode}", file=sys.stderr)
                return 1

        artifact_paths = sorted(str(p) for p in run_dir.rglob("*.run.json"))
        if len(artifact_paths) < 2:
            print(f"error: expected at least 2 run artifacts, found {len(artifact_paths)}", file=sys.stderr)
            return 1

    if len(artifact_paths) < 2:
        print("error: compare requires at least 2 run artifact paths (or --products for inline mode)", file=sys.stderr)
        return 1

    artifacts = [load_run_artifact(p) for p in artifact_paths]
    products_seen = _ordered_products(artifacts)
    if len(products_seen) != 2:
        print(
            f"error: compare currently supports exactly 2 products, found {products_seen}",
            file=sys.stderr,
        )
        return 1
    baseline_product = args.baseline_product or products_seen[0]
    comparison_product = args.comparison_product or products_seen[1]
    if baseline_product == comparison_product:
        print(
            "error: baseline and comparison products must differ",
            file=sys.stderr,
        )
        return 1
    baseline_artifact = next(
        (
            artifact
            for artifact in artifacts
            if artifact["product"] == baseline_product
        ),
        None,
    )
    comparison_artifact = next(
        (
            artifact
            for artifact in artifacts
            if artifact["product"] == comparison_product
        ),
        None,
    )
    if baseline_artifact is None or comparison_artifact is None:
        print(
            "error: selected baseline/comparison products are missing from the artifact set",
            file=sys.stderr,
        )
        return 1
    benchmark_policy = load_benchmark_methodology_policy(
        _resolve_compare_policy_path(args=args, artifacts=artifacts)
    )
    legacy_args = _legacy_compare_args(
        args=args,
        baseline_product=baseline_product,
        comparison_product=comparison_product,
        baseline_executor_id=str(baseline_artifact.get("executorId", "")),
        comparison_executor_id=str(comparison_artifact.get("executorId", "")),
    )
    out_path = Path(args.out)
    workspace = out_path.parent / f"{out_path.stem}.workspace"
    try:
        report, comparability_failures, claimability_failures = (
            build_legacy_compare_report_from_artifacts(
                args=legacy_args,
                artifacts=artifacts,
                baseline_product=baseline_product,
                comparison_product=comparison_product,
                benchmark_policy=benchmark_policy,
                output_timestamp=_utc_timestamp(),
                out=out_path,
                workspace=workspace,
                run_artifact_paths=artifact_paths,
            )
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\nCompare report: {out_path}")
    return write_report_and_determine_status(
        report=report,
        out=out_path,
        workspace=workspace,
        args=legacy_args,
        comparability_failures=comparability_failures,
        claimability_failures=claimability_failures,
        workload_count=len(report.get("workloads", [])),
    )


# ---------------------------------------------------------------------------
# list subcommand
# ---------------------------------------------------------------------------


def _add_list_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--products", action="store_true", help="List known products from taxonomy")
    group.add_argument("--executors", action="store_true", help="List executor registry entries")
    group.add_argument("--workloads", default="", metavar="FILE", help="List workloads from contract JSON")
    group.add_argument("--surfaces", action="store_true", help="List known surfaces from taxonomy")


def _cmd_list(args: argparse.Namespace) -> int:
    _ensure_bench_imports()

    if args.products or args.surfaces:
        taxonomy_path = Path("config/compare-taxonomy.json")
        if not taxonomy_path.exists():
            print(f"error: taxonomy not found at {taxonomy_path}", file=sys.stderr)
            return 1
        taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        if args.products:
            print("Products:")
            for p in taxonomy["axes"]["products"]:
                print(f"  {p}")
        else:
            print("Surfaces:")
            for s in taxonomy["axes"]["surfaces"]:
                print(f"  {s}")
        return 0

    if args.executors:
        from native_compare_modules.executor_registry import _REGISTRY
        print("Executors:")
        for eid, spec in sorted(_REGISTRY.items()):
            print(f"  {eid:40s}  boundary={spec.execution_boundary}")
        return 0

    if args.workloads:
        wl_path = Path(args.workloads)
        if not wl_path.exists():
            print(f"error: workload file not found: {wl_path}", file=sys.stderr)
            return 1
        data = json.loads(wl_path.read_text(encoding="utf-8"))
        workloads = data.get("workloads", [])
        print(f"Workloads ({len(workloads)}) from {wl_path}:")
        for w in workloads:
            wid = w.get("id", "?")
            domain = w.get("domain", "?")
            cls = w.get("benchmarkClass", "?")
            comparable = w.get("comparable", False)
            print(f"  {wid:55s}  domain={domain:15s}  class={cls:14s}  comparable={comparable}")
        return 0

    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="doe-bench",
        description="Doe benchmark CLI: run products independently, then build compare reports from run artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one product on workload(s)")
    _add_run_args(run_parser)

    compare_parser = subparsers.add_parser("compare", help="Compare run artifacts or run config-backed/promoted compare profiles")
    _add_compare_args(compare_parser)

    list_parser = subparsers.add_parser("list", help="List products, executors, workloads, or surfaces")
    _add_list_args(list_parser)

    if argv and argv[0] == "compare":
        compare_parser = argparse.ArgumentParser(
            prog="doe-bench compare",
            description="Compare run artifacts or resolve config-backed/promoted compare profiles.",
        )
        _add_compare_args(compare_parser)
        compare_args, _ = compare_parser.parse_known_args(argv[1:])
        return _cmd_compare(compare_args, raw_compare_argv=argv[1:])

    args = parser.parse_args(argv)

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "list":
        return _cmd_list(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
