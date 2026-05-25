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
DEFAULT_DOE_EMIT_BINARY = "runtime/zig/zig-out/bin/doe-runtime-compile-report"
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
    parser.add_argument(
        "--evidence-out",
        default="",
        help=(
            "Optional tint-compiler-evidence JSON path. The report is diagnostic "
            "unless the timed rows, compiler outputs, validation, and claim gate all pass."
        ),
    )
    parser.add_argument(
        "--doe-emit-binary",
        default=DEFAULT_DOE_EMIT_BINARY,
        help="Doe compiler-report binary used to emit validation-bound MSL outputs.",
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


def bytes_sha256(value):
    return hashlib.sha256(value).hexdigest()


def stable_json_sha256(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return bytes_sha256(payload)


def repo_relative(path):
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def command_version(command, fallback):
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return fallback
    if proc.returncode != 0:
        return fallback
    text = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
    return text.splitlines()[0].strip() if text else fallback


def git_revision():
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def normalize_schema_target(target):
    if target == "spv":
        return "spirv"
    if target == "spirv":
        return "spirv"
    if target in {"msl", "hlsl", "dxil"}:
        return target
    return target


def infer_shader_stage(shader_path):
    try:
        source = Path(shader_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "mixed"
    stages = []
    for marker, stage in (
        ("@compute", "compute"),
        ("@vertex", "vertex"),
        ("@fragment", "fragment"),
    ):
        if marker in source:
            stages.append(stage)
    return stages[0] if len(stages) == 1 else "mixed"


def validation_result_not_run(reason):
    return {
        "status": "not_run",
        "tool": "",
        "reason": reason,
    }


def validate_msl_output(path):
    try:
        find_proc = subprocess.run(
            ["xcrun", "-find", "metal"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return validation_result_not_run("xcrun unavailable")

    metal_path = find_proc.stdout.strip()
    if find_proc.returncode != 0 or not metal_path:
        return validation_result_not_run("metal compiler unavailable")

    with tempfile.TemporaryDirectory(prefix="doe-tint-msl-validate-") as tmpdir:
        air_path = Path(tmpdir) / "shader.air"
        proc = subprocess.run(
            ["xcrun", "-sdk", "macosx", "metal", "-c", str(path), "-o", str(air_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        diagnostic = (proc.stderr or proc.stdout or "metal validation failed").strip()
        return {
            "status": "failed",
            "tool": "xcrun metal",
            "reason": diagnostic[:500],
        }
    return {
        "status": "passed",
        "tool": "xcrun metal",
        "reason": "",
    }


def make_compiler_result(
    *,
    status,
    diagnostic_code,
    output_sha256=None,
    ir_sha256=None,
    validation_status="not_run",
    validation_tool="",
    phase_total_ns=0,
    receipt_path="",
):
    timings = {"total": int(phase_total_ns)} if status == "ok" and phase_total_ns else {}
    return {
        "status": status,
        "diagnosticCode": diagnostic_code,
        "outputSha256": output_sha256 if status == "ok" else None,
        "irSha256": ir_sha256 if status == "ok" else None,
        "validationStatus": validation_status,
        "validationTool": validation_tool,
        "phaseTimingsNs": timings,
        "receiptPath": receipt_path if status == "ok" else "",
    }


def get_record_total_ns(record, side):
    if not record or record.get("status") != "compared":
        return 0
    if side == "doe":
        return int(record.get("baseline", {}).get("p50_ns", 0) or 0)
    warm_total = int(record.get("comparison", {}).get("warm", {}).get("p50_ns", 0) or 0)
    if warm_total:
        return warm_total
    return int(record.get("comparison", {}).get("p50_ns", 0) or 0)


def compile_doe_evidence_output(shader, target, record, evidence_dir, doe_emit_binary, dry_run):
    if normalize_schema_target(target) != "msl":
        return make_compiler_result(
            status="unsupported",
            diagnostic_code="doe_evidence_only_supports_msl_output",
        )
    if dry_run:
        return make_compiler_result(
            status="unsupported",
            diagnostic_code="dry_run_no_doe_output",
        )

    doe_bin = REPO_ROOT / doe_emit_binary
    if not doe_bin.is_file():
        return make_compiler_result(
            status="failed",
            diagnostic_code="missing_doe_emit_binary",
        )

    row_dir = evidence_dir / shader["name"] / "doe"
    row_dir.mkdir(parents=True, exist_ok=True)
    output_path = row_dir / "output.msl"
    receipt_path = row_dir / "compile-report.json"
    cmd = [
        str(doe_bin),
        "--shader-path",
        shader["path"],
        "--shader-name",
        shader["name"],
        "--emit-msl",
        str(output_path),
        "--out",
        str(receipt_path),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0 or not output_path.is_file():
        diagnostic_path = row_dir / "compile.stderr.txt"
        diagnostic_path.write_text(proc.stderr or proc.stdout or "Doe compile failed", encoding="utf-8")
        return make_compiler_result(
            status="failed",
            diagnostic_code="doe_compile_failed",
        )

    validation = validate_msl_output(output_path)
    if validation["status"] != "passed":
        return make_compiler_result(
            status="failed",
            diagnostic_code=f"doe_msl_validation_{validation['status']}",
        )

    phase_total_ns = get_record_total_ns(record, "doe")
    if phase_total_ns <= 0:
        return make_compiler_result(
            status="failed",
            diagnostic_code="missing_doe_timing_evidence",
        )

    return make_compiler_result(
        status="ok",
        diagnostic_code="",
        output_sha256=file_sha256(output_path),
        ir_sha256=file_sha256(receipt_path) if receipt_path.is_file() else None,
        validation_status="passed",
        validation_tool=validation["tool"],
        phase_total_ns=phase_total_ns,
        receipt_path=repo_relative(receipt_path),
    )


def compile_tint_evidence_output(cfg, shader, target, record, evidence_dir, dry_run):
    schema_target = normalize_schema_target(target)
    if schema_target != "msl":
        return make_compiler_result(
            status="unsupported",
            diagnostic_code="tint_evidence_only_supports_msl_output",
        )
    if dry_run:
        return make_compiler_result(
            status="unsupported",
            diagnostic_code="dry_run_no_tint_output",
        )

    tint_bin = REPO_ROOT / cfg["comparison"]["binaryPath"]
    if not tint_bin.is_file():
        return make_compiler_result(
            status="failed",
            diagnostic_code="missing_tint_binary",
        )

    row_dir = evidence_dir / shader["name"] / "tint"
    row_dir.mkdir(parents=True, exist_ok=True)
    output_path = row_dir / "output.msl"
    stderr_path = row_dir / "compile.stderr.txt"
    cmd = [str(tint_bin), "--format=msl", shader["path"]]
    proc = subprocess.run(cmd, check=False, capture_output=True)
    if proc.returncode != 0:
        stderr_path.write_bytes(proc.stderr or proc.stdout or b"Tint compile failed")
        return make_compiler_result(
            status="failed",
            diagnostic_code="tint_compile_failed",
        )

    output_path.write_bytes(proc.stdout)
    validation = validate_msl_output(output_path)
    if validation["status"] != "passed":
        return make_compiler_result(
            status="failed",
            diagnostic_code=f"tint_msl_validation_{validation['status']}",
        )

    phase_total_ns = get_record_total_ns(record, "tint")
    if phase_total_ns <= 0:
        return make_compiler_result(
            status="failed",
            diagnostic_code="missing_tint_timing_evidence",
        )

    return make_compiler_result(
        status="ok",
        diagnostic_code="",
        output_sha256=file_sha256(output_path),
        validation_status="passed",
        validation_tool=validation["tool"],
        phase_total_ns=phase_total_ns,
        receipt_path=repo_relative(output_path),
    )


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

    if dry_run:
        for shader in shaders:
            benchmark_name = preferred_tint_warm_benchmark_name(shader)
            command = build_tint_warm_command(
                warm_bin,
                benchmark_prefix,
                benchmark_name,
                min_time,
                repetitions,
            )
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

    results = {}
    for shader in shaders:
        benchmark_name = preferred_tint_warm_benchmark_name(shader)
        command = build_tint_warm_command(
            warm_bin,
            benchmark_prefix,
            benchmark_name,
            min_time,
            repetitions,
        )
        proc = subprocess.run(command, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            diagnostic = (proc.stderr or proc.stdout or "tint_benchmark failed").strip()
            print(
                f"  warning: tint_benchmark failed on {shader['name']}: {diagnostic[:200]}",
                file=sys.stderr,
            )
            continue
        try:
            payload = parse_google_benchmark_json(proc.stdout)
        except ValueError as exc:
            print(
                f"  warning: tint_benchmark JSON parse failed on {shader['name']}: {exc}",
                file=sys.stderr,
            )
            continue

        aliases = tint_warm_benchmark_aliases(shader)
        samples = []
        for benchmark in payload.get("benchmarks", []):
            if benchmark.get("run_type") != "iteration":
                continue
            name = benchmark.get("name", "")
            if not name.startswith(f"{benchmark_prefix}/"):
                continue
            short_name = name.split("/", 1)[1]
            if short_name not in aliases:
                continue
            sample_ns = duration_to_ns(benchmark.get("real_time"), benchmark.get("time_unit"))
            if sample_ns is not None:
                samples.append(sample_ns)
        if not samples:
            continue
        result = ns_stats(samples)
        result["timingNote"] = "in-process tint_benchmark real_time samples"
        results[shader["name"]] = result
    return results


def build_tint_warm_command(warm_bin, benchmark_prefix, benchmark_name, min_time, repetitions):
    return [
        str(warm_bin),
        f"--benchmark_filter=^{benchmark_prefix}/{google_benchmark_filter_literal(benchmark_name)}$",
        f"--benchmark_min_time={min_time}",
        f"--benchmark_repetitions={repetitions}",
        "--benchmark_report_aggregates_only=false",
        "--benchmark_format=json",
    ]


def google_benchmark_filter_literal(value):
    special = set(".+*?^$()[]{}|\\")
    return "".join(f"\\{char}" if char in special else char for char in str(value))


def parse_google_benchmark_json(text):
    start = text.find("{")
    if start < 0:
        raise ValueError("missing JSON object")
    return json.loads(text[start:])


def preferred_tint_warm_benchmark_name(shader):
    benchmark_name = str(shader.get("benchmarkName", "")).strip()
    if benchmark_name:
        return benchmark_name
    workload_id = str(shader.get("workloadId", "")).strip()
    if workload_id:
        return f"{workload_id}.wgsl"
    path_name = Path(str(shader.get("path", ""))).name
    return path_name or str(shader["name"])


def tint_warm_benchmark_aliases(shader):
    aliases = {
        str(shader.get("name", "")).strip(),
        str(shader.get("benchmarkName", "")).strip(),
    }
    path_name = Path(str(shader.get("path", ""))).name
    if path_name:
        aliases.add(path_name)
    workload_id = str(shader.get("workloadId", "")).strip()
    if workload_id:
        aliases.add(workload_id)
        aliases.add(f"{workload_id}.wgsl")
    return {alias for alias in aliases if alias}


def build_tint_warm_alias_map(shaders):
    alias_to_shader = {}
    collisions = {}
    for shader in shaders:
        shader_name = shader["name"]
        for alias in tint_warm_benchmark_aliases(shader):
            existing = alias_to_shader.get(alias)
            if existing and existing != shader_name:
                collisions.setdefault(alias, {existing}).add(shader_name)
                continue
            alias_to_shader[alias] = shader_name
    if collisions:
        details = ", ".join(
            f"{alias}: {sorted(names)}" for alias, names in sorted(collisions.items())
        )
        raise RuntimeError(f"ambiguous Tint warm benchmark aliases: {details}")
    return alias_to_shader


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


def build_toolchain_info(cfg, args):
    doe_emit_path = REPO_ROOT / args.doe_emit_binary
    tint_path = REPO_ROOT / cfg["comparison"]["binaryPath"]
    revision = git_revision()
    return {
        "doe": {
            "name": "doe-wgsl",
            "version": command_version([str(doe_emit_path), "--version"], revision)
            if doe_emit_path.is_file()
            else "missing",
            "command": [repo_relative(doe_emit_path), "--emit-msl"],
            "sourceRevision": revision,
            "artifactPath": repo_relative(doe_emit_path) if doe_emit_path.exists() else "",
            "artifactSha256": file_sha256(doe_emit_path) if doe_emit_path.is_file() else None,
        },
        "tint": {
            "name": "tint",
            "version": command_version([str(tint_path), "--version"], "dawn-vendor")
            if tint_path.is_file()
            else "missing",
            "command": [repo_relative(tint_path), "--format=msl"],
            "sourceRevision": "dawn-vendor",
            "artifactPath": repo_relative(tint_path) if tint_path.exists() else "",
            "artifactSha256": file_sha256(tint_path) if tint_path.is_file() else None,
        },
    }


def build_claimability(record, claim_workload, comparable):
    delta = {}
    if record:
        delta = record.get("warmDeltaPercent") or record.get("deltaPercent") or {}
    claim_reasons = []
    if not comparable:
        claim_reasons.append("row is not comparable")
    if not record or record.get("status") != "compared":
        claim_reasons.append(f"row not compared: {record.get('reason', 'missing record') if record else 'missing record'}")
    if not record or not record.get("comparison", {}).get("warm", {}).get("p50_ns"):
        claim_reasons.append("missing in-process Tint warm timing evidence")
    if claim_workload:
        claim_reasons.extend(str(reason) for reason in claim_workload.get("reasons", []))
        if not claim_workload.get("claimable"):
            claim_reasons.append("legacy claim gate did not mark the row claimable")
    else:
        claim_reasons.append("missing claim gate workload result")

    deduped_reasons = []
    for reason in claim_reasons:
        if reason and reason not in deduped_reasons:
            deduped_reasons.append(reason)

    if comparable and claim_workload and claim_workload.get("claimable") and not deduped_reasons:
        return {
            "status": "claimable",
            "reasons": [],
            "deltaPercent": {
                "p50": delta.get("p50"),
                "p95": delta.get("p95"),
                "p99": delta.get("p99"),
            },
        }
    return {
        "status": "diagnostic",
        "reasons": deduped_reasons or ["row is diagnostic"],
        "deltaPercent": {
            "p50": delta.get("p50"),
            "p95": delta.get("p95"),
            "p99": delta.get("p99"),
        },
    }


def build_row_comparability(record, doe_result, tint_result):
    reasons = []
    if not record or record.get("status") != "compared":
        reasons.append(f"row not compared: {record.get('reason', 'missing record') if record else 'missing record'}")
    if doe_result.get("status") != "ok":
        reasons.append(f"doe evidence status: {doe_result.get('diagnosticCode') or doe_result.get('status')}")
    if tint_result.get("status") != "ok":
        reasons.append(f"tint evidence status: {tint_result.get('diagnosticCode') or tint_result.get('status')}")
    if record and not record.get("comparison", {}).get("warm", {}).get("p50_ns"):
        reasons.append("missing in-process Tint warm timing evidence")

    deduped_reasons = []
    for reason in reasons:
        if reason and reason not in deduped_reasons:
            deduped_reasons.append(reason)
    if not deduped_reasons:
        return {"status": "comparable", "reasons": []}
    return {"status": "diagnostic", "reasons": deduped_reasons}


def build_evidence_report(cfg, shaders, target, records, claim_report, args):
    evidence_out = REPO_ROOT / args.evidence_out
    evidence_dir = evidence_out.with_name(f"{evidence_out.stem}.artifacts")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    records_by_shader = {record.get("shader"): record for record in records}
    claim_by_shader = {}
    if claim_report:
        claim_by_shader = {workload.get("shader"): workload for workload in claim_report.get("workloads", [])}

    rows = []
    tool_gap_codes = {gap["name"]: gap["code"] for gap in cfg.get("_toolGaps", [])}
    for shader in shaders:
        record = records_by_shader.get(shader["name"])
        shader_target = normalize_schema_target(shader.get("target", target))
        source_sha = file_sha256(shader["path"])
        if tool_gap_codes:
            doe_result = make_compiler_result(
                status="failed",
                diagnostic_code=tool_gap_codes.get("doe", "tool_preflight_blocked"),
            )
            tint_result = make_compiler_result(
                status="failed",
                diagnostic_code=(
                    tool_gap_codes.get("tint")
                    or tool_gap_codes.get("tintWarm")
                    or "tool_preflight_blocked"
                ),
            )
        else:
            doe_result = compile_doe_evidence_output(
                shader,
                shader_target,
                record,
                evidence_dir,
                args.doe_emit_binary,
                args.dry_run,
            )
            tint_result = compile_tint_evidence_output(
                cfg,
                shader,
                shader_target,
                record,
                evidence_dir,
                args.dry_run,
            )
        comparability = build_row_comparability(record, doe_result, tint_result)
        claimability = build_claimability(
            record,
            claim_by_shader.get(shader["name"]),
            comparability["status"] == "comparable",
        )
        rows.append(
            {
                "shaderId": shader.get("workloadId", shader["name"]),
                "sourceSha256": source_sha,
                "target": shader_target,
                "shaderStage": infer_shader_stage(shader["path"]),
                "doe": doe_result,
                "tint": tint_result,
                "comparability": comparability,
                "claimability": claimability,
            }
        )

    comparable_rows = sum(1 for row in rows if row["comparability"]["status"] == "comparable")
    claimable_rows = sum(1 for row in rows if row["claimability"]["status"] == "claimable")
    summary_reasons = []
    for gap_kind in ("_sourceGaps", "_toolGaps"):
        for gap in cfg.get(gap_kind, []):
            code = gap.get("code", "preflight_gap")
            path = gap.get("path", "")
            summary_reasons.append(f"{code}: {path}" if path else code)
    for row in rows:
        summary_reasons.extend(row["comparability"]["reasons"])
        summary_reasons.extend(row["claimability"]["reasons"])
    summary_reasons = list(dict.fromkeys(reason for reason in summary_reasons if reason))

    corpus_manifest = [
        {
            "shaderId": shader.get("workloadId", shader["name"]),
            "path": repo_relative(shader["path"]),
            "sha256": file_sha256(shader["path"]),
            "target": normalize_schema_target(shader.get("target", target)),
        }
        for shader in shaders
    ]
    report = {
        "schemaVersion": 1,
        "artifactKind": "tint-compiler-evidence",
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "comparisonStatus": "comparable" if rows and comparable_rows == len(rows) else "diagnostic",
        "claimStatus": "claimable" if rows and claimable_rows == len(rows) else "diagnostic",
        "corpus": {
            "id": cfg["run"].get("outStem", "doe-vs-tint"),
            "source": str(cfg.get("_sourceLabel", cfg.get("corpusDir", "bench/kernels/compilation-corpus"))),
            "sourceSha256": stable_json_sha256(corpus_manifest),
            "manifestPath": str(cfg.get("_configPath", "")),
        },
        "toolchains": build_toolchain_info(cfg, args),
        "phaseModel": {
            "timingScope": "whole-compile",
            "units": "ns",
            "requiredPhases": ["total"],
        },
        "rows": rows,
        "summary": {
            "rowCount": len(rows),
            "comparableRows": comparable_rows,
            "claimableRows": claimable_rows,
            "reasons": summary_reasons,
        },
    }
    evidence_out.parent.mkdir(parents=True, exist_ok=True)
    evidence_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def required_tool_gaps(cfg):
    gaps = []
    checks = [
        ("doe", REPO_ROOT / cfg["baseline"]["binaryPath"], "missing_doe_bench_binary"),
        ("tint", REPO_ROOT / cfg["comparison"]["binaryPath"], "missing_tint_binary"),
    ]
    warm_binary_path = cfg["comparison"].get("warmBinaryPath")
    if warm_binary_path:
        checks.append(("tintWarm", REPO_ROOT / warm_binary_path, "missing_tint_warm_binary"))
    for name, path, code in checks:
        if not path.is_file():
            gaps.append({"name": name, "path": str(path), "code": code})
    return gaps


def source_gaps_for_config(cfg):
    gaps = []
    script_path = cfg.get("tintBenchmarkInputsScriptPath")
    if script_path:
        path = REPO_ROOT / script_path
        if not path.is_file():
            gaps.append(
                {
                    "name": "tintBenchmarkInputsScript",
                    "path": str(path),
                    "code": "missing_tint_benchmark_input_script",
                }
            )
    return gaps


def evidence_args_for_target(args, target, targets):
    if not args.evidence_out or len(targets) == 1:
        return args
    cloned = argparse.Namespace(**vars(args))
    evidence_out = Path(args.evidence_out)
    cloned.evidence_out = str(evidence_out.with_name(f"{evidence_out.stem}.{target}{evidence_out.suffix}"))
    return cloned


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

    source_gaps = source_gaps_for_config(cfg)
    if source_gaps and args.evidence_out:
        shaders = []
        source_label = cfg["tintBenchmarkInputsScriptPath"]
    elif source_gaps:
        gap = source_gaps[0]
        print(f"error: {gap['code']}: {gap['path']}", file=sys.stderr)
        sys.exit(1)
    elif "tintBenchmarkInputsScriptPath" in cfg:
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
    cfg["_sourceLabel"] = source_label

    for target in targets:
        print(f"\n=== target: {target} ===")
        target_evidence_args = evidence_args_for_target(args, target, targets)

        doe_out = REPO_ROOT / out_dir / f"doe-{target}.ndjson"
        os.makedirs(doe_out.parent, exist_ok=True)

        if source_gaps and target_evidence_args.evidence_out:
            cfg["_sourceGaps"] = source_gaps
            for gap in source_gaps:
                print(f"diagnostic: {gap['code']}: {gap['path']}", file=sys.stderr)
            evidence_report = build_evidence_report(
                cfg,
                shaders,
                target,
                [],
                None,
                target_evidence_args,
            )
            print(
                f"wrote diagnostic compiler evidence: {REPO_ROOT / target_evidence_args.evidence_out} "
                f"status: {evidence_report['claimStatus']}"
            )
            cfg.pop("_sourceGaps", None)
            continue

        tool_gaps = required_tool_gaps(cfg)
        if tool_gaps and target_evidence_args.evidence_out:
            cfg["_toolGaps"] = tool_gaps
            for gap in tool_gaps:
                print(f"diagnostic: {gap['code']}: {gap['path']}", file=sys.stderr)
            records = build_report(cfg, shaders, target, {}, {})
            gap_reason = ",".join(gap["code"] for gap in tool_gaps)
            for record in records:
                if record.get("status") == "skipped":
                    record["reason"] = gap_reason
            evidence_report = build_evidence_report(
                cfg,
                shaders,
                target,
                records,
                None,
                target_evidence_args,
            )
            print(
                f"wrote diagnostic compiler evidence: {REPO_ROOT / target_evidence_args.evidence_out} "
                f"status: {evidence_report['claimStatus']}"
            )
            cfg.pop("_toolGaps", None)
            continue
        cfg.pop("_toolGaps", None)

        doe_results, calibration = run_doe_bench(cfg, shaders, target, doe_out, args.dry_run)
        tint_results = run_tint_bench(cfg, shaders, target, iterations, warmup, args.dry_run)

        records = build_report(cfg, shaders, target, doe_results, tint_results)

        report_path = REPO_ROOT / out_dir / f"{out_stem}.{target}.ndjson"
        write_report(records, report_path)
        print_summary(records, target)

        claim_report = None
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

        if target_evidence_args.evidence_out:
            evidence_report = build_evidence_report(
                cfg,
                shaders,
                target,
                records,
                claim_report,
                target_evidence_args,
            )
            print(
                f"\nwrote compiler evidence: {REPO_ROOT / target_evidence_args.evidence_out} "
                f"status: {evidence_report['claimStatus']}"
            )


if __name__ == "__main__":
    main()
