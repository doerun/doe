#!/usr/bin/env python3
"""Run a Doppler-state to CSL top-k selected-logit splice for Gemma 4 31B AF16."""

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
DEFAULT_TAIL_CELLS_ROOT = (
    REPO_ROOT / "bench/runners/csl-runners/doppler-csl-splice-cells"
)
CHAIN_STEP_ADAPTER = RUNNER_DIR / "chain_step_adapter.py"
HIDDEN_SIZE = 5376
IN_DIM_PER_PE = 32
CHUNK_PE_WIDTH = 32
FINAL_LAYER_INDEX = 59
DEFAULT_TOKEN_ID = 3730
FINAL_LOGIT_SOFTCAP = 30.0
RMS_NORM_EPS = 1.0e-6
FINAL_NORM_ATOL = 5.0e-3
ADAPTER_WATCHDOG = 240


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--reference-export", type=Path, default=DEFAULT_REFERENCE_EXPORT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--cells-root", type=Path, default=DEFAULT_CELLS_ROOT)
    parser.add_argument("--tail-cells-root", type=Path, default=DEFAULT_TAIL_CELLS_ROOT)
    parser.add_argument(
        "--token-id",
        type=int,
        default=None,
        help="Optional primary token id. Default uses Doppler's reference argmax.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=32,
        help="Number of Doppler top logits to replay through CSL.",
    )
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
    artifact_kind: str = "gemma4_31b_af16_selected_logit_compile_receipt",
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
        "artifactKind": artifact_kind,
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


def compile_final_norm_cell(
    *,
    hidden_size: int,
    weight_offset: bool,
    out_dir: Path,
    sdk_root: Path,
    tail_cells_root: Path,
    artifact_kind: str,
) -> dict[str, Any]:
    compile_root = out_dir / "compile-final-norm-f16"
    compile_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        tail_cells_root / "final_norm_f16_layout.csl",
        compile_root / "layout.csl",
    )
    shutil.copy2(
        tail_cells_root / "final_norm_f16_pe_program.csl",
        compile_root / "pe_program.csl",
    )
    compile_dir = compile_root / "compiled"
    if compile_dir.exists():
        shutil.rmtree(compile_dir)
    command = [
        str(sdk_root / "cslc"),
        "layout.csl",
        "--arch=wse3",
        "--fabric-dims=11,5",
        "--fabric-offsets=4,1",
        (
            "--params="
            f"hidden_size:{hidden_size},"
            f"weight_offset:{1 if weight_offset else 0}"
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
        "artifactKind": artifact_kind,
        "status": "succeeded" if completed.returncode == 0 else "blocked",
        "blockers": [] if completed.returncode == 0 else [f"cslc_exit_{completed.returncode}"],
        "compileDir": rel(compile_dir),
        "command": command,
        "params": {
            "hiddenSize": hidden_size,
            "weightOffset": bool(weight_offset),
        },
        "stdoutTail": completed.stdout.splitlines()[-8:],
        "stderrTail": completed.stderr.splitlines()[-8:],
    }
    receipt_path = compile_root / "compile-receipt.json"
    write_json(receipt_path, receipt)
    if completed.returncode != 0:
        raise RuntimeError(f"final_norm_f16_cslc_failed:{hidden_size}")
    return {
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


def run_final_norm_cell(
    *,
    compile_dir: Path,
    input_hidden: np.ndarray,
    norm_weight: np.ndarray,
    expected_activation: np.ndarray,
    out_dir: Path,
    sdk_root: Path,
) -> dict[str, Any]:
    norm_dir = out_dir / "final-norm-csl"
    norm_dir.mkdir(parents=True, exist_ok=True)
    input_path = norm_dir / "input.npy"
    weight_path = norm_dir / "weight.npy"
    output_path = norm_dir / "output.npy"
    phase_path = norm_dir / "phase.log"
    hidden_size = int(expected_activation.size)
    np.save(input_path, input_hidden.astype(np.float16, copy=False))
    np.save(weight_path, norm_weight.astype(np.float16, copy=False))
    command = [
        str(sdk_root / "cs_python"),
        str(CHAIN_STEP_ADAPTER),
        "--compile-dir",
        str(compile_dir),
        "--width",
        "1",
        "--height",
        "1",
        "--chunk-size",
        str(hidden_size),
        "--input",
        f"input:{input_path}:f16:{hidden_size}",
        "--input",
        f"weight:{weight_path}:f16:{hidden_size}",
        "--output",
        f"output:{output_path}:f16:{hidden_size}:0,0,1,1",
        "--phase-trace",
        str(phase_path),
    ]
    exit_code, stdout, stderr, timed_out = run_adapter(command, cwd=REPO_ROOT)
    output_ready = output_path.is_file()
    actual = np.array([], dtype=np.float16)
    if output_ready:
        actual = np.load(output_path, allow_pickle=False).astype(np.float16).reshape(-1)
        output_ready = actual.size == hidden_size
    expected_f16 = expected_activation.astype(np.float16, copy=False).reshape(-1)
    max_abs = (
        float(np.max(np.abs(actual.astype(np.float32) - expected_f16.astype(np.float32))))
        if output_ready
        else None
    )
    exact_match = bool(output_ready and np.array_equal(actual, expected_f16))
    within_atol = bool(
        output_ready
        and max_abs is not None
        and max_abs <= FINAL_NORM_ATOL
    )
    return {
        "kernel": "final_norm_f16",
        "status": "succeeded" if exit_code == 0 and output_ready else "blocked",
        "compileDir": rel(compile_dir),
        "input": artifact(input_path),
        "weight": artifact(weight_path),
        "output": artifact(output_path) if output_path.is_file() else None,
        "outputSha256": sha256_file(output_path) if output_path.is_file() else "",
        "phaseTrace": artifact(phase_path) if phase_path.is_file() else None,
        "phaseTail": (
            phase_path.read_text(encoding="utf-8").splitlines()[-12:]
            if phase_path.is_file()
            else []
        ),
        "hiddenSize": hidden_size,
        "maxAbsDiffVsHostF16": max_abs,
        "exactMatchVsHostF16": exact_match,
        "atol": FINAL_NORM_ATOL,
        "withinAtol": within_atol,
        "exitCode": exit_code,
        "timedOut": timed_out,
        "stdoutTail": stdout.splitlines()[-4:],
        "stderrTail": stderr.splitlines()[-4:],
        "command": command,
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


def reference_top_token_ids(logits: np.ndarray, top_k: int) -> list[int]:
    k = max(1, min(int(top_k), int(logits.size)))
    indices = np.argpartition(logits, -k)[-k:]
    ordered = indices[np.argsort(logits[indices])[::-1]]
    return [int(item) for item in ordered]


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.manifest)
    fixture_root = resolve(args.fixture_root)
    reference_export_path = resolve(args.reference_export)
    out_dir = resolve(args.out_dir)
    sdk_root = resolve(args.sdk_root)
    cells_root = resolve(args.cells_root)
    tail_cells_root = resolve(args.tail_cells_root)
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
    rms = np.sqrt(np.mean(final_input * final_input) + RMS_NORM_EPS)
    normalized = (final_input / rms) * norm_weight
    host_activation = normalized.astype(np.float16)
    final_norm_compile = compile_final_norm_cell(
        hidden_size=HIDDEN_SIZE,
        weight_offset=False,
        out_dir=out_dir,
        sdk_root=sdk_root,
        tail_cells_root=tail_cells_root,
        artifact_kind="gemma4_31b_af16_final_norm_f16_compile_receipt",
    )
    final_norm_run = run_final_norm_cell(
        compile_dir=Path(str(final_norm_compile["compileDir"])),
        input_hidden=final_input,
        norm_weight=norm_weight,
        expected_activation=host_activation,
        out_dir=out_dir,
        sdk_root=sdk_root,
    )
    final_norm_output = final_norm_run.get("output") or {}
    if final_norm_run["status"] == "succeeded" and final_norm_output.get("path"):
        activation = np.load(
            resolve(Path(str(final_norm_output["path"]))),
            allow_pickle=False,
        ).astype(np.float16)
    else:
        activation = host_activation

    logits_path = reference_prefill_logits_path(reference_export)
    logits = np.fromfile(logits_path, dtype=np.float32)
    expected_token_id = int(np.argmax(logits))
    generated_tokens = generated_token_ids(reference_export)
    top_token_ids = reference_top_token_ids(logits, int(args.top_k))
    primary_token_id = int(args.token_id) if args.token_id is not None else expected_token_id
    if primary_token_id < 0 or primary_token_id >= logits.size:
        raise ValueError(f"token_id_out_of_range:{primary_token_id}:{logits.size}")
    candidate_token_ids = [primary_token_id] + [
        token for token in top_token_ids if token != primary_token_id
    ]
    rank_by_token = {token: index + 1 for index, token in enumerate(top_token_ids)}

    compile_cache: dict[int, dict[str, Any]] = {}
    chunk_width = max(1, int(args.chunk_pe_width))
    chunk_elems = chunk_width * IN_DIM_PER_PE

    def run_token(token_id: int) -> dict[str, Any]:
        lm_head_row = f16_tensor_slice(
            manifest=manifest,
            root=source_root,
            tensor_name="model.language_model.embed_tokens.weight",
            elem_offset=token_id * HIDDEN_SIZE,
            elem_count=HIDDEN_SIZE,
        )
        chunk_results: list[dict[str, Any]] = []
        chunk_values: list[float] = []
        chunk_index = 0
        token_dir = out_dir / f"token-{token_id}"
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
                    artifact_kind="gemma4_31b_af16_selected_logit_compile_receipt",
                )
            result = run_chunk(
                chunk_index=chunk_index,
                width=width,
                compile_dir=Path(str(compile_cache[width]["compileDir"])),
                activation=act_chunk,
                weight=weight_chunk,
                out_dir=token_dir,
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

        cpu_raw = float(
            np.dot(activation.astype(np.float32), lm_head_row.astype(np.float32))
        )
        cpu_softcapped = float(
            FINAL_LOGIT_SOFTCAP * np.tanh(cpu_raw / FINAL_LOGIT_SOFTCAP)
        )
        csl_raw = float(np.sum(np.array(chunk_values, dtype=np.float32)))
        csl_softcapped = float(
            FINAL_LOGIT_SOFTCAP * np.tanh(csl_raw / FINAL_LOGIT_SOFTCAP)
        )
        expected_logit = float(logits[token_id])
        logit_abs_diff = abs(csl_softcapped - expected_logit)
        csl_matches_cpu = len(chunk_values) == len(chunk_results) and all(
            abs(float(item.get("outputValue") or 0.0) - float(item["cpuPartial"])) <= 1.0e-4
            for item in chunk_results
            if item.get("status") == "succeeded"
        )
        all_chunks_succeeded = len(chunk_results) > 0 and all(
            item.get("status") == "succeeded" for item in chunk_results
        )
        return {
            "tokenId": token_id,
            "referenceRank": rank_by_token.get(token_id),
            "expectedLogit": expected_logit,
            "rawLogit": csl_raw,
            "softcappedLogit": csl_softcapped,
            "cpuRawLogit": cpu_raw,
            "cpuSoftcappedLogit": cpu_softcapped,
            "logitAbsDiff": logit_abs_diff,
            "chunkCount": len(chunk_results),
            "chunkResults": chunk_results,
            "allChunksSucceeded": all_chunks_succeeded,
            "cslCpuPartialsMatch": csl_matches_cpu,
            "lmHeadRowSha256": tensor_sha256(lm_head_row),
        }

    candidate_runs = [run_token(token_id) for token_id in candidate_token_ids]
    primary_run = candidate_runs[0]
    max_logit_abs_diff = max(float(run["logitAbsDiff"]) for run in candidate_runs)
    csl_argmax_token_id = int(
        max(candidate_runs, key=lambda run: float(run["softcappedLogit"]))["tokenId"]
    )
    reference_top1_top2_margin = (
        float(logits[top_token_ids[0]] - logits[top_token_ids[1]])
        if len(top_token_ids) > 1
        else float("inf")
    )
    decision_margin_lower_bound = reference_top1_top2_margin - (
        2.0 * max_logit_abs_diff
    )
    argmax_decision_stable = (
        csl_argmax_token_id == expected_token_id
        and decision_margin_lower_bound > 0.0
    )
    all_candidates_succeeded = all(
        bool(run["allChunksSucceeded"]) for run in candidate_runs
    )
    all_candidates_match_cpu = all(
        bool(run["cslCpuPartialsMatch"]) for run in candidate_runs
    )
    all_candidates_match_doppler = all(
        float(run["logitAbsDiff"]) <= float(args.atol) for run in candidate_runs
    )
    token_matches = csl_argmax_token_id == expected_token_id and (
        not generated_tokens or expected_token_id == int(generated_tokens[0])
    )
    comparison_mode = (
        "parity"
        if all_candidates_match_doppler
        else "argmax_decision_bound"
    )
    verdict = (
        "pass"
        if all_candidates_succeeded
        and final_norm_run["status"] == "succeeded"
        and bool(final_norm_run.get("withinAtol"))
        and all_candidates_match_cpu
        and argmax_decision_stable
        and token_matches
        else "blocked"
    )
    blockers: list[str] = []
    if not all_candidates_succeeded:
        blockers.append("topk_selected_logits_csl_chunk_blocked")
    if final_norm_run["status"] != "succeeded":
        blockers.append("final_norm_csl_blocked")
    elif not final_norm_run.get("withinAtol"):
        blockers.append("final_norm_csl_host_f16_exceeds_tolerance")
    if not all_candidates_match_cpu:
        blockers.append("topk_selected_logits_csl_cpu_partial_mismatch")
    if not argmax_decision_stable:
        blockers.append("topk_selected_logits_decision_margin_not_positive")
    if not token_matches:
        blockers.append("topk_selected_logits_argmax_mismatch")

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_doppler_selected_logit_splice_receipt",
        "receiptClass": "manifest_shape_doppler_selected_logit_splice",
        "comparisonMode": comparison_mode,
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
            "selectedTokenId": primary_token_id,
            "selectedTokenIds": candidate_token_ids,
            "topK": len(top_token_ids),
            "selectedText": " blue" if primary_token_id == DEFAULT_TOKEN_ID else None,
        },
        "dopplerReference": {
            "fixtureManifest": artifact(fixture_manifest_path),
            "inputTensor": artifact(post_ffn_path),
            "prefillLogits": artifact(logits_path),
            "expectedTokenId": expected_token_id,
            "expectedTopKTokenIds": top_token_ids,
            "expectedTopKLogits": [
                {"rank": index + 1, "tokenId": token, "logit": float(logits[token])}
                for index, token in enumerate(top_token_ids)
            ],
            "generatedTokenIds": generated_tokens,
            "expectedSelectedLogit": float(logits[primary_token_id]),
        },
        "weights": {
            "sourceRoot": rel(source_root),
            "finalNormTensor": "model.language_model.norm.weight",
            "lmHeadTensor": "model.language_model.embed_tokens.weight",
            "lmHeadTiedEmbedding": True,
            "finalNormSha256": tensor_sha256(norm_weight.astype(np.float16)),
            "finalNormCslOutputSha256": str(final_norm_run.get("outputSha256") or ""),
            "selectedLmHeadRowSha256": primary_run["lmHeadRowSha256"],
            "candidateLmHeadRows": [
                {"tokenId": int(run["tokenId"]), "sha256": run["lmHeadRowSha256"]}
                for run in candidate_runs
            ],
        },
        "cslRun": {
            "tailKernels": ["final_norm_f16", "lm_head_prefill"],
            "finalNorm": final_norm_run,
            "kernel": "lm_head_prefill",
            "chunkPeWidth": chunk_width,
            "inDimPerPe": IN_DIM_PER_PE,
            "topK": len(top_token_ids),
            "candidateCount": len(candidate_runs),
            "candidateTokenIds": candidate_token_ids,
            "candidateRuns": candidate_runs,
            "referenceArgmaxTokenId": expected_token_id,
            "cslArgmaxTokenId": csl_argmax_token_id,
            "maxLogitAbsDiff": max_logit_abs_diff,
            "allCandidateLogitsWithinTolerance": all_candidates_match_doppler,
            "strictLogitTolerancePassed": all_candidates_match_doppler,
            "strictLogitToleranceAtol": float(args.atol),
            "referenceTop1Top2Margin": reference_top1_top2_margin,
            "decisionMarginLowerBound": decision_margin_lower_bound,
            "argmaxDecisionStable": argmax_decision_stable,
            "chunkCount": int(primary_run["chunkCount"]),
            "chunkResults": primary_run["chunkResults"],
            "rawLogit": float(primary_run["rawLogit"]),
            "softcappedLogit": float(primary_run["softcappedLogit"]),
            "cpuRawLogit": float(primary_run["cpuRawLogit"]),
            "cpuSoftcappedLogit": float(primary_run["cpuSoftcappedLogit"]),
            "softcap": FINAL_LOGIT_SOFTCAP,
            "rmsNormEps": RMS_NORM_EPS,
            "logitAbsDiff": float(primary_run["logitAbsDiff"]),
            "atol": float(args.atol),
        },
        "claim": {
            "scope": (
                "Doppler supplies real Gemma 4 31B af16 post-FFN state for the "
                "final prompt position; CSL computes final RMSNorm plus the "
                "tied lm-head logits for the Doppler top-k token candidates "
                "across hidden chunks and preserves the top-token decision."
            ),
            "notWhat": (
                "Not a full-vocabulary argmax, not a full layer-59 CSL run, "
                "and not hardware execution. It avoids the full-logits copyback "
                "wall by binding the Doppler top-k candidate logits; strict "
                "logit tolerance status is recorded separately from the "
                "top-token decision bound."
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
        f"(verdict={verdict}, topK={len(top_token_ids)}, "
        f"token={primary_token_id}, maxDiff={max_logit_abs_diff:.6e})"
    )
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
