#!/usr/bin/env python3
"""Run a Doppler-state to CSL selected-logit splice for Qwen 3.6 27B AF16."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "bench/runners/csl-runners"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from bench.tools._receipt_hash_guard import enforce_receipt_hash_spine  # noqa: E402
from bench.tools.run_gemma4_31b_af16_doppler_selected_logit_splice import (  # noqa: E402
    DEFAULT_CELLS_ROOT,
    DEFAULT_SDK_ROOT,
    IN_DIM_PER_PE,
    artifact,
    compile_cell,
    f16_tensor_slice,
    generated_token_ids,
    load_json,
    reference_prefill_logits_path,
    rel,
    resolve,
    run_chunk,
    sha256_bytes,
    sha256_file,
    tensor_sha256,
    weight_root,
    write_json,
)


MODEL_ID = "qwen-3-6-27b-q4k-eaf16"
DEFAULT_MANIFEST = (
    REPO_ROOT / "../doppler/models/local/qwen-3-6-27b-q4k-eaf16/manifest.json"
).resolve()
DEFAULT_REFERENCE_ROOT = (
    REPO_ROOT
    / "bench/out/doppler-reference/"
    "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8"
)
DEFAULT_TSIR_FIXTURE = DEFAULT_REFERENCE_ROOT / "tsir-fixture"
DEFAULT_REFERENCE_EXPORT = (
    DEFAULT_REFERENCE_ROOT
    / "int4ple-export/doppler_int4ple_reference_export.json"
)
DEFAULT_REFERENCE_REPORT = DEFAULT_REFERENCE_ROOT / "reference-report.json"
DEFAULT_PROGRAM_BUNDLE = DEFAULT_REFERENCE_ROOT / "program-bundle.node.json"
DEFAULT_OUT_DIR = (
    REPO_ROOT
    / "bench/out/r3-2-27b-af16-doppler-csl-splice/selected-logit-splice"
)
HIDDEN_SIZE = 5120
CHUNK_PE_WIDTH = 32
FINAL_LAYER_INDEX = 63
DEFAULT_TOKEN_ID = 760
QK_K = 256
Q4K_BLOCK_BYTES = 144


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tsir-fixture", type=Path, default=DEFAULT_TSIR_FIXTURE)
    parser.add_argument("--reference-export", type=Path, default=DEFAULT_REFERENCE_EXPORT)
    parser.add_argument("--reference-report", type=Path, default=DEFAULT_REFERENCE_REPORT)
    parser.add_argument("--program-bundle", type=Path, default=DEFAULT_PROGRAM_BUNDLE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--cells-root", type=Path, default=DEFAULT_CELLS_ROOT)
    parser.add_argument("--token-id", type=int, default=DEFAULT_TOKEN_ID)
    parser.add_argument("--chunk-pe-width", type=int, default=CHUNK_PE_WIDTH)
    parser.add_argument("--atol", type=float, default=2.0e-2)
    return parser.parse_args()


def tensor_byte_slice(
    *,
    manifest: dict[str, Any],
    root: Path,
    tensor_name: str,
    byte_offset: int,
    byte_count: int,
) -> bytes:
    tensors = manifest.get("tensors") or {}
    tensor = tensors.get(tensor_name)
    if not isinstance(tensor, dict):
        raise ValueError(f"tensor_missing:{tensor_name}")
    spans = tensor.get("spans")
    if not isinstance(spans, list):
        spans = [
            {
                "shardIndex": tensor.get("shard"),
                "offset": tensor.get("offset"),
                "size": tensor.get("size"),
            }
        ]
    shards = manifest.get("shards") or []
    chunks: list[bytes] = []
    cursor = 0
    for span in spans:
        if not isinstance(span, dict):
            continue
        span_size = int(span.get("size") or 0)
        span_start = cursor
        span_end = cursor + span_size
        cursor = span_end
        req_start = max(byte_offset, span_start)
        req_end = min(byte_offset + byte_count, span_end)
        if req_start >= req_end:
            continue
        shard_index = int(span.get("shardIndex") or 0)
        shard = shards[shard_index]
        shard_path = root / str(shard["filename"])
        with shard_path.open("rb") as handle:
            handle.seek(int(span.get("offset") or 0) + (req_start - span_start))
            chunks.append(handle.read(req_end - req_start))
    data = b"".join(chunks)
    if len(data) != byte_count:
        raise ValueError(f"tensor_byte_slice_short:{tensor_name}:{len(data)}<{byte_count}")
    return data


def dequantize_q4km_block(block_bytes: bytes) -> np.ndarray:
    if len(block_bytes) != Q4K_BLOCK_BYTES:
        raise ValueError(f"q4k_block_size:{len(block_bytes)}")
    block = np.frombuffer(block_bytes, dtype=np.uint8)
    d = float(np.frombuffer(block_bytes[0:2], dtype=np.dtype("<f2"))[0])
    dmin = float(np.frombuffer(block_bytes[2:4], dtype=np.dtype("<f2"))[0])
    scale_bits = np.zeros(8, dtype=np.uint8)
    min_bits = np.zeros(8, dtype=np.uint8)
    for i in range(4):
        scale_bits[i] = block[4 + i] & 0x3F
        scale_bits[i + 4] = ((block[4 + i] >> 6) & 0x03) << 4
        min_bits[i] = block[8 + i] & 0x3F
        min_bits[i + 4] = ((block[8 + i] >> 6) & 0x03) << 4
    for i in range(4):
        scale_bits[i + 4] |= block[12 + i] & 0x0F
        min_bits[i + 4] |= (block[12 + i] >> 4) & 0x0F
    scales = d * scale_bits.astype(np.float32)
    min_offsets = dmin * min_bits.astype(np.float32)
    result = np.zeros(QK_K, dtype=np.float32)
    for chunk in range(4):
        chunk_base = chunk * 64
        byte_base = 16 + chunk * 32
        for i in range(32):
            packed = int(block[byte_base + i])
            lo = packed & 0x0F
            hi = (packed >> 4) & 0x0F
            sb0 = (chunk_base + i) // 32
            sb1 = (chunk_base + 32 + i) // 32
            result[chunk_base + i] = scales[sb0] * lo - min_offsets[sb0]
            result[chunk_base + 32 + i] = scales[sb1] * hi - min_offsets[sb1]
    return result


def q4km_tensor_row(
    *,
    manifest: dict[str, Any],
    root: Path,
    tensor_name: str,
    row_index: int,
) -> tuple[np.ndarray, bytes]:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if not isinstance(tensor, dict):
        raise ValueError(f"tensor_missing:{tensor_name}")
    if tensor.get("dtype") != "Q4_K_M":
        raise ValueError(f"tensor_dtype_unsupported:{tensor_name}:{tensor.get('dtype')}")
    if tensor.get("layout") != "row":
        raise ValueError(f"tensor_layout_unsupported:{tensor_name}:{tensor.get('layout')}")
    shape = tensor.get("shape")
    if not isinstance(shape, list) or len(shape) != 2:
        raise ValueError(f"tensor_shape_unsupported:{tensor_name}:{shape}")
    rows = int(shape[0])
    cols = int(shape[1])
    if row_index < 0 or row_index >= rows:
        raise ValueError(f"row_index_out_of_range:{row_index}:{rows}")
    blocks_per_row = (cols + QK_K - 1) // QK_K
    row_bytes = tensor_byte_slice(
        manifest=manifest,
        root=root,
        tensor_name=tensor_name,
        byte_offset=row_index * blocks_per_row * Q4K_BLOCK_BYTES,
        byte_count=blocks_per_row * Q4K_BLOCK_BYTES,
    )
    parts = [
        dequantize_q4km_block(
            row_bytes[i * Q4K_BLOCK_BYTES : (i + 1) * Q4K_BLOCK_BYTES]
        )
        for i in range(blocks_per_row)
    ]
    return np.concatenate(parts)[:cols].astype(np.float32), row_bytes


def optional_artifact(path: Path) -> dict[str, Any] | None:
    return artifact(path) if path.is_file() else None


def reference_fixture_hash(paths: list[Path]) -> str:
    payload = {
        "kind": "qwen_3_6_27b_af16_selected_logit_fixture",
        "artifacts": [
            {"path": rel(path), "sha256": sha256_file(path), "byteLength": path.stat().st_size}
            for path in paths
            if path.is_file()
        ],
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.manifest)
    tsir_fixture = resolve(args.tsir_fixture)
    reference_export_path = resolve(args.reference_export)
    reference_report_path = resolve(args.reference_report)
    program_bundle_path = resolve(args.program_bundle)
    out_dir = resolve(args.out_dir)
    sdk_root = resolve(args.sdk_root)
    cells_root = resolve(args.cells_root)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_json(manifest_path)
    reference_export = load_json(reference_export_path)
    source_root = weight_root(manifest_path, manifest)
    post_ffn_path = tsir_fixture / f"layer_{FINAL_LAYER_INDEX}/post_ffn.npy"
    if not post_ffn_path.is_file():
        raise ValueError(f"qwen_post_ffn_fixture_missing:{post_ffn_path}")
    post_ffn = np.load(post_ffn_path, allow_pickle=False).astype(np.float32)
    hidden_rows = post_ffn.reshape(-1, HIDDEN_SIZE)
    final_input = hidden_rows[-1]

    inference = manifest.get("inference") or {}
    norm_cfg = inference.get("normalization") or {}
    output_cfg = inference.get("output") or {}
    rms_norm_eps = float(norm_cfg.get("rmsNormEps", 1.0e-6))
    rms_norm_weight_offset = bool(norm_cfg.get("rmsNormWeightOffset", False))
    final_logit_softcap = output_cfg.get("finalLogitSoftcapping")
    tie_word_embeddings = bool(output_cfg.get("tieWordEmbeddings", False))

    norm_weight = f16_tensor_slice(
        manifest=manifest,
        root=source_root,
        tensor_name="model.language_model.norm.weight",
        elem_offset=0,
        elem_count=HIDDEN_SIZE,
    ).astype(np.float32)
    token_id = int(args.token_id)
    lm_head_row_f32, lm_head_row_raw = q4km_tensor_row(
        manifest=manifest,
        root=source_root,
        tensor_name="lm_head.weight",
        row_index=token_id,
    )
    lm_head_row = lm_head_row_f32.astype(np.float16)

    rms = np.sqrt(np.mean(final_input * final_input) + rms_norm_eps)
    norm_scale = norm_weight + (1.0 if rms_norm_weight_offset else 0.0)
    normalized = (final_input / rms) * norm_scale
    activation = normalized.astype(np.float16)
    cpu_raw = float(np.dot(activation.astype(np.float32), lm_head_row.astype(np.float32)))
    cpu_softcapped = cpu_raw
    if isinstance(final_logit_softcap, (int, float)):
        cpu_softcapped = float(final_logit_softcap * np.tanh(cpu_raw / final_logit_softcap))

    logits_path = reference_prefill_logits_path(reference_export)
    logits = np.fromfile(logits_path, dtype=np.float32)
    if token_id < 0 or token_id >= logits.size:
        raise ValueError(f"token_id_out_of_range:{token_id}:{logits.size}")
    expected_logit = float(logits[token_id])
    expected_token_id = int(np.argmax(logits))
    selected_text = None
    logits_digest_token = None
    for item in (reference_export.get("decodeTranscript") or {}).get("logitsDigests") or []:
        if isinstance(item, dict) and item.get("phase") == "prefill":
            logits_digest_token = item.get("selectedTokenId")
            selected_text = item.get("selectedText")
            break
    generated_tokens = generated_token_ids(reference_export)

    compile_cache: dict[int, dict[str, Any]] = {}
    chunk_results: list[dict[str, Any]] = []
    chunk_values: list[float] = []
    chunk_width = max(1, int(args.chunk_pe_width))
    chunk_elems = chunk_width * IN_DIM_PER_PE
    chunk_index = 0
    for start in range(0, HIDDEN_SIZE, chunk_elems):
        count = min(chunk_elems, HIDDEN_SIZE - start)
        width = (count + IN_DIM_PER_PE - 1) // IN_DIM_PER_PE
        padded = width * IN_DIM_PER_PE
        act_chunk = np.zeros(padded, dtype=np.float16)
        weight_chunk = np.zeros(padded, dtype=np.float16)
        act_chunk[:count] = activation[start : start + count]
        weight_chunk[:count] = lm_head_row[start : start + count]
        if width not in compile_cache:
            compile_cache[width] = compile_cell(
                width=width,
                out_dir=out_dir,
                sdk_root=sdk_root,
                cells_root=cells_root,
                artifact_kind="qwen_3_6_27b_af16_selected_logit_compile_receipt",
            )
        result = run_chunk(
            chunk_index=chunk_index,
            width=width,
            compile_dir=Path(str(compile_cache[width]["compileDir"])),
            activation=act_chunk,
            weight=weight_chunk,
            out_dir=out_dir,
            sdk_root=sdk_root,
        )
        result["hiddenStart"] = start
        result["hiddenCount"] = count
        result["cpuPartial"] = float(
            np.dot(act_chunk.astype(np.float32), weight_chunk.astype(np.float32))
        )
        chunk_results.append(result)
        if result["status"] != "succeeded" or result["outputValue"] is None:
            break
        chunk_values.append(float(result["outputValue"]))
        chunk_index += 1

    csl_raw = float(np.sum(np.array(chunk_values, dtype=np.float32)))
    csl_softcapped = csl_raw
    if isinstance(final_logit_softcap, (int, float)):
        csl_softcapped = float(final_logit_softcap * np.tanh(csl_raw / final_logit_softcap))
    csl_matches_cpu = len(chunk_values) == len(chunk_results) and all(
        abs(float(item.get("outputValue") or 0.0) - float(item["cpuPartial"])) <= 1.0e-4
        for item in chunk_results
        if item.get("status") == "succeeded"
    )
    logit_abs_diff = abs(csl_softcapped - expected_logit)
    all_chunks_succeeded = len(chunk_results) > 0 and all(
        item.get("status") == "succeeded" for item in chunk_results
    )
    generated_token_match = not generated_tokens or token_id == int(generated_tokens[0])
    digest_token_match = logits_digest_token is None or token_id == int(logits_digest_token)
    token_matches = token_id == expected_token_id and generated_token_match and digest_token_match
    verdict = (
        "pass"
        if all_chunks_succeeded
        and csl_matches_cpu
        and logit_abs_diff <= float(args.atol)
        and token_matches
        else "blocked"
    )
    blockers: list[str] = []
    if not all_chunks_succeeded:
        blockers.append("selected_logit_csl_chunk_blocked")
    if not csl_matches_cpu:
        blockers.append("selected_logit_csl_cpu_partial_mismatch")
    if logit_abs_diff > float(args.atol):
        blockers.append("selected_logit_doppler_logit_mismatch")
    if not token_matches:
        blockers.append("selected_token_not_doppler_argmax")

    fixture_hash = reference_fixture_hash(
        [
            post_ffn_path,
            reference_export_path,
            reference_report_path,
            program_bundle_path,
            logits_path,
        ]
    )
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "qwen_3_6_27b_af16_doppler_selected_logit_splice_receipt",
        "receiptClass": "manifest_shape_doppler_selected_logit_splice",
        "comparisonMode": "parity",
        "verdict": verdict,
        "blockers": blockers,
        "modelId": MODEL_ID,
        "manifestPath": rel(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        "referenceFixtureHash": fixture_hash,
        "sourceProgram": {
            "authoringSurface": "doppler_execution_v1",
            "manifestSha256": str(reference_export.get("manifestSha256") or ""),
            "executionGraphSha256": str(reference_export.get("executionGraphSha256") or ""),
            "weightSetSha256": str(reference_export.get("weightSetSha256") or ""),
            "inputSetSha256": str(reference_export.get("inputSetSha256") or ""),
            "referenceExport": artifact(reference_export_path),
            "referenceReport": optional_artifact(reference_report_path),
            "programBundle": optional_artifact(program_bundle_path),
        },
        "splicePoint": {
            "kind": "selected_lm_head_logit",
            "layerIndex": FINAL_LAYER_INDEX,
            "inputProbe": "post_ffn",
            "promptTokenCount": int(hidden_rows.shape[0]),
            "selectedTokenId": token_id,
            "selectedText": selected_text,
        },
        "dopplerReference": {
            "tsirFixtureRoot": rel(tsir_fixture),
            "inputTensor": artifact(post_ffn_path),
            "prefillLogits": artifact(logits_path),
            "expectedTokenId": expected_token_id,
            "logitsDigestSelectedTokenId": logits_digest_token,
            "generatedTokenIds": generated_tokens,
            "expectedSelectedLogit": expected_logit,
        },
        "weights": {
            "sourceRoot": rel(source_root),
            "finalNormTensor": "model.language_model.norm.weight",
            "lmHeadTensor": "lm_head.weight",
            "lmHeadStorageDtype": "Q4_K_M",
            "lmHeadTiedEmbedding": tie_word_embeddings,
            "rmsNormWeightOffset": rms_norm_weight_offset,
            "finalNormSha256": tensor_sha256(norm_weight.astype(np.float16)),
            "selectedLmHeadQ4RowSha256": sha256_bytes(lm_head_row_raw),
            "selectedLmHeadDequantizedRowSha256": tensor_sha256(lm_head_row),
        },
        "cslRun": {
            "kernel": "lm_head_prefill",
            "chunkPeWidth": chunk_width,
            "inDimPerPe": IN_DIM_PER_PE,
            "chunkCount": len(chunk_results),
            "chunkResults": chunk_results,
            "rawLogit": csl_raw,
            "softcappedLogit": csl_softcapped,
            "cpuRawLogit": cpu_raw,
            "cpuSoftcappedLogit": cpu_softcapped,
            "softcap": final_logit_softcap,
            "rmsNormEps": rms_norm_eps,
            "logitAbsDiff": logit_abs_diff,
            "atol": float(args.atol),
        },
        "claim": {
            "scope": (
                "Doppler supplies real Qwen 3.6 27B af16 post-FFN state for "
                "the final prompt position; CSL computes the selected q4k "
                "lm-head logit for the Doppler argmax token across hidden chunks."
            ),
            "notWhat": (
                "Not a full-vocabulary argmax, not a full layer-63 CSL run, "
                "and not hardware execution. The q4k lm-head row is "
                "dequantized host-side and the selected dense dot runs in CSL."
            ),
        },
    }
    enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    schema_path = REPO_ROOT / "config/doppler-selected-logit-splice-receipt.schema.json"
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        jsonschema.Draft202012Validator(load_json(schema_path)).validate(receipt)
    receipt_path = out_dir / "selected-logit-splice.json"
    write_json(receipt_path, receipt)
    print(
        f"wrote {rel(receipt_path)} "
        f"(verdict={verdict}, token={token_id}, diff={logit_abs_diff:.6e})"
    )
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
