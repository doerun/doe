#!/usr/bin/env python3
"""Config-backed front door for compare lanes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bench.lib import compare_axes as compare_axes_mod


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = REPO_ROOT / "config" / "promoted-compare-catalog.json"
DEFAULT_COMPARE_SCRIPT = REPO_ROOT / "bench" / "native-compare" / "compare_dawn_vs_doe.py"

DIRECT_SURFACE = "direct"
PACKAGE_SURFACE = "package"
NATIVE_SURFACE = "native"
DEFAULT_DIRECT_MODE = "default"
DEFAULT_PACKAGE_MODE = "cold"
DEFAULT_NATIVE_MODE = "default"
DEFAULT_PACKAGE_RUNTIME = "node"


@dataclass(frozen=True)
class PromotedCompareEntry:
    id: str
    backend: str
    boundary: str
    runtime_host: str
    temperature: str
    comparison_view: str
    provider_set: str
    providers: tuple[str, ...]
    surface: str
    package_runtime: str
    preset: str
    workload: str
    mode: str
    benchmark_class: str
    left_executor_id: str
    right_executor_id: str
    config_path: str
    description: str


def load_catalog(path: Path) -> list[PromotedCompareEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    result: list[PromotedCompareEntry] = []
    for raw in entries:
        surface = raw["surface"]
        package_runtime = raw.get(
            "packageRuntime",
            DEFAULT_PACKAGE_RUNTIME if surface == PACKAGE_SURFACE else "",
        )
        boundary = raw.get("boundary", compare_axes_mod.boundary_for_surface(surface))
        runtime_host = raw.get(
            "runtimeHost",
            compare_axes_mod.runtime_host_for_surface(surface, package_runtime),
        )
        temperature = raw.get("temperature", raw.get("mode", "default"))
        comparison_view = raw.get(
            "comparisonView",
            compare_axes_mod.derive_comparison_view(
                surface=surface,
                runtime_host=runtime_host,
                provider_pair=raw.get("providerPair", ""),
            ),
        )
        provider_set = raw.get(
            "providerSet",
            compare_axes_mod.derive_provider_set(
                boundary=boundary,
                runtime_host=runtime_host,
                comparison_view=comparison_view,
            ),
        )
        providers = tuple(
            raw.get("providers")
            or compare_axes_mod.providers_for_comparison_view(comparison_view)
            or compare_axes_mod.providers_for_provider_set(provider_set)
        )
        result.append(
            PromotedCompareEntry(
                id=raw["id"],
                backend=raw["backend"],
                boundary=boundary,
                runtime_host=runtime_host,
                temperature=temperature,
                comparison_view=comparison_view,
                provider_set=provider_set,
                providers=providers,
                surface=surface,
                package_runtime=package_runtime,
                preset=raw.get("preset", ""),
                workload=raw.get("workload", ""),
                mode=raw["mode"],
                benchmark_class=raw["benchmarkClass"],
                left_executor_id=raw["leftExecutorId"],
                right_executor_id=raw["rightExecutorId"],
                config_path=raw["configPath"],
                description=raw["description"],
            )
        )
    return result


def default_mode_for_surface(surface: str) -> str:
    if surface == PACKAGE_SURFACE:
        return DEFAULT_PACKAGE_MODE
    if surface == NATIVE_SURFACE:
        return DEFAULT_NATIVE_MODE
    return DEFAULT_DIRECT_MODE


def resolve_entry(
    entries: Sequence[PromotedCompareEntry],
    *,
    profile_id: str = "",
    backend: str = "",
    boundary: str = "",
    runtime_host: str = "",
    temperature: str = "",
    surface: str = "",
    preset: str = "",
    workload: str = "",
    mode: str = "",
    package_runtime: str = "",
) -> PromotedCompareEntry:
    if profile_id:
        for entry in entries:
            if entry.id == profile_id:
                return entry
        raise ValueError(f"unknown promoted compare profile {profile_id!r}")

    if not backend or (not surface and not boundary):
        raise ValueError(
            "resolve_entry requires either --profile or the tuple "
            "that identifies one catalog entry"
        )

    if boundary and surface:
        expected_surface = compare_axes_mod.surface_for_boundary(boundary)
        if expected_surface != surface:
            raise ValueError(
                "surface/boundary mismatch: "
                f"surface={surface!r} implies boundary={expected_surface!r}, "
                f"received boundary={boundary!r}"
            )
    effective_surface = surface or (
        compare_axes_mod.surface_for_boundary(boundary) if boundary else ""
    )
    effective_boundary = boundary or (
        compare_axes_mod.boundary_for_surface(surface) if surface else ""
    )
    if runtime_host and effective_surface and effective_surface != PACKAGE_SURFACE and runtime_host != "none":
        raise ValueError("--runtime-host applies only to package surfaces")
    if preset and workload:
        raise ValueError("resolve_entry accepts only one of --preset or --workload")
    if not preset and not workload:
        raise ValueError(
            "resolve_entry requires either --preset or --workload when --profile is omitted"
        )
    if package_runtime and effective_surface != PACKAGE_SURFACE:
        raise ValueError("--package-runtime applies only to --surface package")

    effective_mode = temperature or mode or default_mode_for_surface(effective_surface)
    effective_package_runtime = (
        package_runtime
        or (runtime_host if effective_surface == PACKAGE_SURFACE and runtime_host and runtime_host != "none" else "")
        or (DEFAULT_PACKAGE_RUNTIME if effective_surface == PACKAGE_SURFACE else "")
    )
    matches = [
        entry
        for entry in entries
        if entry.backend == backend
        and entry.surface == effective_surface
        and entry.boundary == effective_boundary
        and entry.runtime_host == compare_axes_mod.runtime_host_for_surface(
            effective_surface,
            effective_package_runtime,
        )
        and entry.package_runtime == effective_package_runtime
        and entry.preset == preset
        and entry.workload == workload
        and entry.temperature == effective_mode
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        target_name = "preset" if preset else "workload"
        target_value = preset or workload
        raise ValueError(
            "no promoted compare profile matches "
            f"backend={backend!r}, boundary={effective_boundary!r}, "
            f"runtime_host={compare_axes_mod.runtime_host_for_surface(effective_surface, effective_package_runtime)!r}, "
            f"{target_name}={target_value!r}, temperature={effective_mode!r}"
        )
    raise ValueError(
        "multiple promoted compare profiles matched "
        f"backend={backend!r}, boundary={effective_boundary!r}, preset={preset!r}, "
        f"workload={workload!r}, temperature={effective_mode!r}, "
        f"runtime_host={compare_axes_mod.runtime_host_for_surface(effective_surface, effective_package_runtime)!r}"
    )


def build_compare_argv(
    entry: PromotedCompareEntry,
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    compare_script: Path = DEFAULT_COMPARE_SCRIPT,
    passthrough: Sequence[str] = (),
) -> list[str]:
    raw_config_path = Path(entry.config_path)
    if raw_config_path.is_absolute():
        resolved_config_path = raw_config_path
    elif catalog_path.resolve() == DEFAULT_CATALOG_PATH.resolve():
        resolved_config_path = REPO_ROOT / raw_config_path
    else:
        catalog_relative = catalog_path.resolve().parent / raw_config_path
        repo_relative = REPO_ROOT / raw_config_path
        if catalog_relative.exists():
            resolved_config_path = catalog_relative
        elif repo_relative.exists():
            resolved_config_path = repo_relative
        else:
            resolved_config_path = catalog_relative
    return [
        sys.executable,
        str(compare_script),
        "--config",
        str(resolved_config_path),
        "--boundary",
        entry.boundary,
        "--runtime-host",
        entry.runtime_host,
        "--temperature",
        entry.temperature,
        "--comparison-view",
        entry.comparison_view,
        "--provider-set",
        entry.provider_set,
        "--left-provider-id",
        entry.providers[0],
        "--right-provider-id",
        entry.providers[1],
        *passthrough,
    ]


def parse_args(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run a promoted direct/package Doe-vs-Dawn compare profile."
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="Path to the promoted compare catalog JSON.",
    )
    parser.add_argument("--profile", default="", help="Exact promoted profile id.")
    parser.add_argument("--backend", default="", help="Promoted backend id, e.g. apple-metal.")
    parser.add_argument(
        "--boundary",
        choices=["backend_native", "direct_plan", "package_surface"],
        default="",
        help="Canonical compare boundary. Preferred over --surface.",
    )
    parser.add_argument(
        "--surface",
        choices=[NATIVE_SURFACE, DIRECT_SURFACE, PACKAGE_SURFACE],
        default="",
        help="Legacy promoted compare surface alias.",
    )
    parser.add_argument(
        "--preset",
        default="",
        help="Promoted preset alias for native compare surfaces, e.g. compare or release.",
    )
    parser.add_argument("--workload", default="", help="Promoted workload alias, e.g. gemma64.")
    parser.add_argument(
        "--runtime-host",
        choices=["none", DEFAULT_PACKAGE_RUNTIME, "bun", "deno"],
        default="",
        help="Canonical runtime host. Preferred over --package-runtime.",
    )
    parser.add_argument(
        "--package-runtime",
        choices=[DEFAULT_PACKAGE_RUNTIME, "bun", "deno"],
        default="",
        help="Legacy package runtime selector for package surfaces. Defaults to 'node'.",
    )
    parser.add_argument(
        "--temperature",
        choices=[DEFAULT_DIRECT_MODE, "cold", "warm"],
        default="",
        help="Canonical startup temperature. Preferred over --mode.",
    )
    parser.add_argument(
        "--mode",
        choices=[DEFAULT_DIRECT_MODE, "cold", "warm"],
        default="",
        help="Legacy promoted compare temperature alias.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List promoted compare profiles and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved compare command instead of executing it.",
    )
    return parser.parse_known_args(argv)


def format_entry(entry: PromotedCompareEntry) -> str:
    target_field = f"preset={entry.preset}" if entry.preset else f"workload={entry.workload}"
    package_runtime_field = (
        f" packageRuntime={entry.package_runtime}" if entry.package_runtime else ""
    )
    return (
        f"{entry.id}: backend={entry.backend} boundary={entry.boundary} "
        f"runtimeHost={entry.runtime_host} temperature={entry.temperature} "
        f"comparisonView={entry.comparison_view} providerSet={entry.provider_set} "
        f"{target_field}{package_runtime_field} class={entry.benchmark_class} "
        f"left={entry.left_executor_id} right={entry.right_executor_id} "
        f"config={entry.config_path}"
    )


def filter_entries(
    entries: Sequence[PromotedCompareEntry],
    *,
    backend: str = "",
    boundary: str = "",
    runtime_host: str = "",
    temperature: str = "",
    surface: str = "",
    preset: str = "",
    workload: str = "",
    mode: str = "",
    package_runtime: str = "",
) -> list[PromotedCompareEntry]:
    return [
        entry
        for entry in entries
        if (not backend or entry.backend == backend)
        and (not boundary or entry.boundary == boundary)
        and (not runtime_host or entry.runtime_host == runtime_host)
        and (not surface or entry.surface == surface)
        and (not preset or entry.preset == preset)
        and (not workload or entry.workload == workload)
        and (not temperature or entry.temperature == temperature)
        and (not mode or entry.temperature == mode)
        and (not package_runtime or entry.package_runtime == package_runtime)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    ns, passthrough = parse_args(sys.argv[1:] if argv is None else argv)
    catalog_path = Path(ns.catalog)
    entries = load_catalog(catalog_path)

    if ns.list:
        filtered = filter_entries(
            entries,
            backend=ns.backend,
            boundary=ns.boundary,
            runtime_host=ns.runtime_host,
            temperature=ns.temperature,
            surface=ns.surface,
            preset=ns.preset,
            workload=ns.workload,
            mode=ns.mode,
            package_runtime=ns.package_runtime,
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
            print(format_entry(entry))
        return 0

    entry = resolve_entry(
        entries,
        profile_id=ns.profile,
        backend=ns.backend,
        boundary=ns.boundary,
        runtime_host=ns.runtime_host,
        temperature=ns.temperature,
        surface=ns.surface,
        preset=ns.preset,
        workload=ns.workload,
        mode=ns.mode,
        package_runtime=ns.package_runtime,
    )
    argv_out = build_compare_argv(entry, catalog_path=catalog_path, passthrough=passthrough)
    if ns.dry_run:
        print(" ".join(argv_out))
        return 0
    os.execv(sys.executable, argv_out)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
