#!/usr/bin/env python3
"""Run a Doppler-state to CSL selected-logit splice for Gemma 4 31B AF16."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
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


MODEL_ID = "gemma-4-31b-it-text-q4k-ehf16-af16"
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "../doppler/models/local/gemma-4-31b-it-text-q4k-ehf16-af16/manifest.json"
).resolve()
DEFAULT_FIXTURE_ROOT = REPO_ROOT / "bench/fixtures/r3-1-31b-doppler-frozen-af16"
DEFAULT_REFERENCE_EXPORT = (
    REPO_ROOT
    / "bench/out/doppler-reference/"
    "gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/"
    "doppler_int4ple_reference_export.json"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-doppler-csl-splice/selected-logit-splice"
)
DEFAULT_SDK_ROOT = Path("/home/x/cerebras-sdk-2.10.0")
DEFAULT_CELLS_ROOT = (
    REPO_ROOT / "bench/runners/csl-runners/gemma-4-31b-af16-cells"
)
CHAIN_STEP_ADAPTER = RUNNER_DIR / "chain_step_adapter.py"
HIDDEN_SIZE = 5376
IN_DIM_PER_PE = 32
CHUNK_PE_WIDTH = 32
FINAL_LAYER_INDEX = 59
DEFAULT_TOKEN_ID = 3730
FINAL_LOGIT_SOFTCAP = 30.0
RMS_NORM_EPS = 1.0e-6
ADAPTER_WATCHDOG = 240


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--reference-export", type=Path, default=DEFAULT_REFERENCE_EXPORT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--cells-root", type=Path, default=DEFAULT_CELLS_ROOT)
    parser.add_argument("--token-id", type=int, default=DEFAULT_TOKEN_ID)
    parser.add_argument("--chunk-pe-width", type=int, default=CHUNK_PE_WIDTH)
    parser.add_argument("--atol", type=float, default=2.0e-2)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tensor_sha256(array: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(array).tobytes(order="C"))


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "sha256": sha256_file(path),
        "byteLength": path.stat().st_size,
    }


def weight_root(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    weights_ref = manifest.get("weightsRef") or {}
    artifact_root = weights_ref.get("artifactRoot")
    if not isinstance(artifact_root, str) or not artifact_root:
        return manifest_path.parent
    return (manifest_path.parent / artifact_root).resolve()


def f16_tensor_slice(
    *,
    manifest: dict[str, Any],
    root: Path,
    tensor_name: str,
    elem_offset: int,
    elem_count: int,
) -> np.ndarray:
    tensors = manifest.get("tensors") or {}
    tensor = tensors.get(tensor_name)
    if not isinstance(tensor, dict):
        raise ValueError(f"tensor_missing:{tensor_name}")
    if tensor.get("dtype") != "F16":
        raise ValueError(f"tensor_dtype_unsupported:{tensor_name}:{tensor.get('dtype')}")
    byte_start = elem_offset * 2
    byte_len = elem_count * 2
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
        req_start = max(byte_start, span_start)
        req_end = min(byte_start + byte_len, span_end)
        if req_start >= req_end:
            continue
        shard_index = int(span.get("shardIndex") or 0)
        shard = shards[shard_index]
        shard_path = root / str(shard["filename"])
        with shard_path.open("rb") as handle:
            handle.seek(int(span.get("offset") or 0) + (req_start - span_start))
            chunks.append(handle.read(req_end - req_start))
    data = b"".join(chunks)
    if len(data) != byte_len:
        raise ValueError(
            f"tensor_slice_short:{tensor_name}:{len(data)}<{byte_len}"
        )
    return np.frombuffer(data, dtype=np.float16).copy()


def fixture_tensor_path(
    *,
    fixture_root: Path,
    fixture_manifest: dict[str, Any],
    layer_index: int,
    probe: str,
) -> Path:
    layer = (fixture_manifest.get("activations") or {}).get(str(layer_index))
    if not isinstance(layer, dict):
        raise ValueError(f"fixture_layer_absent:{layer_index}")
    spec = layer.get(probe)
    if not isinstance(spec, dict):
        raise ValueError(f"fixture_probe_absent:{layer_index}:{probe}")
    path = fixture_root / str(spec.get("path") or "")
    if not path.is_file():
        raise ValueError(f"fixture_tensor_missing:{path}")
    return path


def compile_cell(
    *,
    width: int,
    out_dir: Path,
    sdk_root: Path,
    cells_root: Path,
) -> dict[str, Any]:
    compile_root = out_dir / f"compile-w{width:04d}"
    compile_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cells_root / "lm_head_prefill_layout.csl", compile_root / "layout.csl")
    shutil.copy2(
        cells_root / "lm_head_prefill_pe_program.csl",
        compile_root / "pe_program.csl",
    )
    compile_dir = compile_root / "compiled"
    if compile_dir.exists():
        shutil.rmtree(compile_dir)
    command = [
        str(sdk_root / "cslc"),
        "layout.csl",
        "--arch=wse3",
        "--fabric-dims=40,5",
        "--fabric-offsets=4,1",
        (
            "--params="
            f"width:{width},height:1,out_dim:1,out_dim_per_pe:1,"
            f"in_dim_per_pe:{IN_DIM_PER_PE}"
        ),
        "--memcpy",
        "--channels=1",
        "-o",
        "compiled",
    ]
    completed = subprocess.run(
        command,
        cwd=compile_root,
        check=False,
        capture_output=True,
        text=True,
    )
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_selected_logit_compile_receipt",
        "status": "succeeded" if completed.returncode == 0 else "blocked",
        "blockers": [] if completed.returncode == 0 else [f"cslc_exit_{completed.returncode}"],
        "compileDir": rel(compile_dir),
        "command": command,
        "params": {
            "width": width,
            "height": 1,
            "outDim": 1,
            "outDimPerPe": 1,
            "inDimPerPe": IN_DIM_PER_PE,
        },
        "stdoutTail": completed.stdout.splitlines()[-8:],
        "stderrTail": completed.stderr.splitlines()[-8:],
    }
    receipt_path = compile_root / "compile-receipt.json"
    write_json(receipt_path, receipt)
    if completed.returncode != 0:
        raise RuntimeError(f"selected_logit_cslc_failed:{width}")
    return {
        "width": width,
        "compileDir": compile_dir,
        "compileReceipt": receipt_path,
    }


def run_adapter(command: list[str], *, cwd: Path) -> tuple[int, str, str, bool]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=ADAPTER_WATCHDOG)
        return int(process.returncode or 0), stdout, stderr, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        return -1, stdout, stderr, True


def run_chunk(
    *,
    chunk_index: int,
    width: int,
    compile_dir: Path,
    activation: np.ndarray,
    weight: np.ndarray,
    out_dir: Path,
    sdk_root: Path,
) -> dict[str, Any]:
    chunk_dir = out_dir / f"chunk-{chunk_index:04d}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    activation_path = chunk_dir / "activation.npy"
    weight_path = chunk_dir / "weight.npy"
    output_path = chunk_dir / "output.npy"
    phase_path = chunk_dir / "phase.log"
    np.save(activation_path, activation.astype(np.float16, copy=False))
    np.save(weight_path, weight.astype(np.float16, copy=False))
    command = [
        str(sdk_root / "cs_python"),
        str(CHAIN_STEP_ADAPTER),
        "--compile-dir",
        str(compile_dir),
        "--width",
        str(width),
        "--height",
        "1",
        "--chunk-size",
        str(IN_DIM_PER_PE),
        "--input",
        f"activation:{activation_path}:f16:{IN_DIM_PER_PE}",
        "--input",
        f"weight:{weight_path}:f16:{IN_DIM_PER_PE}",
        "--output",
        f"output:{output_path}:f32:1:{width - 1},0,1,1",
        "--phase-trace",
        str(phase_path),
    ]
    exit_code, stdout, stderr, timed_out = run_adapter(command, cwd=REPO_ROOT)
    output_value: float | None = None
    output_sha = ""
    output_ready = output_path.is_file()
    if output_ready:
        values = np.load(output_path, allow_pickle=False).astype(np.float32).reshape(-1)
        output_ready = values.size == 1
        if output_ready:
            output_value = float(values[0])
            output_sha = sha256_file(output_path)
    return {
        "chunkIndex": chunk_index,
        "width": width,
        "compileDir": rel(compile_dir),
        "activation": artifact(activation_path),
        "weight": artifact(weight_path),
        "output": artifact(output_path) if output_path.is_file() else None,
        "outputValue": output_value,
        "outputSha256": output_sha,
        "phaseTrace": artifact(phase_path) if phase_path.is_file() else None,
        "phaseTail": (
            phase_path.read_text(encoding="utf-8").splitlines()[-12:]
            if phase_path.is_file()
            else []
        ),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "stdoutTail": stdout.splitlines()[-4:],
        "stderrTail": stderr.splitlines()[-4:],
        "command": command,
        "status": "succeeded" if exit_code == 0 and output_ready else "blocked",
    }


def generated_token_ids(reference_export: dict[str, Any]) -> list[int]:
    transcript = reference_export.get("decodeTranscript") or {}
    generated = transcript.get("generatedTokenIds")
    if isinstance(generated, dict) and isinstance(generated.get("preview"), list):
        return [int(item) for item in generated["preview"]]
    if isinstance(generated, list):
        return [int(item) for item in generated]
    return []


def reference_prefill_logits_path(reference_export: dict[str, Any]) -> Path:
    for item in (reference_export.get("decodeTranscript") or {}).get("logitsDigests") or []:
        if isinstance(item, dict) and item.get("phase") == "prefill":
            path = item.get("path")
            if isinstance(path, str) and path:
                return resolve(Path(path))
    raise ValueError("prefill_logits_reference_missing")


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.manifest)
    fixture_root = resolve(args.fixture_root)
    reference_export_path = resolve(args.reference_export)
    out_dir = resolve(args.out_dir)
    sdk_root = resolve(args.sdk_root)
    cells_root = resolve(args.cells_root)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_json(manifest_path)
    fixture_manifest_path = fixture_root / "frozen-reference.manifest.json"
    fixture_manifest = load_json(fixture_manifest_path)
    reference_export = load_json(reference_export_path)
    source_root = weight_root(manifest_path, manifest)
    post_ffn_path = fixture_tensor_path(
        fixture_root=fixture_root,
        fixture_manifest=fixture_manifest,
        layer_index=FINAL_LAYER_INDEX,
        probe="post_ffn",
    )
    post_ffn = np.load(post_ffn_path, allow_pickle=False).astype(np.float32)
    hidden_rows = post_ffn.reshape(-1, HIDDEN_SIZE)
    final_input = hidden_rows[-1]

    norm_weight = f16_tensor_slice(
        manifest=manifest,
        root=source_root,
        tensor_name="model.language_model.norm.weight",
        elem_offset=0,
        elem_count=HIDDEN_SIZE,
    ).astype(np.float32)
    token_id = int(args.token_id)
    lm_head_row = f16_tensor_slice(
        manifest=manifest,
        root=source_root,
        tensor_name="model.language_model.embed_tokens.weight",
        elem_offset=token_id * HIDDEN_SIZE,
        elem_count=HIDDEN_SIZE,
    )
    rms = np.sqrt(np.mean(final_input * final_input) + RMS_NORM_EPS)
    normalized = (final_input / rms) * norm_weight
    activation = normalized.astype(np.float16)
    cpu_raw = float(np.dot(activation.astype(np.float32), lm_head_row.astype(np.float32)))
    cpu_softcapped = float(FINAL_LOGIT_SOFTCAP * np.tanh(cpu_raw / FINAL_LOGIT_SOFTCAP))

    logits_path = reference_prefill_logits_path(reference_export)
    logits = np.fromfile(logits_path, dtype=np.float32)
    if token_id < 0 or token_id >= logits.size:
        raise ValueError(f"token_id_out_of_range:{token_id}:{logits.size}")
    expected_logit = float(logits[token_id])
    expected_token_id = int(np.argmax(logits))
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
    csl_softcapped = float(FINAL_LOGIT_SOFTCAP * np.tanh(csl_raw / FINAL_LOGIT_SOFTCAP))
    csl_matches_cpu = len(chunk_values) == len(chunk_results) and all(
        abs(float(item.get("outputValue") or 0.0) - float(item["cpuPartial"])) <= 1.0e-4
        for item in chunk_results
        if item.get("status") == "succeeded"
    )
    logit_abs_diff = abs(csl_softcapped - expected_logit)
    all_chunks_succeeded = len(chunk_results) > 0 and all(
        item.get("status") == "succeeded" for item in chunk_results
    )
    token_matches = token_id == expected_token_id and (
        not generated_tokens or token_id == int(generated_tokens[0])
    )
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

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_doppler_selected_logit_splice_receipt",
        "receiptClass": "manifest_shape_doppler_selected_logit_splice",
        "comparisonMode": "parity",
        "verdict": verdict,
        "blockers": blockers,
        "modelId": MODEL_ID,
        "manifestPath": rel(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        "referenceFixtureHash": fixture_manifest["fixtureDigest"],
        "sourceProgram": {
            "authoringSurface": "doppler_execution_v1",
            "manifestSha256": str(reference_export.get("manifestSha256") or ""),
            "executionGraphSha256": str(reference_export.get("executionGraphSha256") or ""),
            "weightSetSha256": str(reference_export.get("weightSetSha256") or ""),
            "inputSetSha256": str(reference_export.get("inputSetSha256") or ""),
            "referenceExport": artifact(reference_export_path),
        },
        "splicePoint": {
            "kind": "selected_lm_head_logit",
            "layerIndex": FINAL_LAYER_INDEX,
            "inputProbe": "post_ffn",
            "promptTokenCount": int(hidden_rows.shape[0]),
            "selectedTokenId": token_id,
            "selectedText": " blue" if token_id == DEFAULT_TOKEN_ID else None,
        },
        "dopplerReference": {
            "fixtureManifest": artifact(fixture_manifest_path),
            "inputTensor": artifact(post_ffn_path),
            "prefillLogits": artifact(logits_path),
            "expectedTokenId": expected_token_id,
            "generatedTokenIds": generated_tokens,
            "expectedSelectedLogit": expected_logit,
        },
        "weights": {
            "sourceRoot": rel(source_root),
            "finalNormTensor": "model.language_model.norm.weight",
            "lmHeadTensor": "model.language_model.embed_tokens.weight",
            "lmHeadTiedEmbedding": True,
            "finalNormSha256": tensor_sha256(norm_weight.astype(np.float16)),
            "selectedLmHeadRowSha256": tensor_sha256(lm_head_row),
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
            "softcap": FINAL_LOGIT_SOFTCAP,
            "rmsNormEps": RMS_NORM_EPS,
            "logitAbsDiff": logit_abs_diff,
            "atol": float(args.atol),
        },
        "claim": {
            "scope": (
                "Doppler supplies real Gemma 4 31B af16 post-FFN state for the "
                "final prompt position; CSL computes the selected tied lm-head "
                "logit for the Doppler argmax token across hidden chunks."
            ),
            "notWhat": (
                "Not a full-vocabulary argmax, not a full layer-59 CSL run, "
                "and not hardware execution. It avoids the full-logits copyback "
                "wall by binding one selected token logit."
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
