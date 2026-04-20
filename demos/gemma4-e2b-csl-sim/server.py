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
        "source": "trace",
        "cacheHit": False,
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


def run_csl(num_layers: int, *, force: bool = False) -> dict[str, Any]:
    trace_rel = trace_path_for(num_layers)
    (REPO_ROOT / trace_rel).parent.mkdir(parents=True, exist_ok=True)
    if not force and (REPO_ROOT / trace_rel).is_file():
        payload = trace_payload(num_layers)
        payload["source"] = "cached_trace"
        payload["cacheHit"] = True
        payload["runnerSkipped"] = (
            "matching-depth CSL trace already exists; pass force=1 "
            "to /api/run-csl to request a fresh simfabric run"
        )
        return payload
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
    payload["source"] = "live_simfabric"
    payload["cacheHit"] = False
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
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            cs_py = cs_python_path()
            self.send_json({
                "repoRoot": str(REPO_ROOT),
                "csPython": redact(cs_py),
                "csPythonAvailable": Path(cs_py).exists() or cs_py == "cs_python",
            })
            return
        if parsed.path == "/api/artifact-dir-info":
            qs = parse_qs(parsed.query or "")
            rel_path = (qs.get("path") or [""])[0]
            self.send_json(self.inspect_artifact_dir(rel_path))
            return
        if parsed.path == "/api/trace-host-io-contract":
            qs = parse_qs(parsed.query or "")
            trace_rel = (qs.get("trace") or [""])[0]
            self.send_json(self.inspect_trace_host_io(trace_rel))
            return
        if parsed.path == "/api/bundle-summary":
            self.send_json(self.inspect_bundle_summary())
            return
        if parsed.path == "/api/evidence-commands":
            self.send_json(self.inspect_evidence_commands())
            return
        super().do_GET()

    def inspect_evidence_commands(self) -> dict:
        archive_dir = REPO_ROOT / "bench/out"
        latest_archive = None
        if archive_dir.is_dir():
            archives = sorted(
                archive_dir.glob("doe-cerebras-evidence-*.tar.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if archives:
                latest_archive = str(archives[0].relative_to(REPO_ROOT))
        verify_arg = latest_archive or "<archive.tar.gz>"
        return {
            "ok": True,
            "latestArchive": latest_archive,
            "commands": {
                "bundleRunner":
                    "python3 bench/tools/run_cerebras_evidence_bundle.py",
                "archivePack":
                    "python3 bench/tools/pack_cerebras_validation_archive.py",
                "archiveVerify": (
                    "python3 bench/tools/verify_cerebras_validation_archive.py "
                    f"--archive {verify_arg}"
                ),
            },
            "copyable": {
                "bundleRunner": True,
                "archivePack": True,
                "archiveVerify": latest_archive is not None,
            },
            "statuses": {
                "bundleRunner": "ready",
                "archivePack": "ready",
                "archiveVerify": (
                    "latest archive found"
                    if latest_archive else "run archive pack first"
                ),
            },
            "note": (
                "Repo-relative commands only. The route never returns SDK "
                "binary file bytes or absolute cluster paths."
            ),
        }

    def inspect_bundle_summary(self) -> dict:
        # Stable route for the evidence bundle summary. When the bundle
        # runner has been invoked on this host, returns the passed/
        # failed verdict + step counts; when absent, returns ok=false
        # so the cockpit fails closed rather than silently showing
        # stale state.
        summary_path = (
            REPO_ROOT / "bench/out/cerebras-evidence-bundle/summary.json"
        )
        if not summary_path.is_file():
            return {
                "ok": False,
                "error": "summary not yet produced",
                "hint": (
                    "run bench/tools/run_cerebras_evidence_bundle.py "
                    "or bench/tools/prepare_cerebras_validation_bundle.sh"
                ),
            }
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"summary unreadable: {exc}"}
        return {
            "ok": True,
            "summaryPath": "bench/out/cerebras-evidence-bundle/summary.json",
            "verdict": data.get("verdict"),
            "totalSteps": data.get("totalSteps"),
            "passedSteps": data.get("passedSteps"),
            "failedSteps": data.get("failedSteps"),
            "skippedSteps": data.get("skippedSteps"),
            "stepStatuses": [
                {
                    "step": s.get("step"),
                    "status": s.get("status"),
                    "elapsedMs": s.get("elapsedMs"),
                }
                for s in (data.get("steps") or [])
                if isinstance(s, dict)
            ],
        }

    def inspect_trace_host_io(self, trace_rel: str) -> dict:
        if not trace_rel:
            return {"ok": False, "error": "missing trace parameter"}
        if trace_rel.startswith("/") or ".." in Path(trace_rel).parts:
            return {
                "ok": False,
                "error": "trace must be repo-relative, no '..' allowed",
            }
        abs_path = (REPO_ROOT / trace_rel).resolve()
        try:
            abs_path.relative_to(REPO_ROOT)
        except ValueError:
            return {"ok": False, "error": "path escapes repo root"}
        if not abs_path.is_file():
            return {
                "ok": False,
                "error": f"trace not found: {trace_rel}",
            }
        try:
            trace = json.loads(abs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"trace unreadable: {exc}"}
        smoke = trace.get("layerBlockSmoke") or {}
        layout = smoke.get("hostIoLayout") or []
        executed_run = trace.get("executedRun") or {}
        stream_events = executed_run.get("streamEventsTail") or []
        stream_telemetry = executed_run.get("streamTelemetry") or {}
        per_stream = executed_run.get("streams") or []
        # Cap to 32 events to keep response payload bounded; 32 covers
        # ~4 streams x ~8 event flips in practice, which is plenty for
        # a quick drilldown.
        event_cap = 32
        return {
            "ok": True,
            "tracePath": trace_rel,
            "modelId": trace.get("modelId"),
            "target": trace.get("target"),
            "kernelSourceSha256": smoke.get("kernelSourceSha256"),
            "planSha256": smoke.get("planSha256"),
            "numLayersChained": executed_run.get("numLayersChained"),
            "executedRunStatus": executed_run.get("status"),
            "hostIoLayout": [
                {
                    "streamId": e.get("streamId"),
                    "role": e.get("role"),
                    "dtype": e.get("dtype"),
                    "order": e.get("order"),
                    "elementsPerPe": e.get("elementsPerPe"),
                    "ioBufferSize": e.get("ioBufferSize"),
                    "planPayloadBytes": e.get("planPayloadBytes"),
                    "tileBehavior": e.get("tileBehavior"),
                }
                for e in layout
                if isinstance(e, dict)
            ],
            "sendReceiveCounts": smoke.get("sendReceiveCounts"),
            "ioBufferSizes": smoke.get("ioBufferSizes"),
            "streamTelemetry": {
                "measurementSource": stream_telemetry.get("measurementSource"),
                "streamEventsTailCount": stream_telemetry.get(
                    "streamEventsTailCount"
                ),
            },
            "perStreamCounters": [
                {
                    "streamId": s.get("streamId"),
                    "role": s.get("role"),
                    "operation": s.get("operation"),
                    "issuedCount": s.get("issuedCount"),
                    "completedCount": s.get("completedCount"),
                    "pendingCount": s.get("pendingCount"),
                    "maxQueueDepth": s.get("maxQueueDepth"),
                }
                for s in per_stream
                if isinstance(s, dict)
            ],
            "streamEventsTail": stream_events[:event_cap],
            "streamEventsTruncated": len(stream_events) > event_cap,
            "streamEventsTotalInTrace": len(stream_events),
            "note": (
                "Metadata only. Stream payloads are never returned — "
                "host I/O contract is the schema, not the data."
            ),
        }

    def inspect_artifact_dir(self, rel_path: str) -> dict:
        # Safe enumerator: refuses absolute paths and parent-traversal,
        # pins everything to REPO_ROOT. Returns structured metadata
        # the SDK-GUI viewer renders; returns NO file bytes (.elf /
        # .map / .viz are SDK-owned and excluded from any response).
        if not rel_path:
            return {"ok": False, "error": "missing path parameter"}
        if rel_path.startswith("/") or ".." in Path(rel_path).parts:
            return {
                "ok": False, "error":
                    "path must be repo-relative and must not contain '..'",
            }
        abs_path = (REPO_ROOT / rel_path).resolve()
        try:
            abs_path.relative_to(REPO_ROOT)
        except ValueError:
            return {"ok": False, "error": "path escapes repo root"}
        if not abs_path.is_dir():
            return {
                "ok": False, "error": f"not a directory: {rel_path}",
                "pathChecked": rel_path,
            }
        # SDK compile-artifact shape to surface: colors, elf, lst,
        # map, symbols, viz, plus any nested generated/ directory.
        interesting = {".elf", ".lst", ".map", ".symbols", ".viz"}
        files = []
        colors_info = None
        map_info = None
        for entry in sorted(abs_path.iterdir()):
            if entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "sizeBytes": stat.st_size,
                    "ext": entry.suffix,
                    "kind": "sdk_artifact" if entry.suffix in interesting
                            else "other",
                })
                if entry.name == "colors.json":
                    try:
                        colors_data = json.loads(entry.read_text())
                        if isinstance(colors_data, dict):
                            colors_info = {
                                "numColors": len(colors_data),
                                "colorNames": sorted(colors_data.keys()),
                            }
                        elif isinstance(colors_data, list):
                            colors_info = {
                                "numColors": len(colors_data),
                                "colorNames": [
                                    str(c.get("name") or i) if isinstance(c, dict) else str(c)
                                    for i, c in enumerate(colors_data)
                                ],
                            }
                    except (OSError, ValueError):
                        colors_info = {"error": "colors.json unparseable"}
                if entry.name.endswith(".map"):
                    map_info = {
                        "path": entry.name,
                        "sizeBytes": stat.st_size,
                    }
            elif entry.is_dir():
                # List child dir name only — no recursion.
                files.append({
                    "name": entry.name + "/",
                    "ext": "",
                    "kind": "subdir",
                })
        return {
            "ok": True,
            "pathChecked": rel_path,
            "numFiles": sum(1 for f in files if f.get("kind") != "subdir"),
            "numSdkArtifacts": sum(
                1 for f in files if f.get("kind") == "sdk_artifact"
            ),
            "subdirs": [f["name"] for f in files if f.get("kind") == "subdir"],
            "files": files,
            "colorsJson": colors_info,
            "mapFile": map_info,
            "sdkVisualizeCommand":
                f"sdk_debug_shell visualize --artifact_dir {rel_path}",
            "note": (
                "Metadata only. The server does NOT return .elf / "
                ".lst / .map / .symbols / .viz file contents — those "
                "are SDK-owned binary artifacts. File bytes stay on "
                "the bundler's host."
            ),
        }

    def do_POST(self) -> None:  # noqa: N802
        # /api/run-csl?num_layers=N  where N in ALLOWED_NUM_LAYERS.
        # Existing matching-depth traces are returned by default because the
        # LAN-hosted systemd service may not be permitted to launch the SDK
        # container. Use force=1 to request a fresh simfabric run.
        # Missing/invalid num_layers defaults to DEFAULT_NUM_LAYERS (1)
        # with an explicit echo field so the browser never silently
        # gets a depth it didn't ask for.
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        if parsed.path != "/api/run-csl":
            self.send_error(HTTPStatus.NOT_FOUND, "unknown API route")
            return
        qs = parse_qs(parsed.query or "")
        force = (qs.get("force") or ["0"])[0] in {"1", "true", "yes"}
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
            payload = run_csl(num_layers, force=force)
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
