#!/usr/bin/env python3
"""WGSL compilation speed comparison: Doe vs Tint.

Runs both compilers on the same named workload rows or a legacy shader
corpus and emits a comparison report with per-shader delta statistics.
Both sides measure the same scope: WGSL source -> target text/binary
(parse + sema + IR + emit).

Usage:
    python3 bench/native-compare/compare_doe_vs_tint_compilation.py \
        --config bench/native-compare/compare_doe_vs_tint.config.json

Requirements:
    - Doe compilation benchmark binary: zig-out/bin/doe-compilation-bench
    - Tint binary (Release build): bench/vendor/dawn/out/Release/tint
    - Both must be built before running.

Output:
    NDJSON comparison report at the configured output path.
"""

import argparse
import ast
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.lib.adhoc_claim_gating import (  # noqa: E402
    CLAIM_REPORT_SCHEMA_VERSION,
    DELTA_PERCENT_CONVENTION,
    ClaimPolicy,
    DeltaPercentiles,
    aggregate_claim_status,
    gate_workload_claim,
)
from bench.native_compare_modules.reporting import (  # noqa: E402
    format_stats,
    subtract_baseline_ms,
)

TARGET_MAP = {"msl": "msl", "spirv": "spv", "hlsl": "hlsl"}
TINT_BENCHMARK_TARGET_MAP = {"msl": "GenerateMSL", "spirv": "GenerateSPIRV", "hlsl": "GenerateHLSL"}
DEFAULT_TINT_WARM_MIN_TIME = "0.01s"
DEFAULT_TINT_WARM_REPETITIONS = 9
SCHEMA_VERSION = 3
_TINT_STARTUP_BASELINE_WGSL = """@compute @workgroup_size(1)
fn main() {}
"""


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to comparison config JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    parser.add_argument(
        "--workload-id",
        action="append",
        default=[],
        help="Optional compilation workload id to run. Repeat to select multiple rows.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        help="Override timed iterations from config.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        help="Override warmup iterations from config.",
    )
    parser.add_argument(
        "--claim-mode",
        choices=("local", "release"),
        default="release",
        help=(
            "Claim policy mode. local requires >=7 timed samples and positive p50/p95; "
            "release requires >=15 timed samples and positive p50/p95/p99."
        ),
    )
    return parser.parse_args()


def load_config(path):
    with open(path) as f:
        return json.load(f)


def infer_tier_from_name(name):
    if name.startswith("compilation_inference_") or name.startswith("inference_"):
        return "inference"
    head = name.split("_", 1)[0]
    if head in {"trivial", "simple", "moderate", "complex", "stress"}:
        return head
    return "external"


def discover_corpus(corpus_dir, tiers):
    """Find .wgsl files in corpus_dir, optionally filtering by tier prefix."""
    corpus_path = REPO_ROOT / corpus_dir
    if not corpus_path.is_dir():
        print(f"error: corpus directory not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    shaders = []
    for wgsl in sorted(corpus_path.glob("*.wgsl")):
        name = wgsl.stem
        tier = name.split("_")[0]  # trivial, simple, moderate, complex, stress
        if tiers and tier not in tiers:
            continue
        line_count = len(wgsl.read_text().splitlines())
        shaders.append(
            {"name": name, "tier": tier, "path": str(wgsl), "sourceLines": line_count}
        )

    if not shaders:
        print(f"error: no shaders found in {corpus_path}", file=sys.stderr)
        sys.exit(1)

    return shaders


def discover_workload_rows(workloads_path, workload_ids):
    workload_path = REPO_ROOT / workloads_path
    if not workload_path.is_file():
        print(f"error: workloads file not found: {workload_path}", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(workload_path.read_text(encoding="utf-8"))
    rows = payload.get("workloads", [])
    requested_ids = list(workload_ids or [])
    requested_id_set = set(requested_ids)
    shaders = []

    for row in rows:
        if row.get("runnerType") != "compilation":
            continue
        workload_id = row.get("id", "")
        if requested_id_set and workload_id not in requested_id_set:
            continue
        shader_rel = row.get("shaderPath", "")
        shader_path = REPO_ROOT / shader_rel
        if not shader_path.is_file():
            print(
                f"error: shaderPath not found for workload {workload_id}: {shader_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        source_lines = len(shader_path.read_text(encoding="utf-8").splitlines())
        shaders.append(
            {
                "workloadId": workload_id,
                "name": workload_id,
                "tier": infer_tier_from_name(workload_id),
                "path": str(shader_path),
                "sourceLines": source_lines,
                "target": row.get("compilationTarget", "msl"),
                "sourceShader": shader_path.stem,
            }
        )

    if requested_id_set:
        found_ids = {shader["workloadId"] for shader in shaders}
        missing = [workload_id for workload_id in requested_ids if workload_id not in found_ids]
        if missing:
            print(
                f"error: workload ids not found in {workload_path}: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not shaders:
        print(f"error: no compilation workloads found in {workload_path}", file=sys.stderr)
        sys.exit(1)

    return shaders


def discover_tint_benchmark_rows(script_path, requested_names):
    benchmark_script = REPO_ROOT / script_path
    if not benchmark_script.is_file():
        print(f"error: Tint benchmark input script not found: {benchmark_script}", file=sys.stderr)
        sys.exit(1)

    script_text = benchmark_script.read_text(encoding="utf-8")
    marker = "kBenchmarkFiles = ["
    start = script_text.find(marker)
    if start < 0:
        print(f"error: failed to locate kBenchmarkFiles in {benchmark_script}", file=sys.stderr)
        sys.exit(1)
    end = script_text.find("]\n\n\ndef main", start)
    if end < 0:
        print(f"error: failed to parse kBenchmarkFiles block in {benchmark_script}", file=sys.stderr)
        sys.exit(1)
    try:
        benchmark_files = ast.literal_eval(script_text[start + len("kBenchmarkFiles = "):end + 1])
    except (SyntaxError, ValueError) as exc:
        print(f"error: failed to parse kBenchmarkFiles from {benchmark_script}: {exc}", file=sys.stderr)
        sys.exit(1)

    requested_name_set = set(requested_names or [])
    base_dir = (benchmark_script.parent / "../../../../").resolve()
    shaders = []
    for benchmark_file in benchmark_files:
        benchmark_name = Path(benchmark_file).name
        if requested_name_set and benchmark_name not in requested_name_set:
            continue
        shader_rel = f"{benchmark_file}.wgsl" if benchmark_file.endswith(".spv") else benchmark_file
        shader_path = (base_dir / shader_rel).resolve()
        if not shader_path.is_file():
            print(
                f"error: Tint benchmark shader not found for {benchmark_name}: {shader_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        source_lines = len(shader_path.read_text(encoding="utf-8").splitlines())
        shaders.append(
            {
                "name": benchmark_name,
                "benchmarkName": benchmark_name,
                "tier": "benchmark",
                "path": str(shader_path),
                "sourceLines": source_lines,
                "sourceShader": shader_path.stem,
            }
        )

    if requested_name_set:
        found_names = {shader["name"] for shader in shaders}
        missing = [name for name in requested_names if name not in found_names]
        if missing:
            print(
                f"error: Tint benchmark shader names not found in {benchmark_script}: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not shaders:
        print(f"error: no Tint benchmark shaders found in {benchmark_script}", file=sys.stderr)
        sys.exit(1)

    return shaders


def ns_stats(samples):
    if not samples:
        return {
            "p50_ns": 0,
            "p95_ns": 0,
            "p99_ns": 0,
            "min_ns": 0,
            "max_ns": 0,
            "mean_ns": 0,
            "iterations": 0,
        }

    ordered = sorted(int(sample) for sample in samples)

    def percentile(p):
        index = int((len(ordered) - 1) * p)
        return ordered[index]

    return {
        "p50_ns": percentile(0.50),
        "p95_ns": percentile(0.95),
        "p99_ns": percentile(0.99),
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
        "mean_ns": sum(ordered) // len(ordered),
        "iterations": len(ordered),
    }


def duration_to_ns(value, unit):
    if value is None:
        return None
    scale = {
        "ns": 1.0,
        "us": 1_000.0,
        "ms": 1_000_000.0,
        "s": 1_000_000_000.0,
    }.get(unit)
    if scale is None:
        return None
    return int(float(value) * scale)


def run_doe_bench(cfg, shaders, target, out_path, dry_run):
    """Run Doe's compilation benchmark on the selected shader rows."""
    doe_bin = REPO_ROOT / cfg["baseline"]["binaryPath"]
    if not doe_bin.exists() and not dry_run:
        print(f"error: Doe binary not found: {doe_bin}", file=sys.stderr)
        print("  Build with: cd runtime/zig && zig build bench-compilation", file=sys.stderr)
        sys.exit(1)
    results = {}
    calibration = None

    for shader in shaders:
        shader_target = shader.get("target", target)
        cmd = [
            str(doe_bin),
            "--target", shader_target,
            "--iterations", str(cfg["run"]["iterations"]),
            "--warmup", str(cfg["run"]["warmup"]),
            "--shader-path", shader["path"],
            "--shader-name", shader["name"],
            "--shader-tier", shader["tier"],
            "--out", str(out_path),
        ]

        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
            results[shader["name"]] = {"p50_ns": 0, "p95_ns": 0, "p99_ns": 0}
            continue

        subprocess.run(cmd, check=True)
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                kind = record.get("kind")
                if kind == "compilation_bench_calibration" and calibration is None:
                    calibration = record
                if kind == "compilation_bench" and record.get("shader") == shader["name"]:
                    results[shader["name"]] = record
                    break

    return results, calibration


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_claim_report(
    *,
    cfg,
    shaders,
    target,
    records,
    calibration,
    claim_mode,
):
    """Build a claim-report alongside the comparison ndjson."""
    policy = ClaimPolicy.for_mode(claim_mode)
    required_pcts = [f"warm.{pct}" for pct in policy.required_positive_percentiles]
    timer_overhead_ns = int(calibration.get("timerOverheadP50Ns", 0)) if calibration else 0
    workloads = []

    for record in records:
        if record.get("status") != "compared":
            workloads.append(
                {
                    "shader": record.get("shader"),
                    "claimable": False,
                    "reasons": [f"row not compared: {record.get('reason', record.get('status'))}"],
                    "requiredPositivePercentiles": required_pcts,
                }
            )
            continue

        comparison = record.get("comparison", {})
        baseline = record.get("baseline", {})
        warm = comparison.get("warm", {})
        warm_iterations = int(warm.get("iterations", 0) or 0)
        comparison_iterations = int(comparison.get("iterations", 0) or 0)
        baseline_iterations = int(
            baseline.get("iterations") or cfg["run"].get("iterations", 0) or 0
        )
        warm_delta = record.get("warmDeltaPercent", {})
        smallest_measurement_candidates = [
            value for value in (baseline.get("p50_ns"), warm.get("p50_ns")) if value
        ]
        smallest_measurement_p50_ns = (
            int(min(smallest_measurement_candidates))
            if smallest_measurement_candidates
            else None
        )
        delta_percent = DeltaPercentiles(
            p50=warm_delta.get("p50"),
            p95=warm_delta.get("p95"),
            p99=warm_delta.get("p99"),
        )
        gate = gate_workload_claim(
            shader=str(record.get("shader", "")),
            baseline_sample_count=baseline_iterations,
            comparison_sample_count=comparison_iterations or warm_iterations,
            warm_comparison_sample_count=warm_iterations,
            delta_percent=delta_percent,
            policy=policy,
            timer_overhead_p50_ns=timer_overhead_ns or None,
            smallest_measurement_p50_ns=smallest_measurement_p50_ns,
            extra_details={
                "requiredPositivePercentiles": required_pcts,
                "warmDeltaPercent": warm_delta,
                "warmIterations": warm_iterations,
                "doeP50Ns": baseline.get("p50_ns"),
                "tintWarmP50Ns": warm.get("p50_ns"),
            },
        )
        if not warm or not warm_iterations:
            gate["reasons"].insert(0, "no warm in-process Tint samples (config lacks warmBinaryPath)")
            gate["claimable"] = False
        workloads.append(gate)

    claim_status, claim_pass, aggregate_reasons = aggregate_claim_status(workloads)

    doe_bin_path = REPO_ROOT / cfg["baseline"]["binaryPath"]
    tint_bin_path = REPO_ROOT / cfg["comparison"]["binaryPath"]
    warm_bin_path = (
        REPO_ROOT / cfg["comparison"].get("warmBinaryPath")
        if cfg["comparison"].get("warmBinaryPath")
        else None
    )
    claim_policy = policy.to_dict(timer_overhead_p50_ns=timer_overhead_ns)
    claim_policy["requiredPositivePercentiles"] = required_pcts
    claim_policy["deltaPercentConvention"] = DELTA_PERCENT_CONVENTION

    return {
        "schemaVersion": CLAIM_REPORT_SCHEMA_VERSION,
        "artifactKind": "claim-report",
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "claimMode": claim_mode,
        "claimPolicy": claim_policy,
        "compareConfigPath": str(cfg.get("_configPath", "")),
        "target": target,
        "binaryProvenance": {
            "doe": {
                "path": str(doe_bin_path),
                "sha256": file_sha256(doe_bin_path) if doe_bin_path.exists() else "",
            },
            "tint": {
                "path": str(tint_bin_path),
                "sha256": file_sha256(tint_bin_path) if tint_bin_path.exists() else "",
            },
            "tintWarm": {
                "path": str(warm_bin_path) if warm_bin_path else "",
                "sha256": (
                    file_sha256(warm_bin_path)
                    if warm_bin_path and warm_bin_path.exists()
                    else ""
                ),
            },
        },
        "timingScopeSymmetry": {
            "doe": "std.time.Timer per-translation in-process",
            "tintWarm": "Google Benchmark real_time per-iteration in-process (tint_benchmark)",
            "equivalent": True,
            "notes": (
                "both sides measure per-iteration in-process compile cost; "
                "Doe per-iteration timer overhead is reported in claimPolicy."
                "timerOverheadP50Ns and gated by claimPolicy.timerOverheadBudgetPercent"
            ),
        },
        "comparisonStatus": "comparable",
        "claimStatus": claim_status,
        "pass": claim_pass,
        "reasons": aggregate_reasons,
        "workloads": workloads,
    }


def _run_tint_samples(tint_bin, tint_format, shader_path, total_runs, warmup):
    samples = []
    for i in range(total_runs):
        start = time.perf_counter_ns()
        proc = subprocess.run(
            [str(tint_bin), f"--format={tint_format}", shader_path],
            capture_output=True,
        )
        elapsed = time.perf_counter_ns() - start

        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode()[:200])

        if i >= warmup:
            samples.append(elapsed)
    return samples


def measure_tint_startup_baseline(tint_bin, tint_format, iterations, warmup, dry_run):
    total_runs = iterations + warmup
    if dry_run:
        print(f"[dry-run] tint startup-baseline --format={tint_format} x{total_runs}")
        return {"p50_ns": 0, "p95_ns": 0, "p99_ns": 0, "min_ns": 0, "max_ns": 0, "mean_ns": 0, "iterations": 0}

    with tempfile.TemporaryDirectory(prefix="doe-tint-startup-") as tmpdir:
        shader_path = Path(tmpdir) / "startup-baseline.wgsl"
        shader_path.write_text(_TINT_STARTUP_BASELINE_WGSL, encoding="utf-8")
        samples = _run_tint_samples(tint_bin, tint_format, str(shader_path), total_runs, warmup)
    stats_ms = format_stats([sample / 1_000_000.0 for sample in samples])
    return {
        "p50_ns": int(stats_ms["p50Ms"] * 1_000_000.0),
        "p95_ns": int(stats_ms["p95Ms"] * 1_000_000.0),
        "p99_ns": int(stats_ms["p99Ms"] * 1_000_000.0),
        "min_ns": int(stats_ms["minMs"] * 1_000_000.0),
        "max_ns": int(stats_ms["maxMs"] * 1_000_000.0),
        "mean_ns": int(stats_ms["meanMs"] * 1_000_000.0),
        "iterations": int(stats_ms["count"]),
    }


def run_tint_bench(cfg, shaders, target, iterations, warmup, dry_run):
    """Time Tint compilation for each shader in the corpus."""
    tint_bin = REPO_ROOT / cfg["comparison"]["binaryPath"]
    tint_format = TARGET_MAP.get(target, target)

    if not tint_bin.exists() and not dry_run:
        print(f"error: Tint binary not found: {tint_bin}", file=sys.stderr)
        print(
            "  Build Dawn in Release mode, then copy tint binary to the configured path.",
            file=sys.stderr,
        )
        sys.exit(1)

    results = {}
    total_runs = iterations + warmup
    startup_baseline = measure_tint_startup_baseline(
        tint_bin,
        tint_format,
        iterations,
        warmup,
        dry_run,
    )
    startup_baseline_p50_ns = startup_baseline.get("p50_ns", 0)
    tint_warm_results = run_tint_warm_bench(cfg, shaders, target, dry_run)

    for shader in shaders:
        if dry_run:
            print(f"[dry-run] tint --format={tint_format} {shader['path']} x{total_runs}")
            results[shader["name"]] = {
                "p50_ns": 0,
                "p95_ns": 0,
                "p99_ns": 0,
                "startupBaseline": startup_baseline,
                "startupCorrected": {"p50_ns": 0, "p95_ns": 0, "p99_ns": 0},
                "warm": tint_warm_results.get(shader["name"], {"p50_ns": 0, "p95_ns": 0, "p99_ns": 0}),
            }
            continue

        try:
            samples = _run_tint_samples(
                tint_bin,
                tint_format,
                shader["path"],
                total_runs,
                warmup,
            )
        except RuntimeError as exc:
            print(
                f"  warning: tint failed on {shader['name']}: {str(exc)[:200]}",
                file=sys.stderr,
            )
            samples = []

        if not samples:
            print(f"  skipping {shader['name']}: no successful timed samples", file=sys.stderr)
            continue

        samples.sort()
        corrected_samples = subtract_baseline_ms(
            [sample / 1_000_000.0 for sample in samples],
            startup_baseline_p50_ns / 1_000_000.0,
        )
        corrected_stats_ms = format_stats(corrected_samples)
        n = len(samples)
        results[shader["name"]] = {
            "p50_ns": samples[n // 2],
            "p95_ns": samples[int(n * 0.95)],
            "p99_ns": samples[min(int(n * 0.99), n - 1)],
            "min_ns": samples[0],
            "max_ns": samples[-1],
            "mean_ns": sum(samples) // n,
            "iterations": n,
            "timingNote": "process-level timing includes tint startup overhead",
            "startupBaseline": startup_baseline,
            "startupCorrected": {
                "p50_ns": int(corrected_stats_ms["p50Ms"] * 1_000_000.0),
                "p95_ns": int(corrected_stats_ms["p95Ms"] * 1_000_000.0),
                "p99_ns": int(corrected_stats_ms["p99Ms"] * 1_000_000.0),
                "timingNote": "raw tint process-wall samples with the trivial-shader baseline p50 subtracted",
            },
            "warm": tint_warm_results.get(shader["name"], {}),
        }

    return results


def run_tint_warm_bench(cfg, shaders, target, dry_run):
    warm_binary_path = cfg["comparison"].get("warmBinaryPath")
    if not warm_binary_path:
        return {}

    benchmark_prefix = TINT_BENCHMARK_TARGET_MAP.get(target)
    if benchmark_prefix is None:
        print(f"error: Tint warm benchmark target is unsupported for {target}", file=sys.stderr)
        sys.exit(1)

    warm_bin = REPO_ROOT / warm_binary_path
    if not warm_bin.exists() and not dry_run:
        print(f"error: Tint warm benchmark binary not found: {warm_bin}", file=sys.stderr)
        print("  Build with: ninja -C bench/vendor/dawn/out/Release tint_benchmark", file=sys.stderr)
        sys.exit(1)

    repetitions = int(cfg["run"].get("warmRepetitions", DEFAULT_TINT_WARM_REPETITIONS))
    min_time = cfg["run"].get("warmMinTime", DEFAULT_TINT_WARM_MIN_TIME)
    selected_names = {shader.get("benchmarkName", shader["name"]) for shader in shaders}
    command = [
        str(warm_bin),
        f"--benchmark_filter={benchmark_prefix}/.*",
        f"--benchmark_min_time={min_time}",
        f"--benchmark_repetitions={repetitions}",
        "--benchmark_report_aggregates_only=false",
        "--benchmark_format=json",
    ]

    if dry_run:
        print(f"[dry-run] {' '.join(command)}")
        return {
            shader["name"]: {
                "p50_ns": 0,
                "p95_ns": 0,
                "p99_ns": 0,
                "timingNote": "in-process tint_benchmark real_time samples",
            }
            for shader in shaders
        }

    proc = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    samples_by_name = {}
    for benchmark in payload.get("benchmarks", []):
        if benchmark.get("run_type") != "iteration":
            continue
        benchmark_name = benchmark.get("name", "")
        if not benchmark_name.startswith(f"{benchmark_prefix}/"):
            continue
        short_name = benchmark_name.split("/", 1)[1]
        if short_name not in selected_names:
            continue
        sample_ns = duration_to_ns(benchmark.get("real_time"), benchmark.get("time_unit"))
        if sample_ns is None:
            continue
        samples_by_name.setdefault(short_name, []).append(sample_ns)

    results = {}
    for shader in shaders:
        benchmark_name = shader.get("benchmarkName", shader["name"])
        samples = samples_by_name.get(benchmark_name, [])
        if not samples:
            continue
        result = ns_stats(samples)
        result["timingNote"] = "in-process tint_benchmark real_time samples"
        results[shader["name"]] = result
    return results


def compute_delta(baseline_ns, comparison_ns):
    """Positive = baseline (Doe) is faster."""
    if baseline_ns == 0:
        return None
    return ((comparison_ns / baseline_ns) - 1) * 100


def build_report(cfg, shaders, target, doe_results, tint_results):
    """Build comparison report records."""
    records = []

    for shader in shaders:
        name = shader["name"]
        doe = doe_results.get(name)
        tint = tint_results.get(name)

        if not doe or not tint:
            records.append(
                {
                    "kind": "compilation_comparison",
                    "schemaVersion": SCHEMA_VERSION,
                    "shader": name,
                    "workloadId": shader.get("workloadId", name),
                    "shaderPath": shader["path"],
                    "tier": shader["tier"],
                    "target": target,
                    "sourceLines": shader["sourceLines"],
                    "status": "skipped",
                    "reason": "missing_doe" if not doe else "missing_tint",
                }
            )
            continue

        baseline_p50 = doe.get("p50_ns", 0)
        comparison_p50 = tint.get("p50_ns", 0)
        baseline_p95 = doe.get("p95_ns", 0)
        comparison_p95 = tint.get("p95_ns", 0)
        baseline_p99 = doe.get("p99_ns", 0)
        comparison_p99 = tint.get("p99_ns", 0)
        comparison_corrected = tint.get("startupCorrected", {})
        comparison_corrected_p50 = comparison_corrected.get("p50_ns", 0)
        comparison_corrected_p95 = comparison_corrected.get("p95_ns", 0)
        comparison_corrected_p99 = comparison_corrected.get("p99_ns", 0)
        comparison_warm = tint.get("warm", {})
        comparison_warm_p50 = comparison_warm.get("p50_ns", 0)
        comparison_warm_p95 = comparison_warm.get("p95_ns", 0)
        comparison_warm_p99 = comparison_warm.get("p99_ns", 0)

        records.append(
            {
                "kind": "compilation_comparison",
                "schemaVersion": SCHEMA_VERSION,
                "deltaPercentConvention": DELTA_PERCENT_CONVENTION,
                "shader": name,
                "workloadId": shader.get("workloadId", name),
                "shaderPath": shader["path"],
                "tier": shader["tier"],
                "target": target,
                "sourceLines": shader["sourceLines"],
                "baseline": {
                    "compiler": "doe_wgsl",
                    "p50_ns": baseline_p50,
                    "p95_ns": baseline_p95,
                    "p99_ns": baseline_p99,
                    "iterations": doe.get("iterations", 0),
                    "bytesOut": doe.get("bytesOut", 0),
                    "timingNote": "in-process measurement, no startup overhead",
                },
                "comparison": {
                    "compiler": "tint",
                    "p50_ns": comparison_p50,
                    "p95_ns": comparison_p95,
                    "p99_ns": comparison_p99,
                    "iterations": tint.get("iterations", 0),
                    "timingNote": tint.get(
                        "timingNote",
                        "process-level timing includes startup overhead",
                    ),
                    "startupBaseline": tint.get("startupBaseline", {}),
                    "startupCorrected": {
                        "p50_ns": comparison_corrected_p50,
                        "p95_ns": comparison_corrected_p95,
                        "p99_ns": comparison_corrected_p99,
                        "timingNote": comparison_corrected.get(
                            "timingNote",
                            "raw tint process-wall samples with the trivial-shader baseline p50 subtracted",
                        ),
                    },
                    "warm": {
                        "p50_ns": comparison_warm_p50,
                        "p95_ns": comparison_warm_p95,
                        "p99_ns": comparison_warm_p99,
                        "iterations": comparison_warm.get("iterations", 0),
                        "timingNote": comparison_warm.get(
                            "timingNote",
                            "in-process tint_benchmark real_time samples",
                        ),
                    },
                },
                "deltaPercent": {
                    "p50": round(compute_delta(baseline_p50, comparison_p50), 2)
                    if baseline_p50 > 0 and comparison_p50 > 0
                    else None,
                    "p95": round(compute_delta(baseline_p95, comparison_p95), 2)
                    if baseline_p95 > 0 and comparison_p95 > 0
                    else None,
                    "p99": round(compute_delta(baseline_p99, comparison_p99), 2)
                    if baseline_p99 > 0 and comparison_p99 > 0
                    else None,
                },
                "startupCorrectedDeltaPercent": {
                    "p50": round(compute_delta(baseline_p50, comparison_corrected_p50), 2)
                    if baseline_p50 > 0 and comparison_corrected_p50 > 0
                    else None,
                    "p95": round(compute_delta(baseline_p95, comparison_corrected_p95), 2)
                    if baseline_p95 > 0 and comparison_corrected_p95 > 0
                    else None,
                    "p99": round(compute_delta(baseline_p99, comparison_corrected_p99), 2)
                    if baseline_p99 > 0 and comparison_corrected_p99 > 0
                    else None,
                },
                "warmDeltaPercent": {
                    "p50": round(compute_delta(baseline_p50, comparison_warm_p50), 2)
                    if baseline_p50 > 0 and comparison_warm_p50 > 0
                    else None,
                    "p95": round(compute_delta(baseline_p95, comparison_warm_p95), 2)
                    if baseline_p95 > 0 and comparison_warm_p95 > 0
                    else None,
                    "p99": round(compute_delta(baseline_p99, comparison_warm_p99), 2)
                    if baseline_p99 > 0 and comparison_warm_p99 > 0
                    else None,
                },
                "status": "compared",
                "comparabilityNote": (
                    "Doe uses in-process timing; Tint raw timings use process-level timing "
                    "which includes OS process startup. startupCorrectedDeltaPercent is a "
                    "derived view that subtracts the trivial-shader baseline p50 from each "
                    "Tint raw sample; raw timings remain the auditable source metric. "
                    "When comparison.warm is present it comes from the in-process Dawn "
                    "tint_benchmark target on the Tint benchmark corpus."
                ),
            }
        )

    return records


def write_report(records, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        for record in records:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"wrote {len(records)} records to {out_path}")


def print_summary(records, target):
    compared = [r for r in records if r.get("status") == "compared"]
    if not compared:
        print("no comparable results")
        return

    print(
        f"\n{'shader':<40} {'tier':<10} {'doe p50(us)':>12} "
        f"{'tint raw(us)':>12} {'tint corr(us)':>14} {'tint warm(us)':>14} "
        f"{'raw delta%':>11} {'corr delta%':>12} {'warm delta%':>12}"
    )
    print("-" * 140)

    for r in compared:
        doe_us = r["baseline"]["p50_ns"] / 1000
        tint_raw_us = r["comparison"]["p50_ns"] / 1000
        tint_corr_us = r["comparison"]["startupCorrected"]["p50_ns"] / 1000
        tint_warm_us = r["comparison"]["warm"]["p50_ns"] / 1000
        raw_delta = r["deltaPercent"]["p50"]
        corr_delta = r["startupCorrectedDeltaPercent"]["p50"]
        warm_delta = r["warmDeltaPercent"]["p50"]
        raw_delta_str = f"+{raw_delta:.1f}%" if raw_delta and raw_delta > 0 else f"{raw_delta:.1f}%" if raw_delta else "n/a"
        corr_delta_str = f"+{corr_delta:.1f}%" if corr_delta and corr_delta > 0 else f"{corr_delta:.1f}%" if corr_delta else "n/a"
        warm_delta_str = f"+{warm_delta:.1f}%" if warm_delta and warm_delta > 0 else f"{warm_delta:.1f}%" if warm_delta else "n/a"
        print(
            f"{r['shader']:<40} {r['tier']:<10} {doe_us:>12.1f} {tint_raw_us:>12.1f} "
            f"{tint_corr_us:>14.1f} {tint_warm_us:>14.1f} "
            f"{raw_delta_str:>11} {corr_delta_str:>12} {warm_delta_str:>12}"
        )

    # aggregate
    doe_total = sum(r["baseline"]["p50_ns"] for r in compared)
    tint_total = sum(r["comparison"]["p50_ns"] for r in compared)
    tint_corrected_total = sum(r["comparison"]["startupCorrected"]["p50_ns"] for r in compared)
    tint_warm_total = sum(r["comparison"]["warm"]["p50_ns"] for r in compared)
    overall_delta = compute_delta(doe_total, tint_total)
    overall_corrected_delta = compute_delta(doe_total, tint_corrected_total)
    overall_warm_delta = compute_delta(doe_total, tint_warm_total)
    overall_delta_str = (
        f"{'+' if overall_delta > 0 else ''}{overall_delta:.1f}%"
        if overall_delta is not None
        else "n/a"
    )
    overall_corrected_delta_str = (
        f"{'+' if overall_corrected_delta > 0 else ''}{overall_corrected_delta:.1f}%"
        if overall_corrected_delta is not None
        else "n/a"
    )
    overall_warm_delta_str = (
        f"{'+' if overall_warm_delta > 0 else ''}{overall_warm_delta:.1f}%"
        if overall_warm_delta is not None
        else "n/a"
    )
    print("-" * 140)
    print(
        f"{'TOTAL':<40} {'':<10} {doe_total/1000:>12.1f} {tint_total/1000:>12.1f} "
        f"{tint_corrected_total/1000:>14.1f} {tint_warm_total/1000:>14.1f} "
        f"{overall_delta_str:>11} {overall_corrected_delta_str:>12} {overall_warm_delta_str:>12}"
    )


def main():
    args = parse_args()
    cfg = load_config(args.config)

    corpus_dir = cfg.get("corpusDir", "bench/kernels/compilation-corpus")
    tiers = cfg["run"].get("tiers", [])
    targets = cfg["run"].get("targets", ["msl"])
    iterations = args.iterations if args.iterations is not None else cfg["run"]["iterations"]
    warmup = args.warmup if args.warmup is not None else cfg["run"]["warmup"]
    out_dir = cfg["run"].get("outDir", "bench/out/compilation")
    out_stem = cfg["run"].get("outStem", "doe-vs-tint")
    cfg["run"]["iterations"] = iterations
    cfg["run"]["warmup"] = warmup

    if "tintBenchmarkInputsScriptPath" in cfg:
        benchmark_names = args.workload_id or cfg.get("shaderNames", [])
        shaders = discover_tint_benchmark_rows(cfg["tintBenchmarkInputsScriptPath"], benchmark_names)
        source_label = cfg["tintBenchmarkInputsScriptPath"]
    elif "workloads" in cfg:
        workload_ids = args.workload_id or cfg.get("workloadIds", [])
        shaders = discover_workload_rows(cfg["workloads"], workload_ids)
        source_label = cfg["workloads"]
    else:
        shaders = discover_corpus(corpus_dir, tiers)
        source_label = corpus_dir

    print(f"shaders: {len(shaders)} selected from {source_label}")

    cfg["_configPath"] = args.config

    for target in targets:
        print(f"\n=== target: {target} ===")

        doe_out = REPO_ROOT / out_dir / f"doe-{target}.ndjson"
        os.makedirs(doe_out.parent, exist_ok=True)

        doe_results, calibration = run_doe_bench(cfg, shaders, target, doe_out, args.dry_run)
        tint_results = run_tint_bench(cfg, shaders, target, iterations, warmup, args.dry_run)

        records = build_report(cfg, shaders, target, doe_results, tint_results)

        report_path = REPO_ROOT / out_dir / f"{out_stem}.{target}.ndjson"
        write_report(records, report_path)
        print_summary(records, target)

        if not args.dry_run:
            claim_report = build_claim_report(
                cfg=cfg,
                shaders=shaders,
                target=target,
                records=records,
                calibration=calibration,
                claim_mode=args.claim_mode,
            )
            claim_path = REPO_ROOT / out_dir / f"{out_stem}.{target}.claim.json"
            with open(claim_path, "w") as f:
                json.dump(claim_report, f, indent=2)
                f.write("\n")
            print(
                f"\nclaim mode: {claim_report['claimMode']} "
                f"status: {claim_report['claimStatus']} pass: {claim_report['pass']}"
            )
            if claim_report["reasons"]:
                for reason in claim_report["reasons"]:
                    print(f"  - {reason}")
            non_claim = [w for w in claim_report["workloads"] if not w["claimable"]]
            if non_claim:
                print(f"\nnon-claimable rows ({len(non_claim)}):")
                for w in non_claim[:10]:
                    print(f"  - {w['shader']}: {'; '.join(w['reasons'])}")
            print(f"\nwrote claim report: {claim_path}")


if __name__ == "__main__":
    main()
