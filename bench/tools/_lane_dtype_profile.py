"""Canonical lane / dtype profile contract for Doppler manifests.

Doppler manifests declare per-role dtypes under `quantizationInfo`:

  - weights      : weight quantization (e.g. "q4k", "f16")
  - embeddings   : embedding-table dtype (e.g. "f16", "bf16")
  - lmHead       : LM head dtype (optional; defaults to weights when absent)
  - compute      : activation / math / accum / output dtype (e.g. "f32", "f16")
  - layout       : memory layout descriptor ("row")
  - variantTag   : denormalized lane key (e.g. "q4k-ehf16-af32",
                   "q4k-ehf16-af16", "q4k-ef16-af32")

Doe ingest reads these fields directly. `variantTag` is the canonical lane
key used by:

  - frozen-reference fixture validators (`--lane-key` match)
  - receipt path-suffix convention (`af32`, `af16`, ...)
  - `dtypeProfile` metadata fields on receipts and fixture manifests

Lane-suffix convention for new receipt / fixture paths:

  - `af32` for compute = "f32"
  - `af16` for compute = "f16"
  - `abf16` for compute = "bf16" (reserved; not currently used)

Pre-existing af32 receipts and fixtures keep their current paths
(`r3-1-31b-*`, `r3-1-31b-doppler-frozen/`, ...) for backward compatibility.
New non-af32 lanes must carry the lane suffix in their path
(`r3-1-31b-af16-*`, `r3-1-31b-doppler-frozen-af16/`) so an aggregator that
globs by model id can split lanes by path. Receipts and fixture manifests
also carry the canonical `dtypeProfile` field so cross-lane confusion can
be detected post-hoc even when paths drift.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LaneDtypeProfileError(ValueError):
    """Raised when a manifest's quantizationInfo violates the lane contract."""


_REQUIRED_FIELDS = ("weights", "embeddings", "compute", "variantTag")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CSL_CONTRACTS_PATH = _REPO_ROOT / "config/doe-csl-dtype-contracts.json"


def canonical_dtype_profile(
    quantization_info: dict[str, Any] | None,
) -> dict[str, str]:
    """Project a manifest's `quantizationInfo` into the canonical lane profile.

    Required fields (raises LaneDtypeProfileError if missing): weights,
    embeddings, compute, variantTag. Optional: lmHead — defaults to
    weights when absent.
    """
    if quantization_info is None:
        raise LaneDtypeProfileError("quantizationInfo is absent")
    if not isinstance(quantization_info, dict):
        raise LaneDtypeProfileError(
            "quantizationInfo must be a dict, got "
            f"{type(quantization_info).__name__}"
        )
    missing = [f for f in _REQUIRED_FIELDS if not quantization_info.get(f)]
    if missing:
        raise LaneDtypeProfileError(
            "quantizationInfo missing required fields: " + ", ".join(missing)
        )
    profile = {
        "weights": str(quantization_info["weights"]),
        "embeddings": str(quantization_info["embeddings"]),
        "lmHead": str(
            quantization_info.get("lmHead") or quantization_info["weights"]
        ),
        "compute": str(quantization_info["compute"]),
        "variantTag": str(quantization_info["variantTag"]),
    }
    return profile


def lane_key(quantization_info: dict[str, Any] | None) -> str:
    """Return the canonical lane key (variantTag) for a manifest."""
    return canonical_dtype_profile(quantization_info)["variantTag"]


def lane_suffix(quantization_info: dict[str, Any] | None) -> str:
    """Return the activation-dtype suffix (e.g. 'af32', 'af16') for new
    receipt / fixture paths. Pre-existing af32 paths are not renamed; new
    non-af32 lanes carry this suffix.
    """
    profile = canonical_dtype_profile(quantization_info)
    return f"a{profile['compute'].lower()}"


def receipt_path_lane_suffix(
    quantization_info: dict[str, Any] | None,
) -> str:
    """Suffix that NEW receipt-path writers append for non-af32 lanes.

    Returns empty string for af32 to preserve existing receipt-path
    conventions (e.g. `bench/out/r3-1-31b-*`). Returns the lane suffix
    (e.g. `af16`) for non-af32 lanes so new receipts land at e.g.
    `bench/out/r3-1-31b-af16-*`.
    """
    suffix = lane_suffix(quantization_info)
    if suffix == "af32":
        return ""
    return suffix


def assert_lane_match(
    expected_lane_key: str,
    fixture_dtype_profile: dict[str, Any] | None,
    *,
    permissive_when_absent: bool = True,
) -> None:
    """Raise LaneDtypeProfileError if expected_lane_key does not match a
    fixture-side dtypeProfile.variantTag.

    Behavior when fixture_dtype_profile is None (legacy fixture without the
    field) is governed by permissive_when_absent. Default True preserves
    backward compatibility with fixtures captured before this contract
    landed (notably `bench/fixtures/r3-1-31b-doppler-frozen/`). Pass
    False at receipt-emit time for new lanes, where dtypeProfile presence
    must be enforced.
    """
    if fixture_dtype_profile is None:
        if permissive_when_absent:
            return
        raise LaneDtypeProfileError(
            "fixture manifest carries no dtypeProfile; cannot validate lane "
            "key (expected_lane_key="
            f"{expected_lane_key!r})"
        )
    actual = fixture_dtype_profile.get("variantTag")
    if actual != expected_lane_key:
        raise LaneDtypeProfileError(
            f"lane key mismatch: expected {expected_lane_key!r}, "
            f"fixture dtypeProfile.variantTag={actual!r}"
        )


def load_csl_dtype_contracts(
    path: Path = _DEFAULT_CSL_CONTRACTS_PATH,
) -> dict[str, Any]:
    """Load the Doe/Cerebras CSL dtype contract registry."""
    return json.loads(path.read_text(encoding="utf-8"))


def csl_dtype_contract_for_profile(
    dtype_profile: dict[str, Any],
    *,
    model_id: str | None = None,
    contracts_path: Path = _DEFAULT_CSL_CONTRACTS_PATH,
) -> dict[str, Any]:
    """Return the Doe/Cerebras CSL dtype contract for a lane profile.

    The match is explicit on `variantTag`, with optional modelId narrowing
    when the contract lists concrete model ids.
    """
    variant_tag = str(dtype_profile.get("variantTag") or "")
    if not variant_tag:
        raise LaneDtypeProfileError("dtypeProfile.variantTag is absent")
    registry = load_csl_dtype_contracts(contracts_path)
    for contract in registry.get("contracts") or []:
        if not isinstance(contract, dict):
            continue
        if contract.get("dopplerVariantTag") != variant_tag:
            continue
        model_ids = contract.get("modelIds") or []
        if model_id is not None and model_ids and model_id not in model_ids:
            continue
        return json.loads(json.dumps(contract))
    suffix = f" for modelId={model_id!r}" if model_id is not None else ""
    raise LaneDtypeProfileError(
        f"no Doe/Cerebras CSL dtype contract for variantTag={variant_tag!r}{suffix}"
    )
