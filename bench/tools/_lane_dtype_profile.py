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
_CSL_DTYPE_CONTRACT_SCHEMA_VERSION = 2
_COMMON_CSL_DTYPES = {
    "activation": "f16",
    "kvCache": "f16",
    "kernelOutput": "f16",
    "embeddingTable": "f16",
    "q4kWeightStorage": "u8_q4k",
    "lmHeadActivation": "f16",
    "logits": "f32",
    "sampleTokenId": "u32",
}
_VARIANT_CSL_DTYPES = {
    "q4k-ehf16-af16": {
        "lmHeadWeight": "f16",
    },
    "q4k-eaf16": {
        "lmHeadWeight": "u8_q4k",
        "linearAttentionState": "f16",
        "ssmState": "f16",
        "recurrenceCarry": "f16",
    },
}
_VARIANT_CSL_ACCUMULATION_DTYPES = {
    "q4k-ehf16-af16": {
        "rmsNorm": "f16",
        "rope": "f16",
        "attention": "f16",
        "summaMatmul": "f16",
        "residual": "f16",
        "gatedActivation": "f16",
        "kvReadWrite": "f16",
        "fusedGemv": "f16",
        "denseLmHead": "f32",
        "sampleCompare": "f32",
    },
    "q4k-eaf16": {
        "rmsNorm": "f16",
        "qkNorm": "f16",
        "rope": "f16",
        "causalPrefillAttention": "f16",
        "summaMatmul": "f16",
        "residual": "f16",
        "swiglu": "f16",
        "conv1dDepthwise": "f16",
        "linearAttention": "f16",
        "deltaNet": "f16",
        "ssmRecurrence": "f16",
        "recurrenceCarry": "f16",
        "kvReadWrite": "f16",
        "fusedGemv": "f16",
        "lmHeadGemv": "f32",
        "sampleCompare": "f32",
    },
}
_VARIANT_CSL_KERNEL_CLASSES = {
    "q4k-ehf16-af16": {
        "rms_norm",
        "rope",
        "attention",
        "residual",
        "tiled_matmul",
        "prefill_q4k_gemv",
        "fused_gemv",
        "kv_read_write",
        "dense_lm_head",
        "sample",
    },
    "q4k-eaf16": {
        "rms_norm",
        "qk_norm",
        "rope",
        "causal_prefill_attention",
        "residual",
        "tiled_matmul",
        "prefill_q4k_gemv",
        "fused_gemv",
        "silu_gated",
        "conv1d_depthwise",
        "linear_attention",
        "delta_net",
        "ssm_recurrence",
        "kv_read_write",
        "lm_head_gemv",
        "sample",
    },
}
_CSL_F16_KERNEL_CLASSES = {
    "rms_norm",
    "qk_norm",
    "rope",
    "attention",
    "causal_prefill_attention",
    "residual",
    "tiled_matmul",
    "prefill_q4k_gemv",
    "fused_gemv",
    "silu_gated",
    "conv1d_depthwise",
    "linear_attention",
    "delta_net",
    "ssm_recurrence",
    "kv_read_write",
}
_CSL_KERNEL_CLASS_DTYPES = {
    **{
        name: {
            "inputDtype": "f16",
            "outputDtype": "f16",
            "accumulationDtype": "f16",
        }
        for name in _CSL_F16_KERNEL_CLASSES
    },
    "dense_lm_head": {
        "inputDtype": "f16",
        "outputDtype": "f32",
        "accumulationDtype": "f32",
    },
    "lm_head_gemv": {
        "inputDtype": "f16",
        "outputDtype": "f32",
        "accumulationDtype": "f32",
    },
    "sample": {
        "inputDtype": "f32",
        "outputDtype": "u32",
        "accumulationDtype": "f32",
    },
}


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


def _expect_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LaneDtypeProfileError(
            f"{label} must be a dict, got {type(value).__name__}"
        )
    return value


def _expect_exact_fields(
    mapping: dict[str, Any],
    expected: dict[str, str],
    label: str,
) -> None:
    for field, expected_value in expected.items():
        actual = mapping.get(field)
        if actual != expected_value:
            raise LaneDtypeProfileError(
                f"{label}.{field} must be {expected_value!r}, got {actual!r}"
            )


def validate_csl_dtype_contract(contract: dict[str, Any]) -> None:
    """Fail closed when a Doe/Cerebras f16 contract loses visible dtype policy."""
    variant_tag = str(contract.get("dopplerVariantTag") or "")
    if variant_tag not in _VARIANT_CSL_DTYPES:
        raise LaneDtypeProfileError(
            f"unknown Doe/Cerebras CSL dtype contract variantTag={variant_tag!r}"
        )
    if contract.get("backend") != "cerebras_csl":
        raise LaneDtypeProfileError("CSL dtype contract backend must be cerebras_csl")
    if contract.get("hostPlanActivationDtype") != "f16":
        raise LaneDtypeProfileError(
            "CSL dtype contract hostPlanActivationDtype must be 'f16'"
        )
    if contract.get("fallbackPolicy") != "forbid_implicit_af32":
        raise LaneDtypeProfileError(
            "CSL dtype contract must forbid implicit af32 fallback"
        )

    weights_ref_policy = _expect_mapping(
        contract.get("weightsRefPolicy"),
        "weightsRefPolicy",
    )
    if weights_ref_policy.get("preserveIdentity") is not True:
        raise LaneDtypeProfileError(
            "weightsRefPolicy.preserveIdentity must be true"
        )
    if weights_ref_policy.get("sharedQ4KWeightPacks") is not True:
        raise LaneDtypeProfileError(
            "weightsRefPolicy.sharedQ4KWeightPacks must be true"
        )

    host_transfer = _expect_mapping(contract.get("hostTransfer"), "hostTransfer")
    _expect_exact_fields(
        host_transfer,
        {
            "f16Encoding": "ieee_binary16",
            "logicalF16Transport": "memcpy32_packed_u32",
            "d2hCopyback": "logical_dtype_preserved",
        },
        "hostTransfer",
    )

    dtypes = _expect_mapping(contract.get("dtypes"), "dtypes")
    _expect_exact_fields(dtypes, _COMMON_CSL_DTYPES, "dtypes")
    _expect_exact_fields(dtypes, _VARIANT_CSL_DTYPES[variant_tag], "dtypes")

    accumulation_dtypes = _expect_mapping(
        contract.get("accumulationDtypes"),
        "accumulationDtypes",
    )
    _expect_exact_fields(
        accumulation_dtypes,
        _VARIANT_CSL_ACCUMULATION_DTYPES[variant_tag],
        "accumulationDtypes",
    )

    kernel_classes_raw = contract.get("kernelClasses")
    if not isinstance(kernel_classes_raw, list):
        raise LaneDtypeProfileError(
            "kernelClasses must be a list, got "
            f"{type(kernel_classes_raw).__name__}"
        )
    kernel_classes: dict[str, dict[str, Any]] = {}
    for entry in kernel_classes_raw:
        entry_mapping = _expect_mapping(entry, "kernelClasses[]")
        name = str(entry_mapping.get("name") or "")
        if name not in _CSL_KERNEL_CLASS_DTYPES:
            raise LaneDtypeProfileError(f"unknown CSL kernel class {name!r}")
        _expect_exact_fields(
            entry_mapping,
            _CSL_KERNEL_CLASS_DTYPES[name],
            f"kernelClasses[{name}]",
        )
        kernel_classes[name] = entry_mapping

    required_kernel_classes = _VARIANT_CSL_KERNEL_CLASSES[variant_tag]
    missing = sorted(required_kernel_classes - set(kernel_classes))
    if missing:
        raise LaneDtypeProfileError(
            "CSL dtype contract missing required kernel classes for "
            f"{variant_tag!r}: " + ", ".join(missing)
        )


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
    if registry.get("schemaVersion") != _CSL_DTYPE_CONTRACT_SCHEMA_VERSION:
        raise LaneDtypeProfileError(
            "Doe/Cerebras CSL dtype contract registry schemaVersion must be "
            f"{_CSL_DTYPE_CONTRACT_SCHEMA_VERSION}"
        )
    for contract in registry.get("contracts") or []:
        if not isinstance(contract, dict):
            continue
        if contract.get("dopplerVariantTag") != variant_tag:
            continue
        model_ids = contract.get("modelIds") or []
        if model_id is not None and model_ids and model_id not in model_ids:
            continue
        validate_csl_dtype_contract(contract)
        return json.loads(json.dumps(contract))
    suffix = f" for modelId={model_id!r}" if model_id is not None else ""
    raise LaneDtypeProfileError(
        f"no Doe/Cerebras CSL dtype contract for variantTag={variant_tag!r}{suffix}"
    )
