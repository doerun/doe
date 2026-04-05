"""Doe benchmark CLI.

Product-based benchmark runner with post-hoc comparison.

Usage:
    python3 bench/cli.py run     --product doe --executor-id doe_direct_vulkan ...
    python3 bench/cli.py compare <artifact1.run.json> <artifact2.run.json> ...
    python3 bench/cli.py list    --products | --executors | --workloads FILE
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
    parser.add_argument("--cohort", default="all", help="Workload cohort filter")
    parser.add_argument("--benchmark-class", default="", help="Filter by benchmarkClass (comparable, directional)")
    parser.add_argument("--out", default="bench/out/runs", help="Output directory for run artifacts")


def _cmd_run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from native_compare_modules.executor_registry import resolve_executor_command_template
    from native_compare_modules.config_support import load_workloads
    from native_compare_modules.run_artifact import (
        artifact_filename,
        build_run_artifact,
        write_run_artifact,
    )
    from native_compare_modules.runner import run_workload

    template = resolve_executor_command_template(args.executor_id)
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
    written: list[str] = []

    for wl in workloads:
        spec, configs = wl.to_spec_and_configs(
            left_product=args.product, right_product=args.product,
        )
        cfg = configs[args.product]

        command_repeat = args.command_repeat if args.command_repeat > 0 else cfg.command_repeat
        timing_divisor = args.timing_divisor if args.timing_divisor > 0 else cfg.timing_divisor
        upload_buffer_usage = args.upload_buffer_usage or cfg.upload_buffer_usage
        upload_submit_every = args.upload_submit_every if args.upload_submit_every > 0 else cfg.upload_submit_every
        ignore_first_ops = args.ignore_first_ops if args.ignore_first_ops > 0 else cfg.ignore_first_ops

        workload_dir = out_dir / f"{args.product}-{wl.id}" / timestamp
        result = run_workload(
            name=args.product,
            template=template,
            workload=wl,
            iterations=args.iterations,
            warmup=args.warmup,
            out_dir=workload_dir,
            gpu_memory_probe=args.resource_probe,
            resource_sample_ms=args.resource_sample_ms,
            resource_sample_target_count=args.resource_sample_target_count,
            timing_divisor=timing_divisor,
            command_repeat=command_repeat,
            ignore_first_ops=ignore_first_ops,
            upload_buffer_usage=upload_buffer_usage,
            upload_submit_every=upload_submit_every,
            inject_upload_runtime_flags=wl.domain == "upload",
            required_timing_class=args.require_timing_class,
            comparability_mode=args.comparability_mode,
            benchmark_policy=None,
            emit_shell=False,
        )

        from native_compare_modules.workload_spec import ProductRunConfig

        run_config = ProductRunConfig(
            product=args.product,
            command_repeat=command_repeat,
            ignore_first_ops=ignore_first_ops,
            upload_buffer_usage=upload_buffer_usage,
            upload_submit_every=upload_submit_every,
            timing_divisor=timing_divisor,
        )
        artifact = build_run_artifact(
            run_result=result,
            product=args.product,
            executor_id=args.executor_id,
            workload_spec=spec,
            run_config=run_config,
            iterations=args.iterations,
            warmup=args.warmup,
            resource_probe=args.resource_probe,
            resource_sample_ms=args.resource_sample_ms,
            resource_sample_target_count=args.resource_sample_target_count,
        )
        filename = artifact_filename(args.product, wl.id, timestamp)
        artifact_path = write_run_artifact(artifact, out_dir / filename)
        written.append(str(artifact_path))
        print(f"  {artifact_path}")

    print(f"\n{len(written)} run artifact(s) written to {out_dir}/")
    return 0


# ---------------------------------------------------------------------------
# compare subcommand
# ---------------------------------------------------------------------------


def _add_compare_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("artifacts", nargs="*", help="Run artifact JSON paths")
    parser.add_argument("--products", default="", help="Comma-separated product pair for inline run+compare (e.g. doe,dawn)")
    parser.add_argument("--executor-ids", default="", help="Comma-separated executor IDs matching --products")
    parser.add_argument("--workloads", default="", help="Workload contract JSON (for inline run+compare)")
    parser.add_argument("--workload-id", default="", help="Single workload ID filter")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--comparability", default="strict", choices=["strict", "warn", "off"])
    parser.add_argument("--require-timing-class", default="operation", choices=["any", "operation", "process-wall"])
    parser.add_argument("--claimability", default="off", choices=["off", "local", "release"])
    parser.add_argument("--claim-min-timed-samples", type=int, default=0)
    parser.add_argument("--resource-probe", default="none", choices=["none", "rocm-smi"])
    parser.add_argument("--resource-sample-target-count", type=int, default=0)
    parser.add_argument("--out", default="bench/out/compare-report.json", help="Output report path")


def _cmd_compare(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from native_compare_modules.compare_from_artifacts import (
        build_compare_report,
        compare_workload_from_artifacts,
        write_compare_report,
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
                "--out", str(run_dir),
            ]
            if args.workload_id:
                cmd.extend(["--workload-id", args.workload_id])
            print(f"Running {product}...")
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                print(f"error: run for {product} failed with exit code {result.returncode}", file=sys.stderr)
                return 1

        artifact_paths = sorted(str(p) for p in run_dir.glob("*.run.json"))
        if len(artifact_paths) < 2:
            print(f"error: expected at least 2 run artifacts, found {len(artifact_paths)}", file=sys.stderr)
            return 1

    if len(artifact_paths) < 2:
        print("error: compare requires at least 2 run artifact paths (or --products for inline mode)", file=sys.stderr)
        return 1

    # Load artifacts and group by workload ID
    artifacts = [load_run_artifact(p) for p in artifact_paths]

    # For now: 2-product comparison (baseline = first product, comparison = second)
    by_workload: dict[str, dict[str, dict[str, Any]]] = {}
    for art, path in zip(artifacts, artifact_paths):
        wid = art["workload"]["id"]
        product = art["product"]
        if wid not in by_workload:
            by_workload[wid] = {}
        by_workload[wid][product] = art

    products_seen = sorted({a["product"] for a in artifacts})
    if len(products_seen) != 2:
        print(f"error: compare currently supports exactly 2 products, found {products_seen}", file=sys.stderr)
        return 1
    baseline_product, comparison_product = products_seen[0], products_seen[1]

    workload_entries: list[dict[str, Any]] = []
    first_baseline = None
    first_comparison = None
    for wid in sorted(by_workload):
        group = by_workload[wid]
        if baseline_product not in group or comparison_product not in group:
            print(f"  skip {wid}: missing product (have {sorted(group)})")
            continue
        baseline = group[baseline_product]
        comparison = group[comparison_product]
        if first_baseline is None:
            first_baseline = baseline
        if first_comparison is None:
            first_comparison = comparison

        entry = compare_workload_from_artifacts(
            baseline=baseline,
            comparison=comparison,
            comparability_mode=args.comparability,
            required_timing_class=args.require_timing_class,
            claimability_mode=args.claimability,
            claimability_min_timed_samples=args.claim_min_timed_samples,
            resource_probe=args.resource_probe,
            resource_sample_target_count=args.resource_sample_target_count,
        )
        status = "comparable" if entry["comparability"].get("comparable") else "diagnostic"
        claim = ""
        if entry["claimability"].get("evaluated"):
            claim = " claimable" if entry["claimability"].get("claimable") else " non-claimable"
        delta_p50 = entry["deltaPercent"].get("p50Percent", 0)
        sign = "+" if delta_p50 > 0 else ""
        print(f"  {wid}: {sign}{delta_p50:.1f}% p50 [{status}{claim}]")
        workload_entries.append(entry)

    if not workload_entries:
        print("error: no workloads matched between the two products", file=sys.stderr)
        return 1

    report = build_compare_report(
        workload_entries=workload_entries,
        baseline_artifact=first_baseline,
        comparison_artifact=first_comparison,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
        claimability_mode=args.claimability,
        claimability_min_timed_samples=args.claim_min_timed_samples,
        out_path=args.out,
        run_artifact_paths=artifact_paths,
    )

    out_path = Path(args.out)
    write_compare_report(report, out_path)
    print(f"\nCompare report: {out_path}")

    n_comparable = sum(1 for e in workload_entries if e["comparability"].get("comparable"))
    n_claimable = sum(1 for e in workload_entries if e["claimability"].get("claimable"))
    print(f"{len(workload_entries)} workloads, {n_comparable} comparable, {n_claimable} claimable")

    if args.comparability == "strict" and n_comparable < len(workload_entries):
        return 1
    return 0


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
    sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    parser = argparse.ArgumentParser(
        prog="doe-bench",
        description="Doe benchmark CLI: run products independently, compare afterward.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one product on workload(s)")
    _add_run_args(run_parser)

    compare_parser = subparsers.add_parser("compare", help="Compare run artifacts from two or more products")
    _add_compare_args(compare_parser)

    list_parser = subparsers.add_parser("list", help="List products, executors, workloads, or surfaces")
    _add_list_args(list_parser)

    args = parser.parse_args()

    if args.command == "run":
        return _cmd_run(args)
    elif args.command == "compare":
        return _cmd_compare(args)
    elif args.command == "list":
        return _cmd_list(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
