#!/usr/bin/env python3
"""Run and record the Gemma-4 E2B manifest-shape attention-core receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    "bench/out/manifest-shape/"
    "gemma-4-e2b-manifest-shape-attention-core.json"
)
DEFAULT_EXECUTION_MANIFEST = (
    "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
)
DEFAULT_KERNEL = (
    "bench/runners/csl-runners/gemma4_e2b_manifest_attention_core.csl"
)
DEFAULT_RUNNER = (
    "bench/runners/csl-runners/gemma4_e2b_manifest_attention_core.py"
)
DEFAULT_TMPDIR = REPO_ROOT / "bench/out/scratch/csl-sdk-2.10-tmp"
DEFAULT_SCRATCH_CWD = (
    REPO_ROOT / "bench/out/scratch/gemma4-e2b-manifest-attention-core"
)
SHAPES = (
    {"attentionKind": "local", "headDim": 256},
    {"attentionKind": "global", "headDim": 512},
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=DEFAULT_OUT)
    parser.add_argument("--execution-manifest", default=DEFAULT_EXECUTION_MANIFEST)
    parser.add_argument("--kernel-source", default=DEFAULT_KERNEL)
    parser.add_argument("--runner", default=DEFAULT_RUNNER)
    parser.add_argument(
        "--sdk-root",
        default=os.environ.get("DOE_CSL_SDK_ROOT", ""),
        help=(
            "Cerebras SDK root. Defaults to DOE_CSL_SDK_ROOT, then the "
            "local SDK 2.10 install when present."
        ),
    )
    parser.add_argument(
        "--cs-python",
        default=os.environ.get("DOE_CSL_CS_PYTHON", ""),
        help="Explicit cs_python executable.",
    )
    parser.add_argument("--cmaddr", default=os.environ.get("DOE_CSL_CMADDR", ""))
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {rel(path)}")
    return payload


def file_link(path: Path) -> dict[str, Any]:
    link: dict[str, Any] = {"path": rel(path), "exists": path.is_file()}
    if path.is_file():
        link["sha256"] = sha256_file(path)
    return link


def classify_subprocess_failure(proc: subprocess.CompletedProcess[str]) -> str:
    text = f"{proc.stdout}\n{proc.stderr}"
    if "Failed to create container process: Operation not permitted" in text:
        return "sdk_container_launch_not_permitted"
    if "root filesystem extraction failed" in text:
        return "sdk_container_rootfs_extract_failed"
    if "Environment variable 'GITTOP' is undefined" in text:
        return "sdk_direct_rootfs_gittop_missing"
    if "elf2jsondebug: not found" in text:
        return "sdk_direct_rootfs_absolute_cb_missing"
    return "sdk_subprocess_failed"


def select_cs_python(args: argparse.Namespace) -> Path | str:
    if args.cs_python:
        selected = Path(args.cs_python)
        return selected if args.cs_python != "cs_python" else "cs_python"
    # Prefer the Doe-local singularity wrapper when both singularity (or
    # apptainer) and a SIF adjacent to the SDK are available. The SDK's
    # own cs_python wrapper picks --direct-rootfs first, which does NOT
    # bind /cbcore for cslc subprocesses and breaks the paint flow with
    # "Could not find source code for /cbcore/src/sdk/ucode/io_port.csl".
    # The wrapper falls back to the SDK default when singularity is not
    # available, so this branch is safe on hosts without singularity.
    singularity_wrapper = (
        REPO_ROOT / "runtime" / "zig" / "tools" / "cs_python_singularity.sh"
    )
    if singularity_wrapper.is_file() and (
        shutil.which("singularity") or shutil.which("apptainer")
    ):
        return singularity_wrapper
    if args.sdk_root:
        return Path(args.sdk_root) / "cs_python"
    sdk210 = Path("/home/x/cerebras-sdk-2.10.0/cs_python")
    if sdk210.is_file():
        return sdk210
    return Path("/home/x/cerebras-sdk/cs_python")


def csl_env() -> dict[str, str]:
    env = os.environ.copy()
    tmpdir = Path(env.get("DOE_CSL_TMPDIR", str(DEFAULT_TMPDIR)))
    tmpdir.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmpdir)
    env.setdefault("APPTAINER_TMPDIR", str(tmpdir))
    env.setdefault("SINGULARITY_TMPDIR", str(tmpdir))
    scratch_cwd = Path(env.get("DOE_CSL_SCRATCH_CWD", str(DEFAULT_SCRATCH_CWD)))
    scratch_cwd.mkdir(parents=True, exist_ok=True)
    env["DOE_CSL_SCRATCH_CWD"] = str(scratch_cwd)
    return env


def blocked_payload(
    args: argparse.Namespace,
    *,
    blocker: str,
    details: list[str],
) -> dict[str, Any]:
    manifest_path = resolve(args.execution_manifest)
    kernel_path = resolve(args.kernel_source)
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_manifest_shape_attention_core",
        "status": "blocked",
        "verdict": "manifest_shape_attention_core_blocked",
        "modelId": "gemma-4-e2b-it",
        "claimable": False,
        "inputs": {
            "executionManifest": file_link(manifest_path),
            "kernelSource": file_link(kernel_path),
        },
        "manifestShapeContract": manifest_shape_contract(manifest_path),
        "coverage": coverage_from_shape_runs([]),
        "shapeRuns": [],
        "groupedKvEvidence": {
            "numAttentionHeads": 8,
            "numKeyValueHeads": 1,
            "queryHeadsPerKvHead": 8,
            "executed": False,
        },
        "claimScope": claim_scope(),
        "blockers": [blocker],
        "errors": details,
    }


def manifest_shape_contract(manifest_path: Path) -> dict[str, Any]:
    fallback = {
        "localHeadDim": 256,
        "globalHeadDim": 512,
        "numAttentionHeads": 8,
        "numKeyValueHeads": 1,
        "numLayers": 35,
        "hiddenSize": 1536,
    }
    if not manifest_path.is_file():
        return fallback
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback
    config = manifest.get("modelConfig")
    if not isinstance(config, dict):
        return fallback
    return {
        "localHeadDim": int(config.get("headDim", fallback["localHeadDim"])),
        "globalHeadDim": int(
            config.get("globalHeadDim", fallback["globalHeadDim"])
        ),
        "numAttentionHeads": int(config.get("numHeads", 8)),
        "numKeyValueHeads": int(config.get("numKeyValueHeads", 1)),
        "numLayers": int(config.get("numLayers", 35)),
        "hiddenSize": int(config.get("hiddenDim", 1536)),
    }


def coverage_from_shape_runs(shape_runs: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [
        run for run in shape_runs
        if run.get("status") == "succeeded"
        and (run.get("executedRun") or {}).get("numericalParity", {}).get("passed")
    ]
    local = any(run.get("attentionKind") == "local" for run in successful)
    global_ = any(run.get("attentionKind") == "global" for run in successful)
    return {
        "localHeadDimExecuted": local,
        "globalHeadDimExecuted": global_,
        "groupedKvExecuted": local and global_,
        "attentionCoreCslRuntimeExecuted": local and global_,
        "embedUnembedExecuted": False,
        "logitsParityExecuted": False,
        "hardwareExecuted": False,
        "claimable": False,
    }


def claim_scope() -> dict[str, Any]:
    return {
        "claimable": False,
        "summary": (
            "Executed attention-core diagnostic only. This receipt proves "
            "SdkLayout can compile and run the E2B local/global head "
            "dimensions with grouped-KV stream reuse, but it does not "
            "execute embed/unembed, decoder stack, logits parity, hardware, "
            "or performance evidence."
        ),
        "notClaimable": [
            "full Gemma 4 E2B manifest-shape Doe/CSL execution",
            "Doppler production inference parity",
            "Cerebras hardware execution",
            "throughput or latency performance",
        ],
    }


def shape_contract(shape: dict[str, Any]) -> dict[str, int]:
    return {
        "headDim": int(shape["headDim"]),
        "numAttentionHeads": 8,
        "numKeyValueHeads": 1,
        "groupedKvQueryHeadsPerKvHead": 8,
    }


def empty_executed_run(status: str, elapsed_ms: float | None) -> dict[str, Any]:
    return {
        "status": status,
        "elapsedMs": elapsed_ms,
        "runtimeStop": {
            "reached": False,
            "elapsedMs": None,
            "error": status,
        },
        "failure": {
            "errorType": status,
            "message": status,
            "completedQueryHeads": 0,
        },
        "sendReceiveCounts": {"sends": 0, "receives": 0},
        "observedBytesTransferredTotal": 0,
        "streamWaitMs": {"q": 0.0, "k": 0.0, "v": 0.0, "out": 0.0},
        "numericalParity": {
            "passed": False,
            "maxAbsErr": 0.0,
            "atol": 0.0,
            "comparison": "bit_exact_np_array_equal",
        },
        "perQueryHead": [],
    }


def normalize_shape_run(
    run: dict[str, Any],
    *,
    shape: dict[str, Any],
    elapsed_ms: float,
) -> dict[str, Any]:
    run.setdefault("schemaVersion", 1)
    run.setdefault(
        "artifactKind",
        "doe_gemma4_e2b_manifest_shape_attention_core_shape_run",
    )
    run.setdefault("attentionKind", shape["attentionKind"])
    run["shape"] = {**shape_contract(shape), **(run.get("shape") or {})}
    status = str(run.get("status") or "blocked:unknown")
    executed = run.get("executedRun")
    if not isinstance(executed, dict):
        run["executedRun"] = empty_executed_run(status, elapsed_ms)
    else:
        executed.setdefault("status", status)
        executed.setdefault("elapsedMs", elapsed_ms)
        executed.setdefault("runtimeStop", {"reached": False})
        executed.setdefault("perQueryHead", [])
        parity = executed.setdefault("numericalParity", {})
        parity.setdefault("passed", False)
        parity.setdefault("maxAbsErr", 0.0)
        parity.setdefault("atol", 0.0)
        parity.setdefault("comparison", "bit_exact_np_array_equal")
    return run


def run_shape(
    args: argparse.Namespace,
    *,
    cs_python: Path | str,
    shape: dict[str, Any],
    shape_out: Path,
) -> dict[str, Any]:
    runner_path = resolve(args.runner)
    compile_out = (
        REPO_ROOT / "bench/out/manifest-shape/attention-core/compile"
        / f"{shape['attentionKind']}-hd{shape['headDim']}"
    )
    command = [
        str(cs_python),
        str(runner_path),
        "--attention-kind",
        str(shape["attentionKind"]),
        "--head-dim",
        str(shape["headDim"]),
        "--kernel-source",
        str(resolve(args.kernel_source)),
        "--compile-out",
        str(compile_out),
        "--out-json",
        str(shape_out),
    ]
    if args.cmaddr:
        command.extend(["--cmaddr", args.cmaddr])

    try:
        shape_out.unlink()
    except FileNotFoundError:
        pass

    start = time.time()
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=csl_env(),
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    elapsed_ms = (time.time() - start) * 1000.0
    if not shape_out.is_file():
        failure_code = classify_subprocess_failure(proc)
        return {
            "schemaVersion": 1,
            "artifactKind": (
                "doe_gemma4_e2b_manifest_shape_attention_core_shape_run"
            ),
            "status": f"blocked:{failure_code}",
            "attentionKind": shape["attentionKind"],
            "shape": shape_contract(shape),
            "executedRun": empty_executed_run(
                f"blocked:{failure_code}",
                elapsed_ms,
            ),
            "failureCode": failure_code,
            "subprocess": {
                "returnCode": proc.returncode,
                "elapsedMs": elapsed_ms,
                "stdoutTail": proc.stdout[-800:],
                "stderrTail": proc.stderr[-800:],
            },
        }
    run = load_json(shape_out)
    normalize_shape_run(run, shape=shape, elapsed_ms=elapsed_ms)
    if proc.returncode != 0:
        run["failureCode"] = classify_subprocess_failure(proc)
    run["subprocess"] = {
        "returnCode": proc.returncode,
        "elapsedMs": elapsed_ms,
        "stdoutTail": proc.stdout[-800:],
        "stderrTail": proc.stderr[-800:],
    }
    return run


def build_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    manifest_path = resolve(args.execution_manifest)
    kernel_path = resolve(args.kernel_source)
    runner_path = resolve(args.runner)
    cs_python = select_cs_python(args)
    if cs_python != "cs_python" and not Path(cs_python).is_file():
        return (
            blocked_payload(
                args,
                blocker="cs_python_not_available",
                details=[f"cs_python not found at {cs_python}"],
            ),
            0,
        )
    if not runner_path.is_file():
        return (
            blocked_payload(
                args,
                blocker="manifest_shape_attention_core_runner_missing",
                details=[f"runner not found: {rel(runner_path)}"],
            ),
            0,
        )
    if not kernel_path.is_file():
        return (
            blocked_payload(
                args,
                blocker="manifest_shape_attention_core_kernel_missing",
                details=[f"kernel not found: {rel(kernel_path)}"],
            ),
            0,
        )

    shape_dir = REPO_ROOT / "bench/out/manifest-shape/attention-core"
    shape_dir.mkdir(parents=True, exist_ok=True)
    shape_runs = [
        run_shape(
            args,
            cs_python=cs_python,
            shape=shape,
            shape_out=shape_dir / (
                f"gemma-4-e2b-attention-core-{shape['attentionKind']}"
                f"-hd{shape['headDim']}.json"
            ),
        )
        for shape in SHAPES
    ]
    coverage = coverage_from_shape_runs(shape_runs)
    failed_runs = [
        run for run in shape_runs
        if run.get("status") != "succeeded"
        or (run.get("subprocess") or {}).get("returnCode") != 0
        or not (run.get("executedRun") or {})
        .get("numericalParity", {})
        .get("passed")
    ]
    status = "succeeded" if not failed_runs else "failed"
    verdict = (
        "manifest_shape_attention_core_passed"
        if status == "succeeded"
        else "manifest_shape_attention_core_failed"
    )
    failure_codes = sorted({
        str(run.get("failureCode"))
        for run in failed_runs
        if run.get("failureCode")
    })
    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_manifest_shape_attention_core",
        "status": status,
        "verdict": verdict,
        "modelId": "gemma-4-e2b-it",
        "claimable": False,
        "inputs": {
            "executionManifest": file_link(manifest_path),
            "kernelSource": file_link(kernel_path),
        },
        "manifestShapeContract": manifest_shape_contract(manifest_path),
        "coverage": coverage,
        "shapeRuns": shape_runs,
        "groupedKvEvidence": {
            "numAttentionHeads": 8,
            "numKeyValueHeads": 1,
            "queryHeadsPerKvHead": 8,
            "executed": coverage["groupedKvExecuted"],
            "kvSourceHeadByQueryHead": [0 for _ in range(8)],
        },
        "claimScope": claim_scope(),
        "blockers": [] if status == "succeeded" else (
            failure_codes or ["manifest_shape_attention_core_execution_failed"]
        ),
        "errors": [
            run.get("status", "unknown")
            for run in failed_runs
        ],
    }
    return payload, 0 if status == "succeeded" else 1


def main() -> int:
    args = parse_args()
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload, rc = build_payload(args)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        payload = blocked_payload(
            args,
            blocker="manifest_shape_attention_core_record_failed",
            details=[f"{type(exc).__name__}: {exc}"],
        )
        rc = 1
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
