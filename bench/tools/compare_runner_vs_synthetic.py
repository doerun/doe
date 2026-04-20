#!/usr/bin/env python3
"""Compare the real-runner E2B layer-block trace against the numpy-only
synthetic trace and emit a doe_cross_runtime_parity_check artifact the
parity-contract gate (parallel-safe support track) can consume directly.

Inputs (all optional; missing inputs surface in the verdict):
  --runner-trace        path to e2b-layer-block-smoke-trace.json (cs_python output)
  --synthetic-trace     path to e2b-layer-block-synthetic-trace.json (numpy-only)
  --kernel-source       path to live transformer_layer_shape.csl

Output JSON shape (top-level fields):
  schemaVersion, artifactKind, comparedAt
  kernelSource:        path + live sha256
  runnerTrace:         exists, sha256, kernelSourceSha256InTrace, shaDrift,
                       executionStatus, dataSourceKind, perLayerMaxAbsErr (if present)
  syntheticTrace:      same shape (always synthetic_numpy_only kind)
  verdict:
    promotionEligible: bool — only true when ALL preconditions met
    preconditionsMet:    list[str]
    preconditionsMissing: list[str]
    notes:             str

Promotion preconditions (all required):
  P1. runner trace exists
  P2. runner kernel sha matches live kernel sha (no drift)
  P3. runner dataSource.kind in {synthetic_seeded_rng, manifest_weights_with_seed_fallback,
      manifest_weights_only}  (NOT numpy_only_no_simulator)
  P4. runner executedRun.status == "succeeded"
  P5. runner perLayerMaxAbsErr exists AND all entries == 0  (bit-exact)
  P6. runner executedRun.output.sha256 == synthetic executedRun.output.sha256
      (cross-runtime final-layer output digest equality; redundant with P5
      when both sides use the same compute module, but surfaces the
      byte-equal contract the Doppler/browser external reference will
      later plug into cslRun.output vs referenceRun.output)

The synthetic trace is informational only — a successful synthetic_numpy_only
trace doesn't satisfy P3, so it cannot promote on its own. But its
kernelSourceSha256InTrace IS validated against the live kernel for drift,
to flag stale synthetic fixtures.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def rel_repo(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--runner-trace",
        default="bench/out/streaming-executor/e2b-layer-block-smoke-trace.json",
    )
    p.add_argument(
        "--synthetic-trace",
        default="bench/out/streaming-executor/e2b-layer-block-synthetic-trace.json",
    )
    p.add_argument(
        "--kernel-source",
        default=(
            "bench/out/streaming-executor/e2b-layer-block-source/"
            "transformer_layer_shape.csl"
        ),
    )
    p.add_argument(
        "--out",
        default=(
            "bench/out/streaming-executor/"
            "e2b-layer-block-cross-runtime-parity-check.json"
        ),
    )
    return p.parse_args()


def summarize_trace(
    path: Path, live_kernel_sha: str
) -> dict[str, Any]:
    """Read a trace + extract the fields the parity check cares about."""
    summary: dict[str, Any] = {
        "path": rel_repo(path),
        "exists": path.is_file(),
    }
    if not summary["exists"]:
        summary["readStatus"] = "file_missing"
        return summary
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        summary["readStatus"] = "json_parse_failed"
        summary["readError"] = str(e)[:160]
        return summary
    summary["sha256"] = sha256_file(path)
    summary["readStatus"] = "ok"

    lbs = trace.get("layerBlockSmoke", {}) or {}
    er = trace.get("executedRun", {}) or {}
    np_block = er.get("numericalParity", {}) or {}
    ds = er.get("dataSource", {}) or {}

    trace_sha = lbs.get("kernelSourceSha256")
    summary["kernelSourceSha256InTrace"] = trace_sha
    summary["shaDrift"] = bool(trace_sha and trace_sha != live_kernel_sha)
    summary["executionStatus"] = er.get("status")
    summary["dataSourceKind"] = ds.get("kind")
    summary["numLayersChained"] = er.get("numLayersChained")

    per_err = np_block.get("perLayerMaxAbsErr")
    summary["perLayerMaxAbsErr"] = per_err
    summary["overallMaxAbsErr"] = np_block.get("maxAbsErr")
    summary["passedReported"] = np_block.get("passed")
    if per_err:
        summary["allPerLayerErrZero"] = all(e == 0 for e in per_err)
    else:
        summary["allPerLayerErrZero"] = None

    output = er.get("output") or {}
    summary["outputSha256"] = output.get("sha256")
    summary["outputPath"] = output.get("path")
    summary["outputShape"] = output.get("shape")
    return summary


def main() -> int:
    args = parse_args()
    runner_path = resolve(args.runner_trace)
    synthetic_path = resolve(args.synthetic_trace)
    kernel_path = resolve(args.kernel_source)
    out_path = resolve(args.out)

    if not kernel_path.is_file():
        print(f"ERROR: kernel source missing at {kernel_path}", file=sys.stderr)
        return 2
    live_kernel_sha = sha256_file(kernel_path)

    runner_summary = summarize_trace(runner_path, live_kernel_sha)
    synthetic_summary = summarize_trace(synthetic_path, live_kernel_sha)

    # Promotion verdict (see file docstring).
    met: list[str] = []
    missing: list[str] = []

    if runner_summary.get("readStatus") == "ok":
        met.append("P1_runner_trace_exists")
    else:
        missing.append("P1_runner_trace_exists")

    if (runner_summary.get("readStatus") == "ok"
            and not runner_summary.get("shaDrift", True)):
        met.append("P2_runner_kernel_sha_matches_live")
    else:
        missing.append("P2_runner_kernel_sha_matches_live")

    real_kinds = {
        "synthetic_seeded_rng",
        "manifest_weights_with_seed_fallback",
        "manifest_weights_only",
    }
    rds_kind = runner_summary.get("dataSourceKind")
    if rds_kind in real_kinds:
        met.append("P3_runner_ran_on_simulator_not_numpy")
    else:
        missing.append("P3_runner_ran_on_simulator_not_numpy")

    if runner_summary.get("executionStatus") == "succeeded":
        met.append("P4_runner_status_succeeded")
    else:
        missing.append("P4_runner_status_succeeded")

    if runner_summary.get("allPerLayerErrZero") is True:
        met.append("P5_per_layer_err_all_zero_bit_exact")
    else:
        missing.append("P5_per_layer_err_all_zero_bit_exact")

    runner_out_sha = runner_summary.get("outputSha256")
    synthetic_out_sha = synthetic_summary.get("outputSha256")
    if (runner_out_sha
            and synthetic_out_sha
            and runner_out_sha == synthetic_out_sha):
        met.append("P6_output_digests_match_across_runtimes")
    else:
        missing.append("P6_output_digests_match_across_runtimes")

    promotion_eligible = len(missing) == 0

    verdict_notes: list[str] = []
    if not runner_summary.get("readStatus") == "ok":
        verdict_notes.append(
            "Runner trace not readable. Run "
            "`python3 bench/runners/csl-runners/e2b_layer_block_smoke.py` "
            "(requires cs_python on PATH) to produce it."
        )
    elif runner_summary.get("shaDrift"):
        verdict_notes.append(
            "Runner trace's kernelSourceSha256 ({trace}) differs "
            "from the live kernel ({live}) — runner trace is stale, "
            "regenerate via the runner.".format(
                trace=(runner_summary.get("kernelSourceSha256InTrace") or "")[:16],
                live=live_kernel_sha[:16],
            )
        )
    elif rds_kind == "numpy_only_no_simulator":
        verdict_notes.append(
            "Runner trace dataSource.kind = numpy_only_no_simulator — "
            "this is a synthetic trace, not real-simulator output; "
            "cannot satisfy promotion preconditions on its own."
        )
    elif rds_kind is None:
        verdict_notes.append(
            "Runner trace lacks executedRun.dataSource.kind — likely "
            "from before the per-layer seed scheme landed. Regenerate "
            "via the current runner."
        )
    if synthetic_summary.get("readStatus") == "ok" and synthetic_summary.get("shaDrift"):
        verdict_notes.append(
            "Synthetic trace kernel sha drifted from live kernel; "
            "regenerate via "
            "`python3 bench/tools/emit_e2b_layer_block_synthetic_trace.py`."
        )
    if runner_out_sha is None:
        verdict_notes.append(
            "Runner trace has no executedRun.output.sha256 — the output "
            "digest was added after the current smoke trace was written. "
            "Regenerate via the runner so P6 can verify cross-runtime "
            "output equality."
        )
    elif synthetic_out_sha is None:
        verdict_notes.append(
            "Synthetic trace has no executedRun.output.sha256 — "
            "regenerate via "
            "`python3 bench/tools/emit_e2b_layer_block_synthetic_trace.py`."
        )
    elif runner_out_sha != synthetic_out_sha:
        verdict_notes.append(
            "Runner and synthetic output.sha256 differ ({runner} vs "
            "{synthetic}) — the CSL simulator's final activation_out "
            "bytes do not match the numpy reference bytes. This is the "
            "cross-runtime parity failure the gate guards against."
            .format(
                runner=(runner_out_sha or "")[:16],
                synthetic=(synthetic_out_sha or "")[:16],
            )
        )

    out = {
        "schemaVersion": 1,
        "artifactKind": "doe_cross_runtime_parity_check",
        "comparedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kernelSource": {
            "path": rel_repo(kernel_path),
            "liveSha256": live_kernel_sha,
        },
        "runnerTrace": runner_summary,
        "syntheticTrace": synthetic_summary,
        "verdict": {
            "promotionEligible": promotion_eligible,
            "preconditionsMet": met,
            "preconditionsMissing": missing,
            "notes": verdict_notes,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        "wrote " + rel_repo(out_path)
        + f"  promotionEligible={promotion_eligible}"
        + f"  met={len(met)}/6  missing={missing}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
