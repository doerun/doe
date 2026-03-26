#!/usr/bin/env python3
"""Unified benchmark entry point.

Dispatches to the right harness script with the right config based on
a small number of human-friendly axes:

    python3 bench/run.py compare metal breadth
    python3 bench/run.py compare vulkan smoke
    python3 bench/run.py compile metal smoke
    python3 bench/run.py single metal --workload-id compute_dispatch_grid

Backend auto-detects from platform when omitted:
    python3 bench/run.py compare breadth   # metal on macOS, vulkan on Linux
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
CATALOG_PATH = BENCH_ROOT / "workloads" / "metadata" / "backend-workload-catalog.json"

# ── Harness → script mapping ────────────────────────────────────────────────

HARNESSES = {
    "compare": "bench/native-compare/compare_dawn_vs_doe.py",
    "single": "bench/single-runtime/run_bench.py",
    "compile": "bench/native-compare/compare_doe_vs_tint_compilation.py",
    "adhoc": "bench/native-compare/compare_runtimes.py",
}

# ── Backend auto-detection ───────────────────────────────────────────────────

BACKEND_ALIASES = {
    "metal": "apple.metal",
    "vulkan": "amd.vulkan",
    "d3d12": "local.d3d12",
}

PRESETS = [
    "smoke",
    "compare-dev",
    "compare",
    "frontier",
    "explore",
    "release",
    "breadth",
]


def detect_backend() -> str:
    system = platform.system()
    if system == "Darwin":
        return "metal"
    if system == "Windows":
        return "d3d12"
    return "vulkan"


# ── Config resolution ────────────────────────────────────────────────────────


def resolve_compare_config(backend: str, preset: str) -> Path:
    backend_key = BACKEND_ALIASES.get(backend, backend)
    config_name = f"compare_dawn_vs_doe.config.{backend_key}.{preset}.json"
    config_path = BENCH_ROOT / "native-compare" / config_name
    if not config_path.exists():
        available = sorted(
            p.name
            for p in (BENCH_ROOT / "native-compare").glob(
                f"compare_dawn_vs_doe.config.{backend_key}.*.json"
            )
        )
        print(f"ERROR: config not found: {config_name}", file=sys.stderr)
        if available:
            presets = [
                n.replace(f"compare_dawn_vs_doe.config.{backend_key}.", "").replace(
                    ".json", ""
                )
                for n in available
            ]
            print(
                f"  Available presets for {backend}: {', '.join(presets)}",
                file=sys.stderr,
            )
        sys.exit(1)
    return config_path


def resolve_compile_config(backend: str, preset: str) -> Path:
    backend_key = BACKEND_ALIASES.get(backend, backend)
    candidates = [
        BENCH_ROOT / "native-compare" / f"compare_doe_vs_tint.config.{backend_key}.{preset}.json",
        BENCH_ROOT / "native-compare" / f"compare_doe_vs_tint.config.{backend_key}.json",
        BENCH_ROOT / "native-compare" / "compare_doe_vs_tint.config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    print("ERROR: Doe-vs-Tint compilation config not found", file=sys.stderr)
    sys.exit(1)


# ── Staleness check ──────────────────────────────────────────────────────────


def check_workload_staleness(config_path: Path) -> None:
    """Warn if the workloads file is older than the catalog."""
    import json

    try:
        with open(config_path) as f:
            cfg = json.load(f)
        workloads_rel = cfg.get("workloads", "")
        if not workloads_rel:
            return
        workloads_path = REPO_ROOT / workloads_rel
        if (
            CATALOG_PATH.exists()
            and workloads_path.exists()
            and os.path.getmtime(CATALOG_PATH) > os.path.getmtime(workloads_path)
        ):
            print(
                f"WARNING: {workloads_path.name} may be stale — "
                f"workloads/metadata/backend-workload-catalog.json was modified more recently. "
                f"Run: python3 bench/tools/generate_backend_workloads.py",
                file=sys.stderr,
            )
    except (json.JSONDecodeError, KeyError, OSError):
        pass


# ── Dispatch ─────────────────────────────────────────────────────────────────


def build_command(
    harness: str, backend: str, preset: str, extra_args: list[str]
) -> list[str]:
    script = REPO_ROOT / HARNESSES[harness]

    if harness == "compare":
        config_path = resolve_compare_config(backend, preset)
        check_workload_staleness(config_path)
        return [sys.executable, str(script), "--config", str(config_path)] + extra_args

    if harness == "compile":
        config_path = resolve_compile_config(backend, preset)
        check_workload_staleness(config_path)
        return [sys.executable, str(script), "--config", str(config_path)] + extra_args

    if harness == "single":
        return [sys.executable, str(script), "--backend", backend] + extra_args

    # adhoc or anything else — pass through
    return [sys.executable, str(script)] + extra_args


def parse_positional(argv: list[str]) -> tuple[str, str, str, list[str]]:
    """Parse [harness] [backend] [preset] from positional args.

    All three are optional and auto-detected by matching against known values.
    Remaining args are passed through to the harness script.
    """
    harness = "compare"
    backend = detect_backend()
    preset = "smoke"
    positionals: list[str] = []
    extra: list[str] = []

    # Split into positionals (before first --flag) and extra (--flags onward)
    hit_flag = False
    for arg in argv:
        if hit_flag or arg.startswith("-"):
            hit_flag = True
            extra.append(arg)
        else:
            positionals.append(arg)

    for pos in positionals:
        if pos in HARNESSES:
            harness = pos
        elif pos in BACKEND_ALIASES:
            backend = pos
        elif pos in PRESETS:
            preset = pos
        else:
            print(
                f"ERROR: unknown argument '{pos}'.\n"
                f"  Harnesses: {', '.join(sorted(HARNESSES))}\n"
                f"  Backends:  {', '.join(sorted(BACKEND_ALIASES))}\n"
                f"  Presets:   {', '.join(PRESETS)}",
                file=sys.stderr,
            )
            sys.exit(1)

    return harness, backend, preset, extra


def print_help() -> None:
    print(
        """Usage: bench/run.py [harness] [backend] [preset] [-- extra-args...]

  Harnesses:  compare (default), single, compile, adhoc
  Backends:   metal, vulkan, d3d12  (auto-detected from platform)
  Presets:    smoke (default), compare-dev, compare, frontier,
              explore, release, breadth

Examples:
  bench/run.py                          # compare metal smoke (macOS default)
  bench/run.py breadth                  # compare metal breadth
  bench/run.py compare vulkan release   # explicit
  bench/run.py compile metal smoke      # compilation comparison
  bench/run.py single metal --workload-id compute_dispatch_grid
  bench/run.py compare metal --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.ir.json

Extra args after the positionals are forwarded to the harness script."""
    )


def main() -> int:
    argv = sys.argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        print_help()
        return 0

    harness, backend, preset, extra = parse_positional(argv)

    cmd = build_command(harness, backend, preset, extra)
    label = f"{harness} {backend} {preset}"
    print(f"→ {label}", file=sys.stderr)
    print(f"  {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
