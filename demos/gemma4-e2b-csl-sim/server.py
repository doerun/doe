#!/usr/bin/env python3
"""Local Gemma 4 E2B WebGPU/CSL demo server."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORT = 8001
SCRATCH_ROOT = Path("bench/out/scratch/gemma4-e2b-csl-sim")
# Depth selector: allowed chain depths. L=1 is the smoke baseline;
# L=35 matches the E2B manifest's modelConfig.numLayers. The server
# writes a depth-specific trace so prior-depth runs are not
# overwritten and can be re-fetched without a new cs_python call.
ALLOWED_NUM_LAYERS = (1, 2, 4, 8, 35)
DEFAULT_NUM_LAYERS = 1


def trace_path_for(num_layers: int) -> Path:
    return SCRATCH_ROOT / f"csl-L{num_layers}-live-trace.json"


def compile_out_for(num_layers: int) -> Path:
    return SCRATCH_ROOT / f"compile-L{num_layers}"


def timeout_seconds_for(num_layers: int) -> int:
    return max(180, num_layers * 15)


def redact(text: str) -> str:
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    return text.replace(sdk_root, "$DOE_CSL_SDK_ROOT")


def cs_python_path() -> str:
    explicit = os.environ.get("DOE_CSL_CS_PYTHON", "")
    if explicit:
        return explicit
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    candidate = Path(sdk_root) / "cs_python"
    if candidate.exists():
        return str(candidate)
    return "cs_python"


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def trace_payload(num_layers: int) -> dict[str, Any]:
    trace_rel = trace_path_for(num_layers)
    trace_abs = REPO_ROOT / trace_rel
    trace = json.loads(trace_abs.read_text(encoding="utf-8"))
    executed = trace.get("executedRun", {})
    output_info = (executed.get("output") or {})
    output_path = REPO_ROOT / output_info.get("path", "")
    output = np.fromfile(output_path, dtype=np.float32)
    parity = executed.get("numericalParity", {})
    return {
        "status": executed.get("status", "unknown"),
        "elapsedMs": executed.get("elapsedMs"),
        "numLayersChained": executed.get("numLayersChained"),
        "maxAbsErr": parity.get("maxAbsErr"),
        "perLayerMaxAbsErr": parity.get("perLayerMaxAbsErr"),
        "tracePath": str(trace_rel),
        "outputPath": output_info.get("path"),
        "outputSha256": sha256_file(output_path),
        "output": [float(x) for x in output],
        "streamTelemetry": executed.get("streams", []),
    }


def run_csl(num_layers: int) -> dict[str, Any]:
    trace_rel = trace_path_for(num_layers)
    (REPO_ROOT / trace_rel).parent.mkdir(parents=True, exist_ok=True)
    command = [
        cs_python_path(),
        "bench/runners/csl-runners/e2b_layer_block_smoke.py",
        "--num-layers",
        str(num_layers),
        "--compile-out",
        str(compile_out_for(num_layers)),
        "--trace-out",
        str(trace_rel),
    ]
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds_for(num_layers),
        check=False,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "returnCode": proc.returncode,
            "numLayersChained": num_layers,
            "stdoutTail": redact(proc.stdout[-4000:]),
            "stderrTail": redact(proc.stderr[-4000:]),
        }
    payload = trace_payload(num_layers)
    payload["returnCode"] = proc.returncode
    payload["stdoutTail"] = redact(proc.stdout[-1200:])
    payload["stderrTail"] = redact(proc.stderr[-1200:])
    return payload


class DemoHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            cs_py = cs_python_path()
            self.send_json({
                "repoRoot": str(REPO_ROOT),
                "csPython": redact(cs_py),
                "csPythonAvailable": Path(cs_py).exists() or cs_py == "cs_python",
            })
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        # /api/run-csl?num_layers=N  where N in ALLOWED_NUM_LAYERS.
        # Missing/invalid num_layers defaults to DEFAULT_NUM_LAYERS (1)
        # with an explicit echo field so the browser never silently
        # gets a depth it didn't ask for.
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        if parsed.path != "/api/run-csl":
            self.send_error(HTTPStatus.NOT_FOUND, "unknown API route")
            return
        qs = parse_qs(parsed.query or "")
        try:
            num_layers = int((qs.get("num_layers") or [str(DEFAULT_NUM_LAYERS)])[0])
        except (TypeError, ValueError):
            num_layers = DEFAULT_NUM_LAYERS
        if num_layers not in ALLOWED_NUM_LAYERS:
            self.send_json(
                {
                    "status": "failed",
                    "error": (
                        f"num_layers={num_layers} not in allowed set "
                        f"{list(ALLOWED_NUM_LAYERS)}"
                    ),
                    "numLayersRequested": num_layers,
                },
                HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            payload = run_csl(num_layers)
        except subprocess.TimeoutExpired:
            self.send_json(
                {
                    "status": "failed",
                    "error": f"CSL simulator timed out at num_layers={num_layers}",
                    "numLayersRequested": num_layers,
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        except Exception as exc:  # pylint: disable=broad-except
            self.send_json(
                {"status": "failed", "error": str(exc), "numLayersRequested": num_layers},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        payload["numLayersRequested"] = num_layers
        status = HTTPStatus.OK if payload.get("status") == "succeeded" else HTTPStatus.INTERNAL_SERVER_ERROR
        self.send_json(payload, status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.chdir(REPO_ROOT)
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(
        "Gemma 4 E2B WebGPU/CSL demo: "
        f"http://{args.host}:{args.port}/demos/gemma4-e2b-csl-sim/"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
