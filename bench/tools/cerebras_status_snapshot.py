#!/usr/bin/env python3
"""Reflect Cerebras lane state from artifacts into a single snapshot.

Reads a fixed list of receipt paths and the latest Phase-7 progress event,
emits two artifacts under bench/out/r3-cerebras-status/:
  snapshot.json  - structured rows
  snapshot.md    - human-readable table

Status docs and memory entries should reference this output instead of
restating verdicts. Drift is impossible because nothing else holds state.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

CROSS_MODEL_PARITY = "bench/out/r3-cross-model-parity/receipt.json"
GEMMA_PER_KERNEL_DIR = "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel"
QWEN_PER_KERNEL_DIR = "bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel"
GEMMA_BOUNDED_SMOKE = "bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json"
GEMMA_LOCAL_SIMFABRIC_CEILING = (
    "bench/out/r3-1-31b-af16-local-simfabric-ceiling/receipt.json"
)
GEMMA_SPLICE_SINGLE_BLOCK_HIDDEN = (
    "bench/out/r3-1-31b-af16-doppler-csl-splice/single-block-hidden.json"
)
GEMMA_SPLICE_SINGLE_BLOCK_HIDDEN_RUN = (
    "bench/out/r3-1-31b-af16-doppler-csl-splice/single_block_hidden-run.json"
)
GEMMA_SPLICE_LAST_LAYER_TAIL_TOKEN = (
    "bench/out/r3-1-31b-af16-doppler-csl-splice/last-layer-tail-token.json"
)
GEMMA_SELECTED_LOGIT_SPLICE = (
    "bench/out/r3-1-31b-af16-doppler-csl-splice/"
    "selected-logit-splice/selected-logit-splice.json"
)
QWEN_SELECTED_LOGIT_SPLICE = (
    "bench/out/r3-2-27b-af16-doppler-csl-splice/"
    "selected-logit-splice/selected-logit-splice.json"
)
QWEN_HARDWARE_TRACE = "bench/out/hardware-run/qwen3-6-27b-af16-trace.json"
QWEN_LOCAL_SIMFABRIC_CEILING = (
    "bench/out/r3-2-27b-af16-local-simfabric-ceiling/receipt.json"
)
QWEN_MULTI_TOKEN_DECODE = "bench/out/r3-2-27b-qwen-multi-token-decode/receipt.json"
GEMMA_SIMFABRIC_CELLS = (
    "bench/out/r3-1-31b-gemma-af16-simfabric-cells/summary-receipt.json"
)
QWEN_SIMFABRIC_CELLS = "bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json"
GEMMA_PHASE7_SESSION_DIR = (
    "bench/out/r3-1-31b-af16-hostplan-session-bos-raw-sky-color-is-fast-embed512"
)
GEMMA_PHASE7_TRACE = (
    "bench/out/r3-1-31b-af16-hostplan-streaming/"
    "trace-bos-raw-sky-color-is-fast-embed512-exec.json"
)

OUT_DIR = "bench/out/r3-cerebras-status"


def _load_json(rel_path: str) -> dict | None:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"_parse_error": True}


def _mtime_iso(rel_path: str) -> str | None:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()


def _row(
    lane: str,
    artifact: str,
    verdict: str,
    blocker: str | None,
    *,
    scope: str | None = None,
) -> dict:
    return {
        "lane": lane,
        "artifact": artifact,
        "verdict": verdict,
        "blocker": blocker,
        "scope": scope or "",
        "artifactMtime": _mtime_iso(artifact),
    }


def _verdict_from_status(status: str | None, blockers: list | None) -> tuple[str, str | None]:
    if status is None:
        return "unknown", "status_field_missing"
    if status == "blocked" or (blockers and len(blockers) > 0):
        first = blockers[0] if blockers else None
        if isinstance(first, dict):
            return "blocked", first.get("class") or first.get("detail")
        if isinstance(first, str):
            return "blocked", first
        return "blocked", None
    if status in ("output_ready", "bound", "succeeded", "ok", "pass"):
        return "bound", None
    return status, None


def cross_model_parity_row() -> dict:
    d = _load_json(CROSS_MODEL_PARITY)
    if d is None:
        return _row("compile.cross_model_parity", CROSS_MODEL_PARITY, "missing", None)
    verdict = d.get("verdict") or "unknown"
    issues = d.get("issues") or []
    blocker = None
    if issues:
        first = issues[0]
        blocker = first.get("class") if isinstance(first, dict) else str(first)
    required_lanes = d.get("requiredLanes") or []
    scope = ""
    if isinstance(required_lanes, list) and required_lanes:
        scope = "requiredLanes=" + ",".join(str(lane) for lane in required_lanes)
    return _row(
        "compile.cross_model_parity",
        CROSS_MODEL_PARITY,
        verdict,
        blocker,
        scope=scope,
    )


def per_kernel_rows(model: str, dir_rel: str) -> list[dict]:
    rows = []
    summary_rel = f"{dir_rel}/summary.json"
    summary = _load_json(summary_rel)
    if summary is None:
        rows.append(_row(f"{model}.per_kernel.summary", summary_rel, "missing", None))
    else:
        kernels = summary.get("kernels") or []
        bound = sum(1 for k in kernels if k.get("verdict") == "bound")
        blocked = [k.get("name") or k.get("kernel") for k in kernels if k.get("verdict") != "bound"]
        verdict = "bound" if kernels and not blocked else "blocked"
        blocker = (
            None if not blocked
            else f"{len(blocked)}/{len(kernels)} kernels not bound: {','.join(b for b in blocked if b)[:120]}"
        )
        rows.append(_row(f"{model}.per_kernel.summary", summary_rel, verdict, blocker))

    dir_p = REPO_ROOT / dir_rel
    if dir_p.exists():
        for receipt_p in sorted(dir_p.glob("*.json")):
            if receipt_p.name == "summary.json":
                continue
            rel = receipt_p.relative_to(REPO_ROOT).as_posix()
            d = _load_json(rel)
            if d is None:
                continue
            verdict = d.get("verdict") or "unknown"
            blocker = d.get("blocker")
            if d.get("dispatchTimedOut"):
                blocker = (blocker or "") + " [dispatchTimedOut]"
            rows.append(_row(f"{model}.per_kernel.{receipt_p.stem}", rel, verdict, blocker))
    return rows


def bounded_smoke_row() -> dict:
    d = _load_json(GEMMA_BOUNDED_SMOKE)
    if d is None:
        return _row("gemma.bounded_smoke", GEMMA_BOUNDED_SMOKE, "missing", None)
    verdict, blocker = _verdict_from_status(d.get("status"), d.get("blockers"))
    n = len(d.get("blockers") or [])
    if verdict == "blocked" and n > 1:
        blocker = f"{blocker} (+{n - 1} more)"
    return _row("gemma.bounded_smoke", GEMMA_BOUNDED_SMOKE, verdict, blocker)


def gemma_local_simfabric_ceiling_row() -> dict:
    d = _load_json(GEMMA_LOCAL_SIMFABRIC_CEILING)
    if d is None:
        return _row(
            "gemma.local_simfabric_ceiling",
            GEMMA_LOCAL_SIMFABRIC_CEILING,
            "missing",
            None,
        )
    return _row(
        "gemma.local_simfabric_ceiling",
        GEMMA_LOCAL_SIMFABRIC_CEILING,
        d.get("verdict") or "unknown",
        d.get("blocker"),
        scope=d.get("lastPhaseReached") or "",
    )


def gemma_splice_row(lane: str, artifact: str, run_artifact: str | None = None) -> dict:
    d = _load_json(artifact)
    if d is None:
        return _row(lane, artifact, "missing", None)
    run = _load_json(run_artifact) if run_artifact else None
    splice = d.get("splicePoint") or {}
    scope_parts = []
    if splice.get("kind"):
        scope_parts.append(str(splice.get("kind")))
    if splice.get("layerIndex") is not None:
        scope_parts.append(f"layer={splice.get('layerIndex')}")
    if splice.get("promptTokenCount") is not None:
        scope_parts.append(f"promptTokens={splice.get('promptTokenCount')}")
    blocker = d.get("blocker")
    if isinstance(run, dict) and run.get("blocker"):
        blocker = run.get("blocker")
        if run.get("prefillTokenCount") is not None:
            scope_parts.append(f"handoffPromptTokens={run.get('prefillTokenCount')}")
    return _row(
        lane,
        run_artifact if run_artifact and run is not None else artifact,
        (run.get("status") or "unknown")
        if isinstance(run, dict)
        else (d.get("verdict") or "unknown"),
        blocker,
        scope=", ".join(scope_parts),
    )


def selected_logit_splice_row(lane: str, artifact: str) -> dict:
    d = _load_json(artifact)
    if d is None:
        return _row(lane, artifact, "missing", None)
    splice = d.get("splicePoint") or {}
    csl_run = d.get("cslRun") or {}
    blockers = d.get("blockers") or []
    verdict = "bound" if d.get("verdict") == "pass" else d.get("verdict") or "unknown"
    blocker = blockers[0] if blockers else None
    scope_parts = []
    if splice.get("kind"):
        scope_parts.append(str(splice.get("kind")))
    if splice.get("layerIndex") is not None:
        scope_parts.append(f"layer={splice.get('layerIndex')}")
    if splice.get("promptTokenCount") is not None:
        scope_parts.append(f"promptTokens={splice.get('promptTokenCount')}")
    if splice.get("selectedTokenId") is not None:
        scope_parts.append(f"token={splice.get('selectedTokenId')}")
    if csl_run.get("logitAbsDiff") is not None:
        scope_parts.append(f"logitAbsDiff={csl_run.get('logitAbsDiff'):.6g}")
    return _row(
        lane,
        artifact,
        verdict,
        blocker,
        scope=", ".join(scope_parts),
    )


def gemma_selected_logit_splice_row() -> dict:
    return selected_logit_splice_row(
        "gemma.doppler_csl_splice.selected_logit",
        GEMMA_SELECTED_LOGIT_SPLICE,
    )


def qwen_selected_logit_splice_row() -> dict:
    return selected_logit_splice_row(
        "qwen.doppler_csl_splice.selected_logit",
        QWEN_SELECTED_LOGIT_SPLICE,
    )


def qwen_multi_token_decode_row() -> dict:
    d = _load_json(QWEN_MULTI_TOKEN_DECODE)
    if d is None:
        return _row("qwen.multi_token_decode", QWEN_MULTI_TOKEN_DECODE, "missing", None)
    bound = d.get("boundKernelCount")
    total = len(d.get("kernelCompileDirs") or [])
    if bound is None:
        return _row("qwen.multi_token_decode", QWEN_MULTI_TOKEN_DECODE, "unknown", None)
    if total and bound == total:
        return _row("qwen.multi_token_decode", QWEN_MULTI_TOKEN_DECODE, "bound", None)
    return _row(
        "qwen.multi_token_decode",
        QWEN_MULTI_TOKEN_DECODE,
        "blocked",
        f"boundKernelCount={bound}/{total}" if total else f"boundKernelCount={bound}",
    )


def qwen_hardware_path_row() -> dict:
    d = _load_json(QWEN_HARDWARE_TRACE)
    if d is None:
        return _row(
            "qwen.hardware_full_prompt",
            QWEN_HARDWARE_TRACE,
            "missing",
            "returned hardware trace absent",
            scope="runner=bench/tools/run_qwen3_6_27b_af16_hardware_path.sh",
        )
    verdict, blocker = _verdict_from_status(d.get("status"), d.get("blockers"))
    return _row(
        "qwen.hardware_full_prompt",
        QWEN_HARDWARE_TRACE,
        verdict,
        blocker,
        scope="runner=bench/tools/run_qwen3_6_27b_af16_hardware_path.sh",
    )


def qwen_local_simfabric_ceiling_row() -> dict:
    d = _load_json(QWEN_LOCAL_SIMFABRIC_CEILING)
    if d is None:
        return _row(
            "qwen.local_simfabric_ceiling",
            QWEN_LOCAL_SIMFABRIC_CEILING,
            "missing",
            None,
        )
    return _row(
        "qwen.local_simfabric_ceiling",
        QWEN_LOCAL_SIMFABRIC_CEILING,
        d.get("verdict") or "unknown",
        d.get("blocker"),
        scope=d.get("lastPhaseReached") or "",
    )


def gemma_simfabric_cells_row() -> dict:
    d = _load_json(GEMMA_SIMFABRIC_CELLS)
    if d is None:
        return _row("gemma.simfabric_cells", GEMMA_SIMFABRIC_CELLS, "missing", None)
    verdict = d.get("verdict") or d.get("status") or "unknown"
    return _row(
        "gemma.simfabric_cells",
        GEMMA_SIMFABRIC_CELLS,
        verdict,
        d.get("blocker"),
    )


def qwen_simfabric_cells_row() -> dict:
    d = _load_json(QWEN_SIMFABRIC_CELLS)
    if d is None:
        return _row("qwen.simfabric_cells", QWEN_SIMFABRIC_CELLS, "missing", None)
    verdict = d.get("verdict") or d.get("status") or "unknown"
    return _row("qwen.simfabric_cells", QWEN_SIMFABRIC_CELLS, verdict, d.get("blocker"))


def phase7_row() -> dict:
    progress_rel = f"{GEMMA_PHASE7_SESSION_DIR}/progress.jsonl"
    progress_p = REPO_ROOT / progress_rel
    if not progress_p.exists():
        return _row("gemma.phase7_session", progress_rel, "missing", None)
    last_complete = None
    last_blocked = None
    last_event = None
    with progress_p.open() as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            last_event = ev
            phase = ev.get("phase")
            if phase == "hostplan_launch_complete":
                last_complete = ev
            elif phase == "hostplan_launch_blocked":
                last_blocked = ev
    if last_complete is None and last_blocked is None:
        return _row("gemma.phase7_session", progress_rel, "no_launches", None)
    completed_idx = last_complete.get("launchIndex") if last_complete else None
    last_phase = last_event.get("phase") if last_event else None
    last_target = last_event.get("target") if last_event else None
    detail_parts = []
    if completed_idx is not None:
        detail_parts.append(f"lastCompleteLaunch={completed_idx}")
    if last_phase:
        detail_parts.append(f"lastEvent={last_phase}")
    if last_target:
        detail_parts.append(f"target={last_target}")
    if last_blocked and (
        last_complete is None
        or last_blocked.get("launchIndex", -1) > last_complete.get("launchIndex", -1)
    ):
        verdict = "blocked"
        blocker = (
            f"launch[{last_blocked.get('launchIndex')}]:"
            f"{last_blocked.get('error', 'unknown')}"
        )
    else:
        verdict = "in_progress"
        blocker = "; ".join(detail_parts) or None
    return _row("gemma.phase7_session", progress_rel, verdict, blocker)


def phase7_trace_row() -> dict:
    d = _load_json(GEMMA_PHASE7_TRACE)
    if d is None:
        return _row("gemma.phase7_trace_synth", GEMMA_PHASE7_TRACE, "missing", None)
    verdict, blocker = _verdict_from_status(d.get("status"), d.get("blockers"))
    return _row("gemma.phase7_trace_synth", GEMMA_PHASE7_TRACE, verdict, blocker)


def collect_rows() -> list[dict]:
    rows: list[dict] = []
    rows.append(cross_model_parity_row())
    rows.extend(per_kernel_rows("gemma", GEMMA_PER_KERNEL_DIR))
    rows.extend(per_kernel_rows("qwen", QWEN_PER_KERNEL_DIR))
    rows.append(bounded_smoke_row())
    rows.append(gemma_local_simfabric_ceiling_row())
    rows.append(gemma_splice_row(
        "gemma.doppler_csl_splice.single_block_hidden",
        GEMMA_SPLICE_SINGLE_BLOCK_HIDDEN,
        GEMMA_SPLICE_SINGLE_BLOCK_HIDDEN_RUN,
    ))
    rows.append(gemma_splice_row(
        "gemma.doppler_csl_splice.last_layer_tail_token",
        GEMMA_SPLICE_LAST_LAYER_TAIL_TOKEN,
    ))
    rows.append(gemma_selected_logit_splice_row())
    rows.append(qwen_selected_logit_splice_row())
    rows.append(qwen_hardware_path_row())
    rows.append(qwen_local_simfabric_ceiling_row())
    rows.append(qwen_multi_token_decode_row())
    rows.append(gemma_simfabric_cells_row())
    rows.append(qwen_simfabric_cells_row())
    rows.append(phase7_row())
    rows.append(phase7_trace_row())
    return rows


def render_markdown(rows: list[dict], generated_at: str) -> str:
    lines = [
        "# Cerebras lane snapshot",
        "",
        "This file is **generated** by `bench/tools/cerebras_status_snapshot.py`.",
        "Do not edit by hand. Re-run the tool to refresh.",
        "",
        f"Generated: `{generated_at}`",
        "",
        "| Lane | Verdict | Scope | Blocker | Artifact mtime | Artifact |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        verdict = r["verdict"] or "unknown"
        marker = {
            "bound": "✅",
            "blocked": "❌",
            "in_progress": "\U0001F504",
            "missing": "❓",
        }.get(verdict, "⚠️")
        blocker = r["blocker"] or ""
        if len(blocker) > 90:
            blocker = blocker[:87] + "..."
        scope = r.get("scope") or ""
        if len(scope) > 90:
            scope = scope[:87] + "..."
        lines.append(
            f"| `{r['lane']}` | {marker} {verdict} | {scope} | {blocker} | "
            f"{r['artifactMtime'] or 'n/a'} | `{r['artifact']}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=OUT_DIR)
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print markdown to stdout.",
    )
    args = parser.parse_args(argv)

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    rows = collect_rows()
    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_json = {
        "generatedAt": generated_at,
        "tool": "bench/tools/cerebras_status_snapshot.py",
        "rows": rows,
    }
    (out_dir / "snapshot.json").write_text(json.dumps(snapshot_json, indent=2) + "\n")
    md = render_markdown(rows, generated_at)
    (out_dir / "snapshot.md").write_text(md)
    if args.print:
        sys.stdout.write(md)
    sys.stderr.write(
        f"wrote {args.out_dir}/snapshot.json and snapshot.md "
        f"({len(rows)} rows)\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
