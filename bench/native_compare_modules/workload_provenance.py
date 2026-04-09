"""Workload-manifest provenance and advisory freshness helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.tools import generate_backend_workloads as generate_backend_workloads_mod
from native_compare_modules.runner import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "bench" / "workloads" / "metadata" / "backend-workload-catalog.json"
OWNERSHIP_VALUES = {"standalone", "generated"}
FRESHNESS_VALUES = {"fresh", "stale", "unknown"}


@dataclass(frozen=True)
class WorkloadManifestProvenance:
    path: str
    sha256: str
    ownership: str
    input_freshness: str
    freshness_reason: str
    generator_id: str = ""
    generator_input_hash: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "path": self.path,
            "sha256": self.sha256,
            "ownership": self.ownership,
            "inputFreshness": self.input_freshness,
            "freshnessReason": self.freshness_reason,
        }
        if self.generator_id:
            payload["generatorId"] = self.generator_id
        if self.generator_input_hash:
            payload["generatorInputHash"] = self.generator_input_hash
        if self.generated_at:
            payload["generatedAt"] = self.generated_at
        return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid workload manifest: expected object at {path}")
    return payload


def _relative_repo_path(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None


def _inferred_ownership(path: Path) -> str:
    relative_path = _relative_repo_path(path)
    if relative_path is None or not CATALOG_PATH.exists():
        return "standalone"
    catalog = generate_backend_workloads_mod.load_json(CATALOG_PATH)
    lane_outputs = catalog.get("laneOutputs", {})
    if not isinstance(lane_outputs, dict):
        return "standalone"
    for lane_entry in lane_outputs.values():
        if not isinstance(lane_entry, dict):
            continue
        if lane_entry.get("outputPath") == relative_path:
            return "generated"
    return "standalone"


def _normalized_ownership(payload: dict[str, Any], path: Path) -> str:
    raw_value = payload.get("ownership")
    if raw_value is None:
        return _inferred_ownership(path)
    value = str(raw_value).strip().lower()
    if value not in OWNERSHIP_VALUES:
        raise ValueError(
            f"invalid workload manifest ownership {raw_value!r} at {path}; "
            f"expected one of {sorted(OWNERSHIP_VALUES)}"
        )
    return value


def _generated_manifest_lane_id(path: Path) -> str | None:
    if not CATALOG_PATH.exists():
        return None
    relative_path = _relative_repo_path(path)
    if relative_path is None:
        return None
    catalog = generate_backend_workloads_mod.load_json(CATALOG_PATH)
    lane_outputs = catalog.get("laneOutputs", {})
    if not isinstance(lane_outputs, dict):
        return None
    for lane_id, lane_entry in lane_outputs.items():
        if not isinstance(lane_entry, dict):
            continue
        if lane_entry.get("outputPath") == relative_path:
            return str(lane_id)
    return None


def _generated_manifest_freshness(
    path: Path,
    payload: dict[str, Any],
) -> tuple[str, str]:
    lane_id = _generated_manifest_lane_id(path)
    if lane_id is None:
        return (
            "unknown",
            "generated manifest has no matching lane entry in "
            "bench/workloads/metadata/backend-workload-catalog.json",
        )
    catalog = generate_backend_workloads_mod.load_json(CATALOG_PATH)
    expected_payload = generate_backend_workloads_mod.materialize_lane(catalog, lane_id)
    if payload == expected_payload:
        return (
            "fresh",
            f"manifest matches generated lane {lane_id} from backend workload catalog",
        )
    return (
        "stale",
        f"manifest differs from generated lane {lane_id} in backend workload catalog",
    )


def workload_manifest_provenance(path: str | Path) -> WorkloadManifestProvenance:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"workload manifest not found: {manifest_path}")
    payload = _load_json(manifest_path)
    ownership = _normalized_ownership(payload, manifest_path)
    generator_id = str(payload.get("generatorId", "")).strip()
    generator_input_hash = str(payload.get("generatorInputHash", "")).strip()
    generated_at = str(payload.get("generatedAt", "")).strip()

    if ownership == "generated":
        input_freshness, freshness_reason = _generated_manifest_freshness(
            manifest_path,
            payload,
        )
        if not generator_id:
            generator_id = "bench.tools.generate_backend_workloads:materialize_lane"
        if not generator_input_hash and CATALOG_PATH.exists():
            generator_input_hash = file_sha256(CATALOG_PATH)
        if not generated_at and CATALOG_PATH.exists():
            generated_at = datetime.fromtimestamp(
                CATALOG_PATH.stat().st_mtime,
                timezone.utc,
            ).isoformat()
    else:
        input_freshness = "unknown"
        freshness_reason = (
            "standalone manifest; no backend workload catalog freshness check applies"
        )

    if input_freshness not in FRESHNESS_VALUES:
        raise ValueError(
            f"invalid workload freshness {input_freshness!r} for {manifest_path}"
        )

    return WorkloadManifestProvenance(
        path=str(manifest_path),
        sha256=file_sha256(manifest_path),
        ownership=ownership,
        input_freshness=input_freshness,
        freshness_reason=freshness_reason,
        generator_id=generator_id,
        generator_input_hash=generator_input_hash,
        generated_at=generated_at,
    )
