#!/usr/bin/env python3
"""Emit the Gemma 4 31B af16 bounded inference smoke receipt.

This is the governed entry point for the first Gemma 4 31B af16 Doe
simulator smoke: a caller-selected prefill token budget plus a fixed greedy
decode budget, bound to the af16 Doppler manifest, the frozen Doppler
reference fixture, the af16 HostPlan compile receipt, and the current
manifest-shape per-kernel evidence.

The receipt is intentionally conservative. It does not invent a simulator
token sequence. It records the state needed by the session-scoped HostPlan
runner and emits named blockers until a real SDK run produces the CSL-side
token/logit/KV transcript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._lane_dtype_profile import (  # noqa: E402
    LaneDtypeProfileError,
    assert_lane_match,
    canonical_dtype_profile,
    csl_dtype_contract_for_profile,
)
from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)
from bench.tools._inference_evidence_gate import (  # noqa: E402
    InferenceEvidenceGateError,
    enforce_inference_evidence_gate,
    evaluate_inference_evidence_gate,
)

MODEL_ID = "gemma-4-31b-it-text-q4k-ehf16-af16"
LANE_KEY = "q4k-ehf16-af16"
ARTIFACT_KIND = "doe_gemma4_31b_af16_bounded_inference_smoke_receipt"
DEFAULT_SOURCE_MANIFEST = (
    WORKSPACE_ROOT
    / "doppler/models/local/gemma-4-31b-it-text-q4k-ehf16-af16/manifest.json"
)
DEFAULT_REFERENCE_ROOT = (
    REPO_ROOT / "bench/fixtures/r3-1-31b-doppler-frozen-af16"
)
DEFAULT_COMPILE_RECEIPT = (
    REPO_ROOT / "bench/out/r3-1-31b-af16-full-graph-compile-attempt/receipt.json"
)
DEFAULT_HOST_PLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/host-plan.json"
)
DEFAULT_SOURCE_GRAPH_INVENTORY = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/"
    "source-graph-inventory.json"
)
DEFAULT_PER_KERNEL_SUMMARY = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/summary.json"
)
DEFAULT_STREAMING_TRACE = (
    REPO_ROOT / "bench/out/r3-1-31b-af16-hostplan-streaming/trace.json"
)
DEFAULT_STREAMING_RUNNER = (
    REPO_ROOT
    / "bench/runners/csl-runners/"
    "gemma4_31b_af16_hostplan_streaming_runner.py"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "config/doe-gemma4-31b-af16-bounded-inference-smoke.schema.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-doppler-manifest",
        type=Path,
        default=DEFAULT_SOURCE_MANIFEST,
    )
    parser.add_argument(
        "--frozen-reference-root",
        type=Path,
        default=DEFAULT_REFERENCE_ROOT,
    )
    parser.add_argument(
        "--compile-receipt",
        type=Path,
        default=DEFAULT_COMPILE_RECEIPT,
    )
    parser.add_argument("--host-plan", type=Path, default=DEFAULT_HOST_PLAN)
    parser.add_argument(
        "--source-graph-inventory",
        type=Path,
        default=DEFAULT_SOURCE_GRAPH_INVENTORY,
    )
    parser.add_argument(
        "--per-kernel-summary",
        type=Path,
        default=DEFAULT_PER_KERNEL_SUMMARY,
    )
    parser.add_argument(
        "--streaming-trace",
        type=Path,
        default=DEFAULT_STREAMING_TRACE,
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--prefill-token-count", type=int, default=2)
    parser.add_argument("--decode-token-count", type=int, default=2)
    parser.add_argument(
        "--emit-blocked-on-evidence-gate",
        action="store_true",
        help=(
            "Emit a blocked receipt carrying inferenceEvidenceGate reasons "
            "when token-output dispatch evidence is incomplete."
        ),
    )
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _display_path(path: Path) -> str:
    resolved = _resolve(path)
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return "../" + resolved.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _load_json(path: Path) -> Any:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with _resolve(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_file(path: Path, label: str) -> None:
    if not _resolve(path).is_file():
        raise FileNotFoundError(f"{label} not found: {_display_path(path)}")


def _load_dtype_profile(source_manifest_path: Path) -> dict[str, str]:
    manifest = _load_json(source_manifest_path)
    profile = canonical_dtype_profile(manifest.get("quantizationInfo"))
    if profile.get("variantTag") != LANE_KEY:
        raise LaneDtypeProfileError(
            f"expected lane {LANE_KEY!r}, got {profile.get('variantTag')!r}"
        )
    if profile.get("compute") != "f16":
        raise LaneDtypeProfileError(
            f"expected f16 compute, got {profile.get('compute')!r}"
        )
    return profile


def _reference_summary(
    reference_root: Path,
    *,
    requested_prefill: int,
    requested_decode: int,
) -> dict[str, Any]:
    root = _resolve(reference_root)
    manifest_path = root / "frozen-reference.manifest.json"
    _require_file(manifest_path, "frozen reference manifest")
    manifest = _load_json(manifest_path)
    assert_lane_match(
        LANE_KEY,
        manifest.get("dtypeProfile"),
        permissive_when_absent=False,
    )
    if manifest.get("modelId") != MODEL_ID:
        raise ValueError(
            f"expected reference modelId {MODEL_ID!r}, "
            f"got {manifest.get('modelId')!r}"
        )
    transcript_rel = manifest.get("transcript", {}).get("path")
    if not isinstance(transcript_rel, str):
        raise ValueError("reference manifest transcript.path is missing")
    transcript_path = root / transcript_rel
    _require_file(transcript_path, "reference transcript")
    transcript = _load_json(transcript_path)
    metrics = transcript.get("metrics") or {}
    reference = metrics.get("referenceTranscript") or {}
    prompt = reference.get("prompt") or {}
    output = reference.get("output") or {}
    tokens = reference.get("tokens") or {}
    logits = reference.get("logits") or {}
    phase = reference.get("phase") or {}
    prompt_token_count = int(
        prompt.get("tokenCount") or phase.get("prefillTokens") or 0
    )
    generated_count = int(
        output.get("tokensGenerated") or phase.get("decodeTokens") or 0
    )
    exact_shape = (
        prompt_token_count == requested_prefill
        and generated_count == requested_decode
    )
    token_ids = tokens.get("ids") or []
    return {
        "fixtureRoot": _display_path(root),
        "manifestPath": _display_path(manifest_path),
        "manifestSha256": _sha256_file(manifest_path),
        "transcriptPath": _display_path(transcript_path),
        "transcriptSha256": _sha256_file(transcript_path),
        "fixtureDigest": str(manifest.get("fixtureDigest")),
        "prompt": {
            "identity": prompt.get("identity"),
            "hash": prompt.get("hash"),
            "tokenIdsHash": prompt.get("tokenIdsHash"),
            "tokenCount": prompt_token_count,
        },
        "output": {
            "tokensGenerated": generated_count,
            "tokenIds": token_ids,
            "generatedTokenIdsHash": tokens.get("generatedTokenIdsHash"),
            "generatedTextHash": output.get("textHash"),
            "stopReason": output.get("stopReason"),
            "stopTokenId": output.get("stopTokenId"),
            "perStepLogitsDigests": logits.get("perStepDigests") or [],
        },
        "exactShapeMatchesRequested": exact_shape,
    }


def _host_plan_summary(host_plan_path: Path) -> dict[str, Any]:
    host_plan = _load_json(host_plan_path)
    plan = host_plan.get("hostPlan") or {}
    phases = plan.get("phases") or {}
    kernels = plan.get("kernels") or []
    return {
        "path": _display_path(host_plan_path),
        "sha256": _sha256_file(host_plan_path),
        "peGrid": plan.get("peGrid") or {},
        "kernelNames": [k.get("name") for k in kernels if k.get("name")],
        "phaseKernelCounts": {
            phase: len(steps)
            for phase, steps in phases.items()
            if isinstance(steps, list)
        },
    }


def _compile_summary(compile_receipt_path: Path) -> dict[str, Any]:
    receipt = _load_json(compile_receipt_path)
    return {
        "path": _display_path(compile_receipt_path),
        "sha256": _sha256_file(compile_receipt_path),
        "compileTargetCount": int(receipt.get("compileTargetCount") or 0),
        "compileSucceededCount": int(
            receipt.get("compileSucceededCount") or 0
        ),
        "blockerClass": (receipt.get("blocker") or {}).get("class"),
    }


def _per_kernel_summary(summary_path: Path) -> dict[str, Any]:
    summary = _load_json(summary_path)
    kernels = summary.get("kernels") or []
    verdicts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    blocked: list[str] = []
    for kernel in kernels:
        verdict = str(kernel.get("verdict") or "unknown")
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        if verdict != "bound":
            name = kernel.get("kernel")
            if isinstance(name, str):
                blocked.append(name)
            blocker = str(kernel.get("blocker") or "unknown")
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    return {
        "summaryPath": _display_path(summary_path),
        "summarySha256": _sha256_file(summary_path),
        "totals": summary.get("totals") or {},
        "verdictCounts": verdicts,
        "blockerCounts": blocker_counts,
        "staleDryRunOnly": bool(blocked)
        and set(blocker_counts) == {"dry_run"},
        "blockedKernels": blocked,
    }


def _source_graph_inventory(
    source_graph_inventory_path: Path,
) -> dict[str, Any]:
    path = _resolve(source_graph_inventory_path)
    if not path.is_file():
        return {
            "path": _display_path(source_graph_inventory_path),
            "present": False,
            "requiredKernels": None,
        }
    payload = _load_json(path)
    kernels = payload.get("requiredKernels")
    required_kernels = (
        [str(item) for item in kernels if str(item)]
        if isinstance(kernels, list)
        else None
    )
    return {
        "path": _display_path(path),
        "sha256": _sha256_file(path),
        "present": True,
        "artifactKind": payload.get("artifactKind"),
        "source": payload.get("source"),
        "sourceGraphSha256": payload.get("sourceGraphSha256"),
        "requiredKernels": required_kernels,
        "prefillTail": payload.get("prefillTail") or [],
        "decodeTail": payload.get("decodeTail") or [],
    }


def _streaming_trace_summary(streaming_trace_path: Path) -> dict[str, Any]:
    path = _resolve(streaming_trace_path)
    if not path.is_file():
        return {
            "path": _display_path(streaming_trace_path),
            "present": False,
            "blockers": [{
                "class": "hostplan_streaming_trace_absent",
                "detail": (
                    "Run the Gemma 4 31B af16 HostPlan streaming runner "
                    "to emit the source-side staging and refresh trace."
                ),
            }],
        }
    trace = _load_json(streaming_trace_path)
    return {
        "path": _display_path(streaming_trace_path),
        "sha256": _sha256_file(streaming_trace_path),
        "present": True,
        "status": trace.get("status"),
        "weightStaging": trace.get("weightStaging") or {},
        "perKernelRefresh": trace.get("perKernelRefresh") or {},
        "realSessionRuntime": trace.get("realSessionRuntime") or {},
        "blockers": trace.get("blockers") or [],
    }


def _blockers(
    *,
    reference: dict[str, Any],
    compile_summary: dict[str, Any],
    kernel_summary: dict[str, Any],
    streaming_trace: dict[str, Any],
    inference_gate: dict[str, Any],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    blocker_classes: set[str] = set()
    if (
        compile_summary["compileTargetCount"]
        != compile_summary["compileSucceededCount"]
    ):
        blocker = {
            "class": "manifest_shape_compile_not_clean",
            "detail": (
                "The af16 HostPlan compile receipt does not report every "
                "target as compiled successfully."
            ),
        }
        blockers.append(blocker)
        blocker_classes.add(blocker["class"])
    if inference_gate.get("eligible") is not True:
        for reason in inference_gate.get("reasons") or []:
            if not isinstance(reason, dict):
                continue
            code = str(reason.get("code") or "")
            if not code:
                continue
            cls = f"inference_evidence_gate.{code}"
            if cls in blocker_classes:
                continue
            blockers.append({
                "class": cls,
                "detail": str(reason.get("detail") or code),
            })
            blocker_classes.add(cls)
    trace_blocker_classes = {
        str(blocker.get("class"))
        for blocker in streaming_trace.get("blockers") or []
        if isinstance(blocker, dict)
    }
    refresh = streaming_trace.get("perKernelRefresh") or {}
    refresh_blocked = refresh.get("status") == "blocked"
    stale_dry_run_only = bool(kernel_summary.get("staleDryRunOnly"))
    if kernel_summary["blockedKernels"] and not (
        refresh_blocked and stale_dry_run_only
    ):
        blocker = {
            "class": "manifest_kernel_dispatch_not_bound",
            "detail": (
                "The af16 per-kernel summary still contains non-bound "
                "kernel verdicts. Re-run the manifest-shape per-kernel "
                "suite on an SDK host and refresh the summary before "
                "using it as execution evidence."
            ),
        }
        if blocker["class"] not in blocker_classes:
            blockers.append(blocker)
            blocker_classes.add(blocker["class"])
    for blocker in streaming_trace.get("blockers") or []:
        if not isinstance(blocker, dict):
            continue
        cls = str(blocker.get("class") or "")
        if (
            not cls
            or cls in {"manifest_kernel_dispatch_not_bound"}
            or cls in blocker_classes
        ):
            continue
        blockers.append({
            "class": cls,
            "detail": str(blocker.get("detail") or cls),
        })
        blocker_classes.add(cls)
    real_session = streaming_trace.get("realSessionRuntime") or {}
    if real_session:
        real_session_status = str(real_session.get("status") or "unknown")
        if real_session_status != "output_ready":
            blocker = {
                "class": "real_session_runtime_not_output_ready",
                "detail": (
                    "The Gemma 4 31B af16 session runtime contract is "
                    f"present, but status is {real_session_status!r}; "
                    "no token/logit/KV transcript is available for parity."
                ),
            }
            if blocker["class"] not in blocker_classes:
                blockers.append(blocker)
                blocker_classes.add(blocker["class"])
    elif "combined_session_runtime_absent" not in trace_blocker_classes:
        blocker = {
            "class": "combined_session_runtime_absent",
            "detail": (
                "The Gemma 4 31B af16 HostPlan streaming front door is "
                "present, but it has not produced a token/logit/KV "
                "transcript from a session-scoped SDK execution."
            ),
        }
        if blocker["class"] not in blocker_classes:
            blockers.append(blocker)
            blocker_classes.add(blocker["class"])
    return blockers


def build_receipt(
    *,
    source_doppler_manifest: Path,
    frozen_reference_root: Path,
    compile_receipt: Path,
    host_plan: Path,
    per_kernel_summary: Path,
    prefill_token_count: int,
    decode_token_count: int,
    source_graph_inventory: Path | None = None,
    streaming_trace: Path = DEFAULT_STREAMING_TRACE,
    emit_blocked_on_evidence_gate: bool = False,
) -> dict[str, Any]:
    for label, path in (
        ("source Doppler manifest", source_doppler_manifest),
        ("compile receipt", compile_receipt),
        ("host plan", host_plan),
        ("per-kernel summary", per_kernel_summary),
        ("streaming runner", DEFAULT_STREAMING_RUNNER),
    ):
        _require_file(path, label)

    source_inventory = (
        _source_graph_inventory(source_graph_inventory)
        if source_graph_inventory is not None
        else {
            "path": "",
            "present": False,
            "requiredKernels": None,
        }
    )
    inference_gate_result = evaluate_inference_evidence_gate(
        host_plan=_load_json(host_plan),
        per_kernel_summary=_load_json(per_kernel_summary),
        source_graph_kernels=source_inventory.get("requiredKernels"),
    )
    if (
        not inference_gate_result.eligible
        and not emit_blocked_on_evidence_gate
    ):
        enforce_inference_evidence_gate(
            host_plan=_load_json(host_plan),
            per_kernel_summary=_load_json(per_kernel_summary),
            source_graph_kernels=source_inventory.get("requiredKernels"),
        )
    inference_gate = inference_gate_result.to_dict()

    dtype_profile = _load_dtype_profile(source_doppler_manifest)
    csl_dtype_contract = csl_dtype_contract_for_profile(
        dtype_profile,
        model_id=MODEL_ID,
    )
    reference = _reference_summary(
        frozen_reference_root,
        requested_prefill=prefill_token_count,
        requested_decode=decode_token_count,
    )
    host_plan_info = _host_plan_summary(host_plan)
    compile_info = _compile_summary(compile_receipt)
    kernel_info = _per_kernel_summary(per_kernel_summary)
    streaming_info = _streaming_trace_summary(streaming_trace)
    blockers = _blockers(
        reference=reference,
        compile_summary=compile_info,
        kernel_summary=kernel_info,
        streaming_trace=streaming_info,
        inference_gate=inference_gate,
    )
    status = "blocked" if blockers else "ready_for_sdk_host"
    receipt = {
        "schemaVersion": 2,
        "artifactKind": ARTIFACT_KIND,
        "receiptClass": "manifest_shape_bounded_inference_smoke",
        "comparisonMode": "parity",
        "modelId": MODEL_ID,
        "laneKey": LANE_KEY,
        "dtypeProfile": dtype_profile,
        "cslDtypeContract": csl_dtype_contract,
        "manifestPath": _display_path(source_doppler_manifest),
        "manifestSha256": _sha256_file(source_doppler_manifest),
        "referenceFixtureHash": reference["fixtureDigest"],
        "hostPlanPath": host_plan_info["path"],
        "hostPlanHash": host_plan_info["sha256"],
        "requestedSmoke": {
            "prefillTokenCount": prefill_token_count,
            "decodeTokenCount": decode_token_count,
            "phaseContract": "prefill_then_fixed_greedy_decode",
        },
        "dopplerReference": reference,
        "sourceProgram": {
            "compileReceiptPath": compile_info["path"],
            "compileReceiptSha256": compile_info["sha256"],
            "compileTargetCount": compile_info["compileTargetCount"],
            "compileSucceededCount": compile_info["compileSucceededCount"],
            "compileBlockerClass": compile_info["blockerClass"],
            "hostPlanPath": host_plan_info["path"],
            "hostPlanHash": host_plan_info["sha256"],
            "peGrid": host_plan_info["peGrid"],
            "phaseKernelCounts": host_plan_info["phaseKernelCounts"],
            "sourceGraphInventory": source_inventory,
        },
        "perKernelEvidence": kernel_info,
        "inferenceEvidenceGate": inference_gate,
        "hostPlanStreamingTrace": streaming_info,
        "executionPlan": {
            "kind": "session_scoped_hostplan_streaming_runner",
            "runnerPath": _display_path(DEFAULT_STREAMING_RUNNER),
            "runnerSha256": _sha256_file(DEFAULT_STREAMING_RUNNER),
            "stateRequirements": [
                "stage shared Q4K weight pack once per session",
                "materialize f16 activation buffers for each HostPlan step",
                "preserve KV cache symbols across decode steps",
                "feed sampled token IDs into the next decode input",
                "emit per-step logits digests and generated token IDs",
            ],
            "dispatchSequence": [
                "tokenize prompt",
                "run hostPlan.phases.prefill once",
                "for each decode step: run hostPlan.phases.decode",
                "read sample output and append token ID",
                "write transcript with token/logit/KV digests",
            ],
        },
        "status": status,
        "blockers": blockers,
        "claim": {
            "scope": (
                "Gemma 4 31B af16 bounded simulator-smoke contract is "
                "hash-bound to the af16 Doppler manifest, frozen Doppler "
                "reference fixture, af16 HostPlan compile receipt, and "
                "current per-kernel evidence."
            ),
            "notWhat": (
                "Not a Doe CSL inference success receipt. Not a hardware "
                "receipt. Not a parity claim until a session-scoped HostPlan "
                "runner emits the matching token/logit/KV transcript."
            ),
            "summary": (
                "Gemma 4 31B af16 bounded inference smoke is specified and "
                "blocked on the named simulator execution gaps."
            ),
        },
    }
    return receipt


def validate_receipt(receipt: dict[str, Any], schema_path: Path) -> None:
    schema = _load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(receipt)
    enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)


def main() -> int:
    args = parse_args()
    if args.prefill_token_count < 1:
        sys.stderr.write("--prefill-token-count must be >= 1\n")
        return 2
    if args.decode_token_count < 1:
        sys.stderr.write("--decode-token-count must be >= 1\n")
        return 2
    try:
        receipt = build_receipt(
            source_doppler_manifest=args.source_doppler_manifest,
            frozen_reference_root=args.frozen_reference_root,
            compile_receipt=args.compile_receipt,
            host_plan=args.host_plan,
            per_kernel_summary=args.per_kernel_summary,
            source_graph_inventory=args.source_graph_inventory,
            streaming_trace=args.streaming_trace,
            prefill_token_count=args.prefill_token_count,
            decode_token_count=args.decode_token_count,
            emit_blocked_on_evidence_gate=args.emit_blocked_on_evidence_gate,
        )
        validate_receipt(receipt, args.schema)
    except (
        FileNotFoundError,
        ValueError,
        LaneDtypeProfileError,
        ReceiptHashSpineError,
        InferenceEvidenceGateError,
        jsonschema.ValidationError,
    ) as err:
        sys.stderr.write(
            "synthesize_gemma4_31b_af16_bounded_inference_smoke_receipt: "
            f"{err}\n"
        )
        return 2

    out = _resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {_display_path(out)} status={receipt['status']} "
        f"blockers={len(receipt['blockers'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
