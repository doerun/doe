#!/usr/bin/env python3
"""Doe parity harness — manual CLI gate.

Runs a three-way comparison for one kernel:

  1. Reference interpreter (TSIR oracle) — ground truth.
  2. WebGPU emission path (Doe compute).
  3. CSL emission on simfabric (Doe simulator).

Emits `parity.json` receipts under `doe/reports/parity/`. Fails closed
on unrecognized exactness class — new classes require explicit harness
support, never silent tolerance.

Not a CI tool. Runs on demand after every kernel rewrite and before
any promotion.

Exactness classes (match RDRR taxonomy verbatim):

  * `bit_exact_solo`       — hex-identical bytes vs reference.
  * `algorithm_exact`      — hex-identical under declared reduction
                             tree; harness runs reference twice, once
                             in source order and once in declared tree
                             order, both must match the backend.
  * `tolerance_bounded`    — declared metric within declared epsilon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import tsir_manifest_lowering  # noqa: E402

DEFAULT_RECEIPT_DIR = REPO_ROOT / "reports" / "parity"
SCHEMA_PATH = REPO_ROOT / "config" / "doe-parity-receipt.schema.json"

VALID_EXACTNESS = frozenset({"bit_exact_solo", "algorithm_exact", "tolerance_bounded"})
BOOTSTRAP_ORACLE_KERNELS = frozenset({"fused_gemv", "gather", "rms_norm"})
FLOAT_ELEMS = frozenset({"f32", "f16", "bf16"})
ELEM_BYTE_SIZE = {"f32": 4, "f16": 2, "bf16": 2, "u32": 4}
KERNEL_ALIASES = {
    "rmsnorm": "rms_norm",
    "rms-norm": "rms_norm",
    "fused-gemv": "fused_gemv",
}

REJECTION_REASONS = frozenset(
    {
        "tsir_subgroup_unlowerable",
        "tsir_pe_budget_exhausted",
        "tsir_collective_not_representable",
        "tsir_dependence_unanalyzable",
        "tsir_source_not_affine",
        "tsir_target_unfit",
    }
)


@dataclass
class ComparisonOutcome:
    backend: str
    status: str
    backend_hash: str | None = None
    detail: str | None = None


class BootstrapOracleNotImplemented(RuntimeError):
    """Raised when the bootstrap oracle cannot honestly execute a case."""


@dataclass(frozen=True)
class OracleBuffer:
    name: str
    elem: str
    shape: tuple[int, ...]
    data: bytes


@dataclass(frozen=True)
class OracleInputDoc:
    kernel: str
    inputs: dict[str, OracleBuffer]
    parameters: dict[str, Any]


@dataclass(frozen=True)
class LoweringIdentity:
    tsir_semantic_digest: str
    tsir_realization_digest: str
    emitter_digest: str
    target_descriptor_correctness_hash: str

    def to_json(self) -> dict[str, str]:
        return {
            "emitterDigest": self.emitter_digest,
            "targetDescriptorCorrectnessHash": (
                self.target_descriptor_correctness_hash
            ),
            "tsirRealizationDigest": self.tsir_realization_digest,
            "tsirSemanticDigest": self.tsir_semantic_digest,
        }


@dataclass
class ParityReceipt:
    schema_version: int
    artifact_kind: str
    kernel: str
    exactness_class: str
    reference_hash: str | None
    inputs_digest: str
    comparisons: list[ComparisonOutcome] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    lowering_identity: LoweringIdentity | None = None

    def to_json(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "artifactKind": self.artifact_kind,
            "kernel": self.kernel,
            "exactnessClass": self.exactness_class,
            "referenceHash": self.reference_hash,
            "inputsDigest": self.inputs_digest,
            "comparisons": [
                {
                    "backend": c.backend,
                    "status": c.status,
                    "backendHash": c.backend_hash,
                    "detail": c.detail,
                }
                for c in self.comparisons
            ],
            "rejectionReasons": self.rejection_reasons,
        }
        if self.lowering_identity is not None:
            doc["loweringIdentity"] = self.lowering_identity.to_json()
        return doc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", help="Kernel name, e.g. `rmsnorm`.")
    parser.add_argument(
        "--class",
        dest="exactness",
        required=True,
        choices=sorted(VALID_EXACTNESS),
        help="Declared exactness class for this kernel.",
    )
    parser.add_argument(
        "--inputs",
        required=True,
        type=Path,
        help="Path to a directory or file holding the kernel inputs.",
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        default=DEFAULT_RECEIPT_DIR,
        help="Directory to write the parity receipt.",
    )
    parser.add_argument(
        "--semantic-tsir",
        type=Path,
        help="Optional TSIR semantic JSON. When present with --realization-tsir, "
        "declared rejections are surfaced in the parity receipt.",
    )
    parser.add_argument(
        "--realization-tsir",
        type=Path,
        help="Optional TSIR realization JSON. Must be paired with --semantic-tsir.",
    )
    parser.add_argument(
        "--manifest-lowering-entry",
        type=Path,
        help="Optional integrityExtensions.lowerings[] fixture entry. Copies "
        "TSIR lowering identity digests into the receipt without changing "
        "stub execution status.",
    )
    return parser.parse_args()


def sha256_of_path(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.read_bytes())
        return h.hexdigest()
    if path.is_dir():
        for entry in sorted(path.rglob("*")):
            if not entry.is_file():
                continue
            h.update(entry.relative_to(path).as_posix().encode("utf-8"))
            h.update(b"\0")
            h.update(entry.read_bytes())
        return h.hexdigest()
    raise FileNotFoundError(f"inputs path not found: {path}")


def canonical_kernel_name(kernel: str) -> str:
    prefix = "doe.tsir.bootstrap."
    if kernel.startswith(prefix):
        kernel = kernel.removeprefix(prefix)
    return KERNEL_ALIASES.get(kernel, kernel)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def _f32_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


def _f32_to_bf16_rne(value: float) -> int:
    bits = _f32_bits(value)
    exp = (bits >> 23) & 0xFF
    mantissa = bits & 0x7FFFFF
    if exp == 0xFF and mantissa != 0:
        return ((bits >> 16) | 0x40) & 0xFFFF
    lsb = (bits >> 16) & 1
    return ((bits + 0x7FFF + lsb) & 0xFFFFFFFF) >> 16


def _elem_count(shape: tuple[int, ...]) -> int:
    count = 1
    for dim in shape:
        count *= dim
    return count


def _parse_shape(value: object, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise BootstrapOracleNotImplemented(f"input {name} shape must be a list")
    shape: list[int] = []
    for dim in value:
        if not isinstance(dim, int) or dim < 0:
            raise BootstrapOracleNotImplemented(
                f"input {name} shape dimensions must be non-negative integers"
            )
        shape.append(dim)
    return tuple(shape)


def _pack_elem(elem: str, value: object) -> bytes:
    if elem == "f32":
        return struct.pack("<f", float(value))
    if elem == "f16":
        return struct.pack("<e", float(value))
    if elem == "bf16":
        return struct.pack("<H", _f32_to_bf16_rne(float(value)))
    if elem == "u32":
        if not isinstance(value, int) or value < 0:
            raise BootstrapOracleNotImplemented("u32 values must be integers")
        return struct.pack("<I", value)
    raise BootstrapOracleNotImplemented(f"unsupported input elem: {elem}")


def _read_f32(buf: OracleBuffer, elem_index: int) -> float:
    if buf.elem == "f32":
        offset = elem_index * ELEM_BYTE_SIZE[buf.elem]
        return struct.unpack("<f", buf.data[offset : offset + 4])[0]
    if buf.elem == "f16":
        offset = elem_index * ELEM_BYTE_SIZE[buf.elem]
        return _f32(struct.unpack("<e", buf.data[offset : offset + 2])[0])
    if buf.elem == "bf16":
        offset = elem_index * ELEM_BYTE_SIZE[buf.elem]
        word = struct.unpack("<H", buf.data[offset : offset + 2])[0]
        return _f32_from_bits(word << 16)
    raise BootstrapOracleNotImplemented(f"cannot read {buf.elem} as f32")


def _read_u32(buf: OracleBuffer, elem_index: int) -> int:
    if buf.elem != "u32":
        raise BootstrapOracleNotImplemented(f"cannot read {buf.elem} as u32")
    offset = elem_index * ELEM_BYTE_SIZE[buf.elem]
    return struct.unpack("<I", buf.data[offset : offset + 4])[0]


def _write_f32_as_elem(elem: str, value: float) -> bytes:
    if elem == "f32":
        return struct.pack("<f", _f32(value))
    if elem == "f16":
        return struct.pack("<e", _f32(value))
    if elem == "bf16":
        return struct.pack("<H", _f32_to_bf16_rne(_f32(value)))
    raise BootstrapOracleNotImplemented(f"cannot write {elem} output")


def _parse_oracle_buffer(name: str, spec: object) -> OracleBuffer:
    if not isinstance(spec, dict):
        raise BootstrapOracleNotImplemented(f"input {name} must be an object")
    elem = spec.get("elem")
    if not isinstance(elem, str) or elem not in ELEM_BYTE_SIZE:
        raise BootstrapOracleNotImplemented(f"input {name} has unsupported elem")
    shape = _parse_shape(spec.get("shape"), name)
    expected_bytes = _elem_count(shape) * ELEM_BYTE_SIZE[elem]
    if "bytesHex" in spec:
        bytes_hex = spec["bytesHex"]
        if not isinstance(bytes_hex, str):
            raise BootstrapOracleNotImplemented(
                f"input {name} bytesHex must be a string"
            )
        try:
            data = bytes.fromhex(bytes_hex)
        except ValueError as exc:
            raise BootstrapOracleNotImplemented(
                f"input {name} bytesHex is not valid hex"
            ) from exc
    elif "values" in spec:
        values = spec["values"]
        if not isinstance(values, list):
            raise BootstrapOracleNotImplemented(
                f"input {name} values must be a list"
            )
        if len(values) != _elem_count(shape):
            raise BootstrapOracleNotImplemented(
                f"input {name} values do not match shape"
            )
        data = b"".join(_pack_elem(elem, value) for value in values)
    else:
        raise BootstrapOracleNotImplemented(
            f"input {name} must declare values or bytesHex"
        )
    if len(data) != expected_bytes:
        raise BootstrapOracleNotImplemented(
            f"input {name} bytes do not match elem/shape"
        )
    return OracleBuffer(name=name, elem=elem, shape=shape, data=data)


def _load_oracle_input_doc(path: Path | None) -> OracleInputDoc:
    if path is None:
        raise BootstrapOracleNotImplemented("no bootstrap oracle input path supplied")
    if not path.is_file():
        raise BootstrapOracleNotImplemented(
            "bootstrap oracle inputs must be a JSON file"
        )
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise BootstrapOracleNotImplemented("bootstrap oracle input must be an object")
    kernel = doc.get("kernel")
    if not isinstance(kernel, str):
        raise BootstrapOracleNotImplemented("bootstrap oracle input needs kernel")
    raw_inputs = doc.get("inputs")
    inputs: dict[str, OracleBuffer] = {}
    if isinstance(raw_inputs, dict):
        for name, spec in raw_inputs.items():
            if not isinstance(name, str) or not name:
                raise BootstrapOracleNotImplemented("input names must be non-empty")
            inputs[name] = _parse_oracle_buffer(name, spec)
    elif isinstance(raw_inputs, list):
        for spec in raw_inputs:
            if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
                raise BootstrapOracleNotImplemented(
                    "listed inputs must include string names"
                )
            name = spec["name"]
            inputs[name] = _parse_oracle_buffer(name, spec)
    else:
        raise BootstrapOracleNotImplemented("bootstrap oracle input needs inputs")
    parameters = doc.get("parameters", {})
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise BootstrapOracleNotImplemented("parameters must be an object")
    return OracleInputDoc(
        kernel=canonical_kernel_name(kernel),
        inputs=inputs,
        parameters=parameters,
    )


def _load_json_object(path: Path | None, label: str) -> dict[str, Any] | None:
    if path is None:
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise BootstrapOracleNotImplemented(f"{label} must be a JSON object")
    return doc


def _semantic_function(semantic_doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if semantic_doc is None:
        return None
    functions = semantic_doc.get("functions")
    if not isinstance(functions, list) or len(functions) != 1:
        raise BootstrapOracleNotImplemented(
            "bootstrap oracle requires exactly one TSIR function"
        )
    func = functions[0]
    if not isinstance(func, dict):
        raise BootstrapOracleNotImplemented("TSIR function must be an object")
    return func


def _binding_for_role(
    func: dict[str, Any] | None,
    role_name: str,
    fallback_name: str,
) -> tuple[str, str | None]:
    if func is None:
        return fallback_name, None
    body = func.get("body")
    bindings = func.get("bindings")
    if not isinstance(body, dict) or not isinstance(bindings, list):
        raise BootstrapOracleNotImplemented("TSIR body/bindings must be objects")
    binding_roles = body.get("bindingRoles")
    if not isinstance(binding_roles, list):
        raise BootstrapOracleNotImplemented("TSIR bindingRoles must be a list")
    matches = [
        role
        for role in binding_roles
        if isinstance(role, dict) and role.get("role") == role_name
    ]
    if len(matches) != 1:
        raise BootstrapOracleNotImplemented(
            f"TSIR must declare exactly one {role_name} binding role"
        )
    binding_index = matches[0].get("bindingIndex")
    if not isinstance(binding_index, int) or binding_index < 0:
        raise BootstrapOracleNotImplemented(
            f"TSIR {role_name} binding index must be a non-negative integer"
        )
    if binding_index >= len(bindings) or not isinstance(bindings[binding_index], dict):
        raise BootstrapOracleNotImplemented(
            f"TSIR {role_name} binding index is out of range"
        )
    binding = bindings[binding_index]
    name = binding.get("name")
    elem = binding.get("elem")
    if not isinstance(name, str) or not name:
        raise BootstrapOracleNotImplemented(f"TSIR {role_name} binding needs a name")
    if elem is not None and not isinstance(elem, str):
        raise BootstrapOracleNotImplemented(f"TSIR {role_name} elem must be a string")
    return name, elem


def _expect_semantic_op(func: dict[str, Any] | None, op: str) -> None:
    if func is None:
        return
    body = func.get("body")
    if not isinstance(body, dict) or body.get("op") != op:
        raise BootstrapOracleNotImplemented(f"TSIR body op is not {op}")


def _get_buffer(inputs: dict[str, OracleBuffer], name: str) -> OracleBuffer:
    try:
        return inputs[name]
    except KeyError as exc:
        raise BootstrapOracleNotImplemented(f"missing oracle input: {name}") from exc


def _check_elem_matches(buf: OracleBuffer, declared_elem: str | None) -> None:
    if declared_elem is not None and buf.elem != declared_elem:
        raise BootstrapOracleNotImplemented(
            f"input {buf.name} elem {buf.elem} does not match TSIR {declared_elem}"
        )


def _realization_tree_shape(realization_doc: dict[str, Any] | None) -> str:
    if realization_doc is None:
        return "linear"
    functions = realization_doc.get("functions")
    if not isinstance(functions, list) or len(functions) != 1:
        return "linear"
    func = functions[0]
    if not isinstance(func, dict):
        return "linear"
    reductions = func.get("reductions")
    if not isinstance(reductions, list) or len(reductions) != 1:
        return "linear"
    reduction = reductions[0]
    if not isinstance(reduction, dict):
        return "linear"
    tree_shape = reduction.get("treeShape")
    if tree_shape in {"linear", "ring", "binomial"}:
        return tree_shape
    return "linear"


def _run_fused_gemv_oracle(
    doc: OracleInputDoc,
    func: dict[str, Any] | None,
    realization_doc: dict[str, Any] | None,
) -> str:
    _expect_semantic_op(func, "fused_gemv")
    matrix_name, matrix_elem = _binding_for_role(func, "matrix", "W")
    vector_name, vector_elem = _binding_for_role(func, "vector", "x")
    output_name, output_elem = _binding_for_role(func, "output", "y")
    _ = output_name

    matrix = _get_buffer(doc.inputs, matrix_name)
    vector = _get_buffer(doc.inputs, vector_name)
    _check_elem_matches(matrix, matrix_elem)
    _check_elem_matches(vector, vector_elem)
    if matrix.elem not in FLOAT_ELEMS or vector.elem != matrix.elem:
        raise BootstrapOracleNotImplemented(
            "fused_gemv requires matching f32/f16/bf16 matrix and vector"
        )
    out_elem = output_elem or matrix.elem
    if out_elem != matrix.elem:
        raise BootstrapOracleNotImplemented(
            "fused_gemv bootstrap oracle requires matching output elem"
        )
    if len(matrix.shape) != 2 or len(vector.shape) != 1:
        raise BootstrapOracleNotImplemented("fused_gemv expects W[M,K] and x[K]")
    rows, cols = matrix.shape
    if vector.shape[0] != cols:
        raise BootstrapOracleNotImplemented(
            "fused_gemv vector length must match matrix K"
        )

    tree_shape = _realization_tree_shape(realization_doc)
    output = bytearray()
    for row in range(rows):
        if tree_shape == "binomial":
            values = [
                _f32(
                    _read_f32(matrix, row * cols + col)
                    * _read_f32(vector, col)
                )
                for col in range(cols)
            ]
            while len(values) > 1:
                next_values: list[float] = []
                idx = 0
                while idx < len(values):
                    if idx + 1 < len(values):
                        next_values.append(_f32(values[idx] + values[idx + 1]))
                    else:
                        next_values.append(values[idx])
                    idx += 2
                values = next_values
            acc = values[0] if values else _f32(0.0)
        else:
            acc = _f32(0.0)
            for col in range(cols):
                product = _f32(
                    _read_f32(matrix, row * cols + col)
                    * _read_f32(vector, col)
                )
                acc = _f32(acc + product)
        output.extend(_write_f32_as_elem(out_elem, acc))
    return _sha256_hex(bytes(output))


def _resolve_rms_norm_epsilon(
    doc: OracleInputDoc,
    func: dict[str, Any] | None,
) -> float:
    if "epsilon" in doc.parameters:
        return _f32(float(doc.parameters["epsilon"]))
    if func is None:
        raise BootstrapOracleNotImplemented("rms_norm input needs epsilon")
    body = func.get("body")
    if not isinstance(body, dict):
        raise BootstrapOracleNotImplemented("rms_norm TSIR body must be an object")
    rms_norm = body.get("rmsNorm")
    if not isinstance(rms_norm, dict):
        raise BootstrapOracleNotImplemented("rms_norm TSIR body needs rmsNorm")
    epsilon = rms_norm.get("epsilon")
    if not isinstance(epsilon, dict):
        raise BootstrapOracleNotImplemented("rms_norm TSIR needs epsilon")
    source = epsilon.get("source")
    if source == "literal_f32":
        literal = epsilon.get("literalF32")
        if not isinstance(literal, (int, float)):
            raise BootstrapOracleNotImplemented("rms_norm literal epsilon missing")
        return _f32(float(literal))
    if source != "uniform_field":
        raise BootstrapOracleNotImplemented("unsupported rms_norm epsilon source")
    binding_index = epsilon.get("bindingIndex")
    byte_offset = epsilon.get("byteOffset")
    bindings = func.get("bindings")
    if (
        not isinstance(binding_index, int)
        or not isinstance(byte_offset, int)
        or not isinstance(bindings, list)
        or binding_index >= len(bindings)
        or not isinstance(bindings[binding_index], dict)
    ):
        raise BootstrapOracleNotImplemented("invalid rms_norm epsilon binding")
    binding_name = bindings[binding_index].get("name")
    if not isinstance(binding_name, str):
        raise BootstrapOracleNotImplemented("rms_norm epsilon binding needs a name")
    uniform = _get_buffer(doc.inputs, binding_name)
    if byte_offset < 0 or byte_offset + 4 > len(uniform.data):
        raise BootstrapOracleNotImplemented("rms_norm epsilon offset out of range")
    bits = struct.unpack("<I", uniform.data[byte_offset : byte_offset + 4])[0]
    return _f32_from_bits(bits)


def _run_rms_norm_oracle(
    doc: OracleInputDoc,
    func: dict[str, Any] | None,
) -> str:
    _expect_semantic_op(func, "rms_norm")
    input_name, input_elem = _binding_for_role(func, "input", "input")
    scale_name, scale_elem = _binding_for_role(func, "scale", "weight")
    output_name, output_elem = _binding_for_role(func, "output", "output")
    _ = output_name

    input_buf = _get_buffer(doc.inputs, input_name)
    scale_buf = _get_buffer(doc.inputs, scale_name)
    _check_elem_matches(input_buf, input_elem)
    _check_elem_matches(scale_buf, scale_elem)
    if input_buf.elem not in FLOAT_ELEMS or scale_buf.elem != input_buf.elem:
        raise BootstrapOracleNotImplemented(
            "rms_norm requires matching f32/f16/bf16 input and weight"
        )
    out_elem = output_elem or input_buf.elem
    if out_elem != input_buf.elem:
        raise BootstrapOracleNotImplemented(
            "rms_norm bootstrap oracle requires matching output elem"
        )
    if len(input_buf.shape) != 1 or scale_buf.shape != input_buf.shape:
        raise BootstrapOracleNotImplemented("rms_norm expects equal rank-1 inputs")

    epsilon = _resolve_rms_norm_epsilon(doc, func)
    hidden = input_buf.shape[0]
    output = bytearray()
    if hidden == 0:
        return _sha256_hex(bytes(output))
    sum_sq = _f32(0.0)
    for idx in range(hidden):
        value = _read_f32(input_buf, idx)
        sum_sq = _f32(sum_sq + _f32(value * value))
    mean_sq = _f32(sum_sq / _f32(float(hidden)))
    inv_rms = _f32(1.0 / _f32(math.sqrt(_f32(mean_sq + epsilon))))
    for idx in range(hidden):
        value = _read_f32(input_buf, idx)
        scale = _read_f32(scale_buf, idx)
        out = _f32(_f32(value * inv_rms) * scale)
        output.extend(_write_f32_as_elem(out_elem, out))
    return _sha256_hex(bytes(output))


def _run_gather_oracle(
    doc: OracleInputDoc,
    func: dict[str, Any] | None,
) -> str:
    _expect_semantic_op(func, "gather")
    indices_name, indices_elem = _binding_for_role(func, "indices", "indices")
    table_name, table_elem = _binding_for_role(func, "table", "table")
    output_name, output_elem = _binding_for_role(func, "output", "output")
    _ = output_name

    indices = _get_buffer(doc.inputs, indices_name)
    table = _get_buffer(doc.inputs, table_name)
    _check_elem_matches(indices, indices_elem)
    _check_elem_matches(table, table_elem)
    if indices.elem != "u32":
        raise BootstrapOracleNotImplemented("gather indices must be u32")
    if table.elem not in FLOAT_ELEMS:
        raise BootstrapOracleNotImplemented("gather table must be f32/f16/bf16")
    out_elem = output_elem or table.elem
    if out_elem != table.elem:
        raise BootstrapOracleNotImplemented(
            "gather bootstrap oracle requires matching output elem"
        )
    if len(indices.shape) != 1 or len(table.shape) != 2:
        raise BootstrapOracleNotImplemented("gather expects indices[T], table[V,H]")
    tokens = indices.shape[0]
    vocab, hidden = table.shape

    output = bytearray()
    elem_size = ELEM_BYTE_SIZE[table.elem]
    for token in range(tokens):
        row = _read_u32(indices, token)
        if row >= vocab:
            raise BootstrapOracleNotImplemented(
                "gather index is outside the declared table"
            )
        start = row * hidden * elem_size
        end = start + hidden * elem_size
        output.extend(table.data[start:end])
    return _sha256_hex(bytes(output))


def _run_bootstrap_oracle(
    kernel: str,
    inputs_path: Path | None,
    semantic_path: Path | None,
    realization_path: Path | None,
) -> str:
    canonical_kernel = canonical_kernel_name(kernel)
    if canonical_kernel not in BOOTSTRAP_ORACLE_KERNELS:
        raise BootstrapOracleNotImplemented(
            f"bootstrap oracle does not support kernel: {kernel}"
        )
    doc = _load_oracle_input_doc(inputs_path)
    if doc.kernel != canonical_kernel:
        raise BootstrapOracleNotImplemented(
            f"input kernel {doc.kernel} does not match CLI kernel {canonical_kernel}"
        )
    semantic_doc = _load_json_object(semantic_path, "semantic TSIR")
    realization_doc = _load_json_object(realization_path, "realization TSIR")
    func = _semantic_function(semantic_doc)

    if canonical_kernel == "fused_gemv":
        return _run_fused_gemv_oracle(doc, func, realization_doc)
    if canonical_kernel == "rms_norm":
        return _run_rms_norm_oracle(doc, func)
    if canonical_kernel == "gather":
        return _run_gather_oracle(doc, func)
    raise BootstrapOracleNotImplemented(
        f"bootstrap oracle does not support kernel: {kernel}"
    )


def extract_rejection_reasons(
    semantic_doc: dict[str, Any], realization_doc: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    for doc in (semantic_doc, realization_doc):
        entries = doc.get("rejections") or []
        if not isinstance(entries, list):
            raise ValueError("TSIR rejections must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("TSIR rejection entry must be an object")
            reason = entry.get("reason")
            if reason not in REJECTION_REASONS:
                raise ValueError(f"unrecognized TSIR rejection reason: {reason}")
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def load_rejection_reasons(
    semantic_path: Path | None, realization_path: Path | None
) -> list[str]:
    if bool(semantic_path) != bool(realization_path):
        raise ValueError(
            "--semantic-tsir and --realization-tsir must be supplied together"
        )
    if semantic_path is None or realization_path is None:
        return []
    semantic_doc = json.loads(semantic_path.read_text(encoding="utf-8"))
    realization_doc = json.loads(realization_path.read_text(encoding="utf-8"))
    if not isinstance(semantic_doc, dict) or not isinstance(realization_doc, dict):
        raise ValueError("TSIR JSON must be top-level objects")
    return extract_rejection_reasons(semantic_doc, realization_doc)


def lowering_identity_from_manifest_entry(
    entry_path: Path | None, exactness: str
) -> LoweringIdentity | None:
    if entry_path is None:
        return None
    entry = tsir_manifest_lowering.load_entry_doc(entry_path)
    entry_exactness = entry["exactness"]["class"]
    if entry_exactness != exactness:
        raise ValueError(
            "manifest lowering exactness class does not match CLI --class: "
            f"{entry_exactness} != {exactness}"
        )
    return LoweringIdentity(
        tsir_semantic_digest=entry["tsirSemanticDigest"],
        tsir_realization_digest=entry["tsirRealizationDigest"],
        emitter_digest=entry["emitterDigest"],
        target_descriptor_correctness_hash=(
            entry["targetDescriptorCorrectnessHash"]
        ),
    )


def run_reference_interpreter(
    kernel: str,
    _inputs_digest: str,
    rejection_reasons: list[str] | None = None,
    inputs_path: Path | None = None,
    semantic_path: Path | None = None,
    realization_path: Path | None = None,
) -> ComparisonOutcome:
    """Invoke the TSIR reference interpreter.

    This is intentionally narrow: it only executes dedicated bootstrap
    oracle input artifacts for the Phase A `fused_gemv`, `rms_norm`, and
    `gather` families. Manifest fixtures, directories, generic TSIR JSON,
    and unrecognized shapes still return `not_implemented` so receipts do
    not imply coverage the harness does not have.
    """
    if rejection_reasons:
        return ComparisonOutcome(
            backend="reference",
            status="rejected",
            detail="TSIR rejected before execution: " + ", ".join(rejection_reasons),
        )
    try:
        reference_hash = _run_bootstrap_oracle(
            kernel,
            inputs_path,
            semantic_path,
            realization_path,
        )
    except BootstrapOracleNotImplemented as exc:
        return ComparisonOutcome(
            backend="reference",
            status="not_implemented",
            detail=str(exc),
        )
    return ComparisonOutcome(
        backend="reference",
        status="pass",
        backend_hash=reference_hash,
        detail="bootstrap TSIR oracle executed",
    )


def run_backend(backend: str) -> ComparisonOutcome:
    """Run a backend emission path and return its hash.

    Scaffolding: both backend lanes are still execution-stub-only. The
    TSIR emitters now have semantic-aware bootstrap bodies, but this CLI
    still needs WebGPU execution and CSL simfabric driver wiring before it
    can compare backend bytes. Until those land, this returns
    `not_implemented` so the receipt reflects the actual state rather than
    an invented answer.
    """
    return ComparisonOutcome(
        backend=backend,
        status="not_implemented",
        detail=f"{backend} backend lane wiring not yet landed",
    )


def compare(
    reference: ComparisonOutcome,
    backend_outcome: ComparisonOutcome,
    exactness: str,
) -> ComparisonOutcome:
    if exactness not in VALID_EXACTNESS:
        raise ValueError(f"unrecognized exactness class: {exactness}")
    if reference.status == "rejected":
        return ComparisonOutcome(
            backend=backend_outcome.backend,
            status="rejected",
            detail=f"{backend_outcome.backend} blocked: reference={reference.status}",
        )
    reference_ready = reference.status in {"ok", "pass"}
    backend_ready = backend_outcome.status in {"ok", "pass"}
    if not reference_ready or not backend_ready:
        detail = (
            f"{backend_outcome.backend} deferred: "
            f"reference={reference.status}, backend={backend_outcome.status}"
        )
        return ComparisonOutcome(
            backend=backend_outcome.backend, status="deferred", detail=detail
        )
    if exactness in {"bit_exact_solo", "algorithm_exact"}:
        if reference.backend_hash == backend_outcome.backend_hash:
            return ComparisonOutcome(
                backend=backend_outcome.backend,
                status="pass",
                backend_hash=backend_outcome.backend_hash,
            )
        return ComparisonOutcome(
            backend=backend_outcome.backend,
            status="fail",
            backend_hash=backend_outcome.backend_hash,
            detail="hash mismatch",
        )
    # tolerance_bounded: the real comparator lives in the kernel's
    # declared metric/epsilon pair; scaffolding refuses to pass here
    # without those fields, by design.
    return ComparisonOutcome(
        backend=backend_outcome.backend,
        status="fail",
        backend_hash=backend_outcome.backend_hash,
        detail="tolerance_bounded metric+epsilon not yet wired",
    )


def _format_schema_path(error: jsonschema.ValidationError) -> str:
    if not error.path:
        return "<root>"
    return ".".join(str(part) for part in error.path)


def validate_receipt_doc(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        path = _format_schema_path(first)
        raise ValueError(
            f"parity receipt schema validation failed at {path}: {first.message}"
        )


def write_receipt(receipt: ParityReceipt, receipt_dir: Path) -> Path:
    doc = receipt.to_json()
    validate_receipt_doc(doc)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    out_path = receipt_dir / f"{receipt.kernel}.parity.json"
    out_path.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    try:
        args = parse_args()
        if args.exactness not in VALID_EXACTNESS:
            # argparse.choices should prevent this, but the guard is
            # declared per the fail-closed contract on unknown classes.
            print(f"unrecognized exactness class: {args.exactness}", file=sys.stderr)
            return 1

        inputs_digest = sha256_of_path(args.inputs)
        rejection_reasons = load_rejection_reasons(
            args.semantic_tsir, args.realization_tsir
        )
        lowering_identity = lowering_identity_from_manifest_entry(
            args.manifest_lowering_entry, args.exactness
        )
        reference = run_reference_interpreter(
            args.kernel,
            inputs_digest,
            rejection_reasons,
            inputs_path=args.inputs,
            semantic_path=args.semantic_tsir,
            realization_path=args.realization_tsir,
        )
        webgpu_result = run_backend("webgpu")
        csl_result = run_backend("csl-simfabric")

        comparisons = [
            compare(reference, webgpu_result, args.exactness),
            compare(reference, csl_result, args.exactness),
        ]

        receipt = ParityReceipt(
            schema_version=2,
            artifact_kind="doe_parity_receipt",
            kernel=args.kernel,
            exactness_class=args.exactness,
            reference_hash=reference.backend_hash,
            inputs_digest=inputs_digest,
            comparisons=[reference] + comparisons,
            rejection_reasons=rejection_reasons,
            lowering_identity=lowering_identity,
        )
        out_path = write_receipt(receipt, args.receipt_dir)
        try:
            display_path: Path | str = out_path.relative_to(REPO_ROOT)
        except ValueError:
            display_path = out_path
        print(f"PARITY RECEIPT: {display_path}")
        # Scaffolding never claims pass; return 1 so callers cannot mistake
        # "receipt produced" for "kernel is green."
        any_non_pass = any(c.status != "pass" for c in comparisons)
        return 1 if any_non_pass else 0
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
