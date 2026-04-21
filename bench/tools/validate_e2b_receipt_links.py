#!/usr/bin/env python3
"""Receipt link-integrity check for the E2B model runtime receipt.

Reads bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json and walks
every (path, sha256) pair recorded in it. For each link, asserts:

  - the path resolves to a file on disk
  - the on-disk sha256 matches the sha256 the receipt recorded

Reports per-link status (PASS / FAIL with reason). Exits 0 only if every
link resolves with matching sha. The parity-contract gate can call this
independently of any regen — it doesn't run the kernel, doesn't re-sha
the live source, and doesn't depend on cs_python; it just confirms the
receipt's machine-readable evidence is internally consistent.

Link locations walked:
  artifactHashes.<key>.{path, sha256}                      (6+ entries)
  streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence:
      kernelSourcePath          + kernelSourceSha256
      referenceDoc.path         + referenceDoc.sha256
      syntheticTrace.path       + syntheticTrace.sha256
      syntheticTrace.outputPath + syntheticTrace.outputSha256
      crossRuntimeParityCheck.path + ...sha256
      tracePath                 + traceSha256              (if present)
  sdkLayoutModelExecutionEvidence:
      streamExecutionPlan.path  + streamExecutionPlan.sha256
      kernelSource.path         + kernelSource.sha256
      simulatorArtifacts.trace.path + ...sha256
      simulatorArtifacts.output.path + ...sha256
      parity.verdictPath        + parity.verdictSha256
  sdkLayoutDepthDiagnosticEvidence.diagnostics[]:
      parity.path               + parity.sha256
      parity.weightsAudit.path  + parity.weightsAudit.sha256
      trace.path                + trace.sha256
      trace.output.path         + trace.output.sha256
  manifestShapePartialExecutionEvidence:
      attentionCoreReceipt.path + attentionCoreReceipt.sha256
      inputs.executionManifest.path + inputs.executionManifest.sha256
      inputs.kernelSource.path  + inputs.kernelSource.sha256
  dopplerWebgpuCaptureEvidence:
      captureGraph.path         + captureGraph.sha256
      model.manifestPath        + model.manifestSha256
"""

from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--receipt",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    return p.parse_args()


def collect_links(receipt: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return [(label, path, recorded_sha)] for every (path, sha) pair
    in the receipt. Skips entries where either field is missing — those
    are useful but not link-checkable here."""
    links: list[tuple[str, str, str]] = []

    # artifactHashes block: {executionManifest, hostPlan, ...}
    for key, val in (receipt.get("artifactHashes") or {}).items():
        path = (val or {}).get("path")
        sha = (val or {}).get("sha256")
        if path and sha:
            links.append((f"artifactHashes.{key}", path, sha))

    # layerBlockKernelEvidence sub-block.
    lbk = (
        receipt.get("streamingExecutorPrimitivesEvidence", {})
        .get("layerBlockKernelEvidence", {})
    )

    # kernelSource: top-level path + sha
    ks_path = lbk.get("kernelSourcePath")
    ks_sha = lbk.get("kernelSourceSha256")
    if ks_path and ks_sha:
        links.append(("layerBlockKernelEvidence.kernelSource", ks_path, ks_sha))

    # tracePath + traceSha256 (when the runner actually ran)
    t_path = lbk.get("tracePath")
    t_sha = lbk.get("traceSha256")
    if t_path and t_sha:
        links.append(("layerBlockKernelEvidence.runnerTrace", t_path, t_sha))

    # Sub-blocks that follow the same {path, exists, sha256} shape.
    for sub_key in ("referenceDoc", "syntheticTrace", "crossRuntimeParityCheck"):
        sub = lbk.get(sub_key) or {}
        path = sub.get("path")
        sha = sub.get("sha256")
        if path and sha:
            links.append(
                (f"layerBlockKernelEvidence.{sub_key}", path, sha)
            )
        # Output tensor digest on the sub-block (e.g. syntheticTrace's
        # outputPath + outputSha256 point at the final-layer f32 bytes
        # that P6 uses as the bit-exact parity target). Walked under
        # the non-standard field-name pair so the canonical parity
        # target is always link-integrity-verified.
        out_path = sub.get("outputPath")
        out_sha = sub.get("outputSha256")
        if out_path and out_sha:
            links.append(
                (f"layerBlockKernelEvidence.{sub_key}.output",
                 out_path, out_sha)
            )

    sdk = receipt.get("sdkLayoutModelExecutionEvidence") or {}
    plan = sdk.get("streamExecutionPlan") or {}
    if plan.get("path") and plan.get("sha256"):
        links.append((
            "sdkLayoutModelExecutionEvidence.streamExecutionPlan",
            plan["path"],
            plan["sha256"],
        ))
    kernel = sdk.get("kernelSource") or {}
    if kernel.get("path") and kernel.get("sha256"):
        links.append((
            "sdkLayoutModelExecutionEvidence.kernelSource",
            kernel["path"],
            kernel["sha256"],
        ))
    artifacts = sdk.get("simulatorArtifacts") or {}
    for sub_key in ("trace", "output"):
        sub = artifacts.get(sub_key) or {}
        if sub.get("path") and sub.get("sha256"):
            links.append((
                f"sdkLayoutModelExecutionEvidence.simulatorArtifacts.{sub_key}",
                sub["path"],
                sub["sha256"],
            ))
    parity = sdk.get("parity") or {}
    if parity.get("verdictPath") and parity.get("verdictSha256"):
        links.append((
            "sdkLayoutModelExecutionEvidence.parity",
            parity["verdictPath"],
            parity["verdictSha256"],
        ))

    manifest_partial = (
        receipt.get("manifestShapePartialExecutionEvidence") or {}
    )
    attention_core = manifest_partial.get("attentionCoreReceipt") or {}
    if attention_core.get("path") and attention_core.get("sha256"):
        links.append((
            "manifestShapePartialExecutionEvidence.attentionCoreReceipt",
            attention_core["path"],
            attention_core["sha256"],
        ))
    partial_inputs = manifest_partial.get("inputs") or {}
    for sub_key in ("executionManifest", "kernelSource"):
        sub = partial_inputs.get(sub_key) or {}
        if sub.get("path") and sub.get("sha256"):
            links.append((
                f"manifestShapePartialExecutionEvidence.inputs.{sub_key}",
                sub["path"],
                sub["sha256"],
            ))

    capture = receipt.get("dopplerWebgpuCaptureEvidence") or {}
    capture_graph = capture.get("captureGraph") or {}
    if capture_graph.get("path") and capture_graph.get("sha256"):
        links.append((
            "dopplerWebgpuCaptureEvidence.captureGraph",
            capture_graph["path"],
            capture_graph["sha256"],
        ))
    capture_model = capture.get("model") or {}
    if capture_model.get("manifestPath") and capture_model.get("manifestSha256"):
        links.append((
            "dopplerWebgpuCaptureEvidence.model.manifest",
            capture_model["manifestPath"],
            capture_model["manifestSha256"],
        ))

    depth = receipt.get("sdkLayoutDepthDiagnosticEvidence") or {}
    for idx, diagnostic in enumerate(depth.get("diagnostics") or []):
        label_prefix = (
            "sdkLayoutDepthDiagnosticEvidence."
            f"diagnostics[{idx}]"
        )
        parity = diagnostic.get("parity") or {}
        if parity.get("path") and parity.get("sha256"):
            links.append((
                f"{label_prefix}.parity",
                parity["path"],
                parity["sha256"],
            ))
        audit = parity.get("weightsAudit") or {}
        if audit.get("path") and audit.get("sha256"):
            links.append((
                f"{label_prefix}.parity.weightsAudit",
                audit["path"],
                audit["sha256"],
            ))
        trace = diagnostic.get("trace") or {}
        if trace.get("path") and trace.get("sha256"):
            links.append((
                f"{label_prefix}.trace",
                trace["path"],
                trace["sha256"],
            ))
        output = trace.get("output") or {}
        if output.get("path") and output.get("sha256"):
            links.append((
                f"{label_prefix}.trace.output",
                output["path"],
                output["sha256"],
            ))

    return links


def main() -> int:
    args = parse_args()
    receipt_path = resolve(args.receipt)
    if not receipt_path.is_file():
        print(f"ERROR: receipt not found at {receipt_path}", file=sys.stderr)
        return 2
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    print(f"E2B receipt link-integrity check")
    print(f"  receipt: {receipt_path.relative_to(REPO_ROOT)}")
    print()

    links = collect_links(receipt)
    if not links:
        print("FAIL — receipt has no (path, sha256) pairs to check")
        return 1

    failures: list[str] = []
    print(f"  walking {len(links)} link(s):")
    for label, path_str, recorded_sha in links:
        abs_path = resolve(path_str)
        if not abs_path.is_file():
            failures.append(f"{label}: path missing  ({path_str})")
            print(f"    FAIL  {label:60} (path missing)")
            continue
        actual_sha = sha256_file(abs_path)
        if actual_sha != recorded_sha:
            failures.append(
                f"{label}: sha mismatch  recorded={recorded_sha[:16]}... "
                f"actual={actual_sha[:16]}..."
            )
            print(
                f"    FAIL  {label:60}  "
                f"sha {recorded_sha[:16]} != {actual_sha[:16]}"
            )
            continue
        print(f"    PASS  {label:60}  {recorded_sha[:16]}...")

    print()
    if failures:
        print(f"FAIL — {len(failures)} link(s) inconsistent:")
        for f in failures:
            print(f"  {f}")
        return 1

    print(f"PASS — every link resolves with matching sha ({len(links)}/{len(links)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
