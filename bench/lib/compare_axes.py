"""Canonical benchmark-surface helpers shared across bench control-plane tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# -- Canonical benchmark surfaces -------------------------------------------

SURFACE_SHORT_NAMES: dict[str, str] = {
    "backend": "backend",
    "plan": "plan",
    "package": "package",
    "dropin": "dropin",
    "browser": "browser",
    "compiler": "compiler",
}

SURFACE_FROM_SHORT: dict[str, str] = {v: k for k, v in SURFACE_SHORT_NAMES.items()}

SURFACE_TO_BOUNDARY = {
    "backend": "backend_native",
    "plan": "direct_plan",
    "package": "package_surface",
    "dropin": "abi_dropin",
    "browser": "browser",
    "compiler": "compiler",
}
BOUNDARY_TO_SURFACE = {v: k for k, v in SURFACE_TO_BOUNDARY.items()}


def surface_for_short(short: str) -> str:
    normalized = short.strip()
    if normalized in SURFACE_FROM_SHORT:
        return SURFACE_FROM_SHORT[normalized]
    if normalized in SURFACE_SHORT_NAMES:
        return normalized
    raise ValueError(f"unknown surface {short!r}")


def short_for_surface(surface: str) -> str:
    normalized = surface.strip()
    if normalized in SURFACE_SHORT_NAMES:
        return SURFACE_SHORT_NAMES[normalized]
    if normalized in SURFACE_FROM_SHORT:
        return normalized
    raise ValueError(f"unknown surface {surface!r}")


def boundary_for_surface(surface: str) -> str:
    normalized = surface.strip()
    try:
        return SURFACE_TO_BOUNDARY[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown compare surface {surface!r}") from exc


def surface_for_boundary(boundary: str) -> str:
    normalized = boundary.strip()
    try:
        return BOUNDARY_TO_SURFACE[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown compare boundary {boundary!r}") from exc


# -- Runtime host helpers ---------------------------------------------------

def runtime_host_for_surface(surface: str, package_runtime: str = "") -> str:
    normalized_surface = surface.strip()
    if normalized_surface in {"package", "package_surface"}:
        return package_runtime.strip() or "node"
    if normalized_surface in {
        "backend",
        "plan",
        "dropin",
        "browser",
        "compiler",
        "backend_native",
        "direct_plan",
        "abi_dropin",
    }:
        return "none"
    raise ValueError(f"unknown compare surface {surface!r}")


def derive_temperature(*, mode: str = "", temperature: str = "") -> str:
    return temperature.strip() or mode.strip() or "default"


# -- Product helpers (v2 taxonomy) ------------------------------------------

_DEFAULT_TAXONOMY_PATH = "config/compare-taxonomy.json"


def _load_taxonomy_axis(axis: str, taxonomy_path: str | Path) -> list[str]:
    p = Path(taxonomy_path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("axes", {}).get(axis, [])


def load_taxonomy_products(taxonomy_path: str | Path = _DEFAULT_TAXONOMY_PATH) -> list[str]:
    return _load_taxonomy_axis("products", taxonomy_path)


def load_taxonomy_surfaces(taxonomy_path: str | Path = _DEFAULT_TAXONOMY_PATH) -> list[str]:
    return _load_taxonomy_axis("surfaces", taxonomy_path)


# -- Compare-view helpers ---------------------------------------------------

@dataclass(frozen=True)
class ComparisonViewMeta:
    provider_set: str
    providers: tuple[str, ...]


PROVIDER_SETS: dict[str, tuple[str, ...]] = {
    "backend_native_providers": ("doe", "dawn", "webkit", "wgpu-native"),
    "direct_plan_providers": ("doe", "dawn", "webkit", "wgpu-native"),
    "package_node_providers": ("doe", "node-webgpu"),
    "package_bun_providers": ("doe", "bun-webgpu"),
    "package_deno_providers": ("doe", "deno-webgpu"),
}

COMPARISON_VIEWS: dict[str, ComparisonViewMeta] = {
    "doe_vs_dawn_delegate": ComparisonViewMeta(
        provider_set="backend_native_providers",
        providers=("doe", "dawn"),
    ),
    "doe_vs_dawn_direct": ComparisonViewMeta(
        provider_set="direct_plan_providers",
        providers=("doe", "dawn"),
    ),
    "doe_vs_node_webgpu_package": ComparisonViewMeta(
        provider_set="package_node_providers",
        providers=("doe", "node-webgpu"),
    ),
    "doe_vs_bun_webgpu_package": ComparisonViewMeta(
        provider_set="package_bun_providers",
        providers=("doe", "bun-webgpu"),
    ),
    "doe_vs_deno_webgpu_package": ComparisonViewMeta(
        provider_set="package_deno_providers",
        providers=("doe", "deno-webgpu"),
    ),
    "doe_vs_dawn": ComparisonViewMeta(
        provider_set="backend_native_providers",
        providers=("doe", "dawn"),
    ),
}


def derive_comparison_view(
    *,
    surface: str,
    runtime_host: str,
    comparison_view: str = "",
    provider_pair: str = "",
) -> str:
    if comparison_view.strip():
        return comparison_view.strip()
    if provider_pair.strip():
        return provider_pair.strip()
    normalized_surface = surface.strip()
    normalized_runtime = runtime_host.strip()
    if normalized_surface == "backend":
        return "doe_vs_dawn_delegate"
    if normalized_surface == "plan":
        return "doe_vs_dawn_direct"
    if normalized_surface == "package":
        if normalized_runtime == "bun":
            return "doe_vs_bun_webgpu_package"
        if normalized_runtime == "deno":
            return "doe_vs_deno_webgpu_package"
        return "doe_vs_node_webgpu_package"
    raise ValueError(
        "cannot derive comparison view for "
        f"surface={surface!r}, runtime_host={runtime_host!r}"
    )


def derive_provider_set(
    *,
    boundary: str,
    runtime_host: str,
    comparison_view: str = "",
) -> str:
    if comparison_view.strip():
        meta = COMPARISON_VIEWS.get(comparison_view.strip())
        if meta is not None:
            return meta.provider_set
    normalized_boundary = boundary.strip()
    normalized_runtime = runtime_host.strip()
    if normalized_boundary == "backend_native":
        return "backend_native_providers"
    if normalized_boundary == "direct_plan":
        return "direct_plan_providers"
    if normalized_boundary == "package_surface":
        if normalized_runtime == "bun":
            return "package_bun_providers"
        if normalized_runtime == "deno":
            return "package_deno_providers"
        return "package_node_providers"
    raise ValueError(
        "cannot derive provider set for "
        f"boundary={boundary!r}, runtime_host={runtime_host!r}"
    )


def providers_for_provider_set(provider_set: str) -> tuple[str, ...]:
    try:
        return PROVIDER_SETS[provider_set.strip()]
    except KeyError as exc:
        raise ValueError(f"unknown provider set {provider_set!r}") from exc


def providers_for_comparison_view(comparison_view: str) -> tuple[str, ...]:
    meta = COMPARISON_VIEWS.get(comparison_view.strip())
    if meta is not None:
        return meta.providers
    return ()
