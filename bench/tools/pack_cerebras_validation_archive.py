#!/usr/bin/env python3
"""Pack a Cerebras hardware-validation archive.

Takes the governing evidence (hardware-validation appendix +
claim-discipline doc + evidence-bundle summary + model runtime
receipts + cross-runtime parity verdicts + real-weight parity
verdicts + Doppler RDRR probe/Q4_K_M parity + fixture contracts +
MoE lane-scope + archive-root governance docs) and bundles it into a dated tarball
suitable for attaching to a hardware-access ask.

What IS included: see the INCLUDE_FILES tuple below. Every bundled
file's sha256 is recorded in MANIFEST.txt with a claim-role tag.
C22 in bench/tools/e2b_layer_block_self_check.py asserts that tuple
and the CLAIM_ROLE dict stay in sync.

What is explicitly NOT included (sensitive size / provider bytes /
anything that would require operator approval to publish): see the
EXCLUDE_SUBSTRINGS tuple. Defense-in-depth: the verifier's
FORBIDDEN_EXTENSIONS and FORBIDDEN_PATH_SUBSTRINGS re-enforce the
same deny-list on the packed archive, and C23 / C32 lock the two
sides in sync.

Usage:
  # default: stamped filename with git sha, dirty flag if applicable
  python3 bench/tools/pack_cerebras_validation_archive.py
  # -> bench/out/doe-cerebras-evidence-YYYYMMDD-HHMM-<shortSha>[-dirty].tar.gz

  # or explicit path:
  python3 bench/tools/pack_cerebras_validation_archive.py \\
    --out bench/out/my-custom-bundle.tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_DEPTHS = (2, 4, 8, 35)
TSIR_REAL_CANARY_KERNELS = (
    "attention_head256_f16kv",
    "attention_head512_f16kv",
    "embed",
    "fused_gemv",
    "lm_head_gemv",
    "rmsnorm",
)
TSIR_REAL_CANARY_BACKENDS = ("msl", "spir-v", "webgpu-generic", "wse3")

# Explicit allow-list. Nothing is bundled that isn't named here — the
# archive cannot accidentally pull SDK binaries or weight bytes
# because the loop walks THIS list, not a directory tree.
#
# Entries are strings OR (source_relpath, archive_relpath) tuples.
# Use the tuple form when the bundled file should sit at a different
# path inside the tarball than in the repo (e.g. surfacing a claim-
# scope doc at the archive root rather than under docs/).
# Tuple sources may use `path.md#ARCHIVE_NAME.md`; the packer extracts
# the matching `<!-- archive:ARCHIVE_NAME.md:start -->` section from
# that source doc.
INCLUDE_FILES: tuple = (
    ("docs/cerebras-evidence-bundle.md#README.md", "README.md"),
    ("docs/cerebras-evidence-bundle.md#CLAIM_SCOPE.md", "CLAIM_SCOPE.md"),
    ("docs/cerebras-evidence-bundle.md#MODEL_ACCESS.md", "MODEL_ACCESS.md"),
    ("docs/cerebras-evidence-bundle.md#CEREBRAS_ASK.md", "CEREBRAS_ASK.md"),
    ("docs/cerebras-evidence-bundle.md#LOCAL_INSPECTION.md", "LOCAL_INSPECTION.md"),
    # NOTE: docs/cerebras-evidence-bundle-pointer.md is intentionally
    # NOT bundled. The prep script writes it AFTER pack, so bundling
    # it would always ship stale values. BUNDLE_META.json inside the
    # archive is authoritative; the pointer doc is a repo-side mirror
    # for git visibility only.
    "docs/hardware-validation-appendix.md",
    "docs/cerebras-hardware-runbook.md",
    "docs/claim-discipline.md",
    # Fixture contracts: one per primary model lane.
    "config/doe-frozen-doppler-reference.schema.json",
    "config/doppler-to-csl-splice-receipt.schema.json",
    "config/doppler-selected-logit-splice-receipt.schema.json",
    "config/gemma-4-e2b-real-weight-fixture.json",
    "config/gemma-4-31b-real-weight-fixture.json",
    "config/qwen-3-6-27b-real-weight-fixture.json",
    "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json",
    "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json",
    "bench/tools/run_gemma4_31b_af16_hardware_path.sh",
    "bench/tools/run_qwen3_6_27b_af16_hardware_path.sh",
    "bench/tools/run_qwen3_6_27b_af16_local_simfabric_ceiling.py",
    "bench/runners/csl-runners/qwen3_6_27b_af16_hostplan_streaming_runner.py",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/host-plan.json",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/runtime-config.json",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/simulator-plan.json",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/memory-plan.json",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/source-graph-inventory.json",
    # Model runtime receipts (json + md for each model).
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.md",
    # Cross-runtime parity verdicts (per model).
    "bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json",
    "bench/out/streaming-executor/gemma-4-31b-layer-block-cross-runtime-parity-check.json",
    # CSL emulator evidence (claimable local-debug speed only for L1 today).
    "bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json",
    # Manifest-shape blocker: upstream tensor metadata vs Doe manifest fields.
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-attention-core.json",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-runtime-path.json",
    "bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json",
    "bench/out/doppler-capture/gemma-4-e2b-capture-to-csl-attention-core-lowering.json",
    # Real-weight parity verdicts and depth diagnostics.
    "bench/out/gemma-4-e2b-real-weight-parity-L1.json",
    *(
        f"bench/out/gemma-4-e2b-real-weight-parity-L{depth}.json"
        for depth in DIAGNOSTIC_DEPTHS
    ),
    "bench/out/gemma-4-31b-real-weight-parity-L1.json",
    # Doppler production-artifact structural probe and Q4_K_M smoke parity.
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-extraction.json",
    "bench/out/weights-audit/gemma-4-e2b-rdrr-int4ple-weights-audit.json",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-l1-parity.json",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json",
    *(
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-rdrr-l{depth}-parity.json"
        for depth in DIAGNOSTIC_DEPTHS
    ),
    *(
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-q4k-parity-L{depth}.json"
        for depth in DIAGNOSTIC_DEPTHS
    ),
    # 26B/A4B MoE lane scope (explicitly blocked, 6 TODO receipts).
    "bench/out/26b-moe-lane/lane-status.json",
    "bench/out/26b-moe-lane/router-todo.json",
    "bench/out/26b-moe-lane/topk-selection-todo.json",
    "bench/out/26b-moe-lane/token-dispatch-todo.json",
    "bench/out/26b-moe-lane/shared-expert-todo.json",
    "bench/out/26b-moe-lane/output-combine-todo.json",
    "bench/out/26b-moe-lane/per-expert-batching-todo.json",
    # Rollups that summarize the lane matrix and gate runs.
    "bench/out/doe-run/all-lanes-summary-L1.json",
    "bench/out/doe-run/depth-coverage-matrix.json",
    "bench/out/doe-run/webgpu-wgsl/L1-receipt.json",
    "bench/out/doe-run/csl-webgpu-emulator/L1-receipt.json",
    "bench/out/doe-run/csl-sdklayout/L1-receipt.json",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/execution_graph.json",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/prompt.txt",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/tokenized_prompt.u32",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/generated_tokens.u32",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/decode_transcript.json",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_int4ple_reference_export.json",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/execution_graph.json",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/prompt.txt",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/tokenized_prompt.u32",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/generated_tokens.u32",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/decode_transcript.json",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/doppler_int4ple_reference_export.json",
    # 31B-led evidence (Step 1 of the Cerebras bundle drive plan).
    # Sources are promoted from dated overnight-matrix cells to stable
    # paths so the packer's static allow-list stays deterministic; the
    # PROVENANCE.json files name the original source paths and hashes.
    "bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json",
    "bench/out/r3-1-31b-doppler-reference/reference.json",
    "bench/out/r3-1-31b-doppler-reference/PROVENANCE.json",
    "bench/out/r3-1-31b-a3-partial/trace.json.progress.jsonl",
    "bench/out/r3-1-31b-a3-partial/PROVENANCE.json",
    "bench/out/r3-1-31b-l1-dry/trace.json",
    "bench/out/r3-1-31b-l61-smoke/trace.json",
    # Gemma AF16 simfabric cell evidence. Source files keep the
    # production kernel stem; receipts bind bounded simfabric parity.
    "bench/runners/csl-runners/gemma-4-31b-af16-cells/README.md",
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "lm_head_prefill_layout.csl"
    ),
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "lm_head_prefill_pe_program.csl"
    ),
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "lm_head_prefill_run.py"
    ),
    (
        "bench/runners/csl-runners/doppler-csl-splice-cells/"
        "final_norm_f16_layout.csl"
    ),
    (
        "bench/runners/csl-runners/doppler-csl-splice-cells/"
        "final_norm_f16_pe_program.csl"
    ),
    (
        "bench/out/r3-1-31b-gemma-af16-lm-head-prefill-"
        "simfabric-cell/receipt.json"
    ),
    (
        "bench/out/r3-1-31b-gemma-af16-simfabric-cells/"
        "summary-receipt.json"
    ),
    # Current Cerebras lane status and bounded af16 blocker taxonomy.
    "bench/out/r3-cerebras-status/snapshot.json",
    "bench/out/r3-cerebras-status/snapshot.md",
    "bench/out/r3-cross-model-parity/receipt.json",
    (
        "bench/out/r3-1-31b-af16-bounded-inference-smoke/"
        "receipt.json"
    ),
    (
        "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/"
        "summary.json"
    ),
    (
        "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/"
        "lm_head_prefill_width_tile_x0_w32.json"
    ),
    "bench/out/r3-1-31b-af16-local-simfabric-ceiling/receipt.json",
    (
        "bench/fixtures/r3-1-31b-doppler-frozen-af16/"
        "frozen-reference.manifest.json"
    ),
    (
        "bench/fixtures/r3-1-31b-doppler-frozen-af16/"
        "reference-report.json"
    ),
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "single-block-hidden.json"
    ),
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "single_block_hidden-run.json"
    ),
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "session-single_block_hidden/hostplan-runtime/launch-receipts/"
        "launch-0001.json"
    ),
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "session-single_block_hidden/hostplan-runtime/tiled-q4k-gemv/"
        "launch-0001/batch-shards/batch-0000-phase.log"
    ),
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "last-layer-tail-token.json"
    ),
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "selected-logit-splice/selected-logit-splice.json"
    ),
    (
        "bench/out/r3-2-27b-af16-doppler-csl-splice/"
        "selected-logit-splice/selected-logit-splice.json"
    ),
    "bench/out/r3-2-27b-af16-local-simfabric-ceiling/receipt.json",
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "program-bundle.node.json"
    ),
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "reference-report.json"
    ),
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "int4ple-export/doppler_int4ple_reference_export.json"
    ),
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "int4ple-export/final_logits.f32"
    ),
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "tsir-fixture/layer_63/post_ffn.npy"
    ),
    "bench/out/r3-1-31b-af16-full-graph-compile-attempt/receipt.json",
    "bench/out/r3-2-27b-af16-full-graph-compile-attempt/receipt.json",
    (
        "bench/out/r3-2-27b-af16-manifest-simfabric-predicted-wallclock/"
        "budget.json"
    ),
    "bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json",
    # 31B no-hardware evidence promoted after the initial bundle.
    "bench/out/r3-1-31b-manifest-compile-attempt/receipt.json",
    "bench/out/r3-1-31b-manifest-compile-attempt/PROVENANCE.json",
    "bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json",
    "bench/out/r3-1-31b-manifest-compile-sweep/PROVENANCE.json",
    "bench/out/r3-1-31b-deployment-widths/derived-widths.json",
    "bench/out/r3-1-31b-deployment-widths/PROVENANCE.json",
    "bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json",
    "bench/out/r3-1-31b-full-graph-compile-attempt/PROVENANCE.json",
    "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/driver-result.json",
    "bench/out/r3-1-31b-bounded-decode-integrated/receipt.json",
    "bench/out/r3-1-31b-bounded-decode-integrated/stage1_kv_write.trace.json",
    "bench/out/r3-1-31b-bounded-decode-integrated/stage2_attention_decode.trace.json",
    "bench/out/r3-1-31b-bounded-decode-integrated/stage3_sample.trace.json",
    "bench/out/r3-1-31b-bounded-decode-integrated/PROVENANCE.json",
    "bench/out/r3-1-31b-multi-token-decode/receipt.json",
    "bench/out/r3-1-31b-multi-token-decode/PROVENANCE.json",
    "bench/out/r3-1-31b-real-weights/pin.json",
    "bench/out/r3-1-31b-real-weights/file_hashes.txt",
    "bench/out/r3-1-31b-real-weights/PROVENANCE.json",
    "bench/out/r3-1-31b-real-weight-smoke-extraction/receipt.json",
    "bench/out/r3-1-31b-real-weight-smoke-extraction/audit.json",
    (
        "bench/out/r3-1-tsir-cross-backend/real-canary-with-transcripts/"
        "nightly-tsir-parity-canary.json"
    ),
    *(
        (
            "bench/out/r3-1-tsir-cross-backend/"
            "real-canary-with-transcripts/receipts/"
            f"{kernel}.{backend}/{kernel}.parity.json"
        )
        for kernel in TSIR_REAL_CANARY_KERNELS
        for backend in TSIR_REAL_CANARY_BACKENDS
    ),
    "bench/out/cerebras-evidence-bundle/summary.json",
)

# Deny-list substrings. Belt-and-suspenders over the allow-list: if
# someone adds a new allow-list entry by mistake, these tokens in the
# relative path block it from the archive.
EXCLUDE_SUBSTRINGS: tuple[str, ...] = (
    ".elf",
    ".lst",
    ".map",
    ".symbols",
    ".viz",
    ".f32",
    "/scratch/",
    "/compile/",
    "/compile-L",
    "simulator.log",
    ".stderr",
    ".stdout",
)

# Claim-role taxonomy per bundled file. Values enforced in MANIFEST
# so reviewers can see at a glance what each artifact is evidence
# FOR, not just where it came from.
CLAIM_ROLE: dict[str, str] = {
    "README.md": "governance",
    "CLAIM_SCOPE.md": "governance",
    "MODEL_ACCESS.md": "governance",
    "CEREBRAS_ASK.md": "governance",
    "LOCAL_INSPECTION.md": "governance",
    "docs/hardware-validation-appendix.md": "governance",
    "docs/cerebras-hardware-runbook.md": "hardware-runbook",
    "docs/claim-discipline.md": "governance",
    "config/doe-frozen-doppler-reference.schema.json": "fixture-schema",
    "config/doppler-to-csl-splice-receipt.schema.json": "splice-receipt-schema",
    "config/doppler-selected-logit-splice-receipt.schema.json": "selected-logit-splice-receipt-schema",
    "config/gemma-4-e2b-real-weight-fixture.json": "real-weight-fixture",
    "config/gemma-4-31b-real-weight-fixture.json": "real-weight-fixture",
    "config/qwen-3-6-27b-real-weight-fixture.json": "real-weight-fixture",
    "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json": "doppler-rdrr-fixture",
    "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json": "qwen-execution-v1-contract",
    "bench/tools/run_gemma4_31b_af16_hardware_path.sh": "hardware-runner-wrapper",
    "bench/tools/run_qwen3_6_27b_af16_hardware_path.sh": "hardware-runner-wrapper",
    "bench/tools/run_qwen3_6_27b_af16_local_simfabric_ceiling.py": "local-simfabric-ceiling-tool",
    "bench/runners/csl-runners/qwen3_6_27b_af16_hostplan_streaming_runner.py": "hardware-runner-source",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/host-plan.json": "qwen-hostplan-fixture",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/runtime-config.json": "qwen-hostplan-fixture",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/simulator-plan.json": "qwen-hostplan-fixture",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/memory-plan.json": "qwen-hostplan-fixture",
    "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16/source-graph-inventory.json": "qwen-hostplan-fixture",
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json": "model-runtime-receipt",
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md": "model-runtime-receipt",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json": "model-runtime-receipt",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.md": "model-runtime-receipt",
    "bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json": "cross-runtime-parity-verdict",
    "bench/out/streaming-executor/gemma-4-31b-layer-block-cross-runtime-parity-check.json": "cross-runtime-parity-verdict",
    "bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json": "emulator-speed-verdict",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json": "manifest-shape-probe",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json": "manifest-shape-execution-oracle",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-attention-core.json": "manifest-shape-attention-core",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-runtime-path.json": "manifest-shape-runtime-path",
    "bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json": "doppler-webgpu-capture-graph",
    "bench/out/doppler-capture/gemma-4-e2b-capture-to-csl-attention-core-lowering.json": "doppler-webgpu-capture-lowering",
    "bench/out/gemma-4-e2b-real-weight-parity-L1.json": "real-weight-parity-verdict",
    **{
        (
            f"bench/out/gemma-4-e2b-real-weight-parity-L{depth}.json"
        ): "real-weight-parity-verdict"
        for depth in DIAGNOSTIC_DEPTHS
    },
    "bench/out/gemma-4-31b-real-weight-parity-L1.json": "real-weight-parity-verdict",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json": "doppler-rdrr-probe",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-extraction.json": "doppler-rdrr-q4k-extraction",
    "bench/out/weights-audit/gemma-4-e2b-rdrr-int4ple-weights-audit.json": "doppler-rdrr-q4k-audit",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-l1-parity.json": "doppler-rdrr-q4k-parity",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json": "doppler-rdrr-q4k-parity",
    **{
        (
            "bench/out/doppler-rdrr/"
            f"gemma-4-e2b-int4ple-rdrr-l{depth}-parity.json"
        ): "doppler-rdrr-q4k-parity"
        for depth in DIAGNOSTIC_DEPTHS
    },
    **{
        (
            "bench/out/doppler-rdrr/"
            f"gemma-4-e2b-int4ple-q4k-parity-L{depth}.json"
        ): "doppler-rdrr-q4k-parity"
        for depth in DIAGNOSTIC_DEPTHS
    },
    "bench/out/26b-moe-lane/lane-status.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/router-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/topk-selection-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/token-dispatch-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/shared-expert-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/output-combine-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/per-expert-batching-todo.json": "moe-lane-scope",
    "bench/out/doe-run/all-lanes-summary-L1.json": "rollup",
    "bench/out/doe-run/depth-coverage-matrix.json": "depth-coverage-rollup",
    "bench/out/doe-run/webgpu-wgsl/L1-receipt.json": "target-run-receipt",
    "bench/out/doe-run/csl-webgpu-emulator/L1-receipt.json": "target-run-receipt",
    "bench/out/doe-run/csl-sdklayout/L1-receipt.json": "target-run-receipt",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/execution_graph.json": "doppler-int4ple-execution-graph",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/prompt.txt": "doppler-int4ple-reference-input",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/tokenized_prompt.u32": "doppler-int4ple-reference-input",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/generated_tokens.u32": "doppler-int4ple-reference-output-tokens",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/decode_transcript.json": "doppler-int4ple-reference-transcript",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_int4ple_reference_export.json": "doppler-int4ple-reference-export",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/execution_graph.json": "doppler-31b-af16-splice-execution-graph",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/prompt.txt": "doppler-31b-af16-splice-reference-input",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/tokenized_prompt.u32": "doppler-31b-af16-splice-reference-input",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/generated_tokens.u32": "doppler-31b-af16-splice-reference-output-tokens",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/decode_transcript.json": "doppler-31b-af16-splice-reference-transcript",
    "bench/out/doppler-reference/gemma-4-31b-af16-bos-the-color-of-the-sky-is-prefill-decode2/doppler_int4ple_reference_export.json": "doppler-31b-af16-splice-reference-export",
    "bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json": "doppler-31b-program-bundle",
    "bench/out/r3-1-31b-doppler-reference/reference.json": "doppler-31b-webgpu-prefill-decode-reference",
    "bench/out/r3-1-31b-doppler-reference/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-a3-partial/trace.json.progress.jsonl": "doe-csl-31b-a3-partial-typed-blocked",
    "bench/out/r3-1-31b-a3-partial/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-l1-dry/trace.json": "simfabric-31b-l1-smoke-receipt",
    "bench/out/r3-1-31b-l61-smoke/trace.json": "simfabric-31b-l61-smoke-receipt",
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "README.md"
    ): "simfabric-cell-source",
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "lm_head_prefill_layout.csl"
    ): "simfabric-cell-source",
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "lm_head_prefill_pe_program.csl"
    ): "simfabric-cell-source",
    (
        "bench/runners/csl-runners/gemma-4-31b-af16-cells/"
        "lm_head_prefill_run.py"
    ): "simfabric-cell-source",
    (
        "bench/runners/csl-runners/doppler-csl-splice-cells/"
        "final_norm_f16_layout.csl"
    ): "doppler-csl-splice-cell-source",
    (
        "bench/runners/csl-runners/doppler-csl-splice-cells/"
        "final_norm_f16_pe_program.csl"
    ): "doppler-csl-splice-cell-source",
    (
        "bench/out/r3-1-31b-gemma-af16-lm-head-prefill-"
        "simfabric-cell/receipt.json"
    ): "simfabric-cell-receipt",
    (
        "bench/out/r3-1-31b-gemma-af16-simfabric-cells/"
        "summary-receipt.json"
    ): "simfabric-cells-summary",
    "bench/out/r3-cerebras-status/snapshot.json": "status-snapshot",
    "bench/out/r3-cerebras-status/snapshot.md": "status-snapshot",
    "bench/out/r3-cross-model-parity/receipt.json": "cross-model-parity-scope",
    (
        "bench/out/r3-1-31b-af16-bounded-inference-smoke/"
        "receipt.json"
    ): "bounded-inference-smoke-receipt",
    (
        "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/"
        "summary.json"
    ): "manifest-simfabric-per-kernel-summary",
    (
        "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/"
        "lm_head_prefill_width_tile_x0_w32.json"
    ): "manifest-simfabric-per-kernel-receipt",
    (
        "bench/out/r3-1-31b-af16-local-simfabric-ceiling/"
        "receipt.json"
    ): "gemma-af16-local-simfabric-ceiling",
    (
        "bench/fixtures/r3-1-31b-doppler-frozen-af16/"
        "frozen-reference.manifest.json"
    ): "doppler-frozen-fixture-manifest",
    (
        "bench/fixtures/r3-1-31b-doppler-frozen-af16/"
        "reference-report.json"
    ): "doppler-frozen-reference-report",
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "single-block-hidden.json"
    ): "doppler-csl-splice-receipt",
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "single_block_hidden-run.json"
    ): "doppler-csl-splice-run-receipt",
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "session-single_block_hidden/hostplan-runtime/launch-receipts/"
        "launch-0001.json"
    ): "doppler-csl-splice-blocked-launch-receipt",
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "session-single_block_hidden/hostplan-runtime/tiled-q4k-gemv/"
        "launch-0001/batch-shards/batch-0000-phase.log"
    ): "doppler-csl-splice-blocked-launch-phase-trace",
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "last-layer-tail-token.json"
    ): "doppler-csl-splice-receipt",
    (
        "bench/out/r3-1-31b-af16-doppler-csl-splice/"
        "selected-logit-splice/selected-logit-splice.json"
    ): "doppler-csl-selected-logit-splice-receipt",
    (
        "bench/out/r3-2-27b-af16-doppler-csl-splice/"
        "selected-logit-splice/selected-logit-splice.json"
    ): "qwen-doppler-csl-selected-logit-splice-receipt",
    (
        "bench/out/r3-2-27b-af16-local-simfabric-ceiling/"
        "receipt.json"
    ): "qwen-af16-local-simfabric-ceiling",
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "program-bundle.node.json"
    ): "qwen-doppler-program-bundle-reference",
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "reference-report.json"
    ): "qwen-doppler-reference-report",
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "int4ple-export/doppler_int4ple_reference_export.json"
    ): "qwen-doppler-int4ple-reference-export",
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "int4ple-export/final_logits.f32"
    ): "qwen-doppler-prefill-logits",
    (
        "bench/out/doppler-reference/"
        "qwen-3-6-27b-eaf16-the-color-of-the-sky-is-prefill-decode8/"
        "tsir-fixture/layer_63/post_ffn.npy"
    ): "qwen-doppler-final-layer-post-ffn",
    (
        "bench/out/r3-1-31b-af16-full-graph-compile-attempt/"
        "receipt.json"
    ): "gemma-af16-full-graph-compile-attempt",
    (
        "bench/out/r3-2-27b-af16-full-graph-compile-attempt/"
        "receipt.json"
    ): "qwen-af16-full-graph-compile-attempt",
    (
        "bench/out/r3-2-27b-af16-manifest-simfabric-predicted-wallclock/"
        "budget.json"
    ): "qwen-af16-simfabric-budget",
    (
        "bench/out/r3-2-27b-qwen-simfabric-cells/"
        "summary-receipt.json"
    ): "qwen-simfabric-cells-summary",
    "bench/out/r3-1-31b-manifest-compile-attempt/receipt.json": "manifest-compile-attempt",
    "bench/out/r3-1-31b-manifest-compile-attempt/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json": "manifest-compile-sweep",
    "bench/out/r3-1-31b-manifest-compile-sweep/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-deployment-widths/derived-widths.json": "deployment-width-derivation",
    "bench/out/r3-1-31b-deployment-widths/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json": "full-graph-compile-attempt",
    "bench/out/r3-1-31b-full-graph-compile-attempt/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/driver-result.json": "full-graph-compile-driver-result",
    "bench/out/r3-1-31b-bounded-decode-integrated/receipt.json": "bounded-decode-receipt",
    "bench/out/r3-1-31b-bounded-decode-integrated/stage1_kv_write.trace.json": "bounded-decode-stage-trace",
    "bench/out/r3-1-31b-bounded-decode-integrated/stage2_attention_decode.trace.json": "bounded-decode-stage-trace",
    "bench/out/r3-1-31b-bounded-decode-integrated/stage3_sample.trace.json": "bounded-decode-stage-trace",
    "bench/out/r3-1-31b-bounded-decode-integrated/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-multi-token-decode/receipt.json": "multi-token-decode-typed-blocker",
    "bench/out/r3-1-31b-multi-token-decode/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-real-weights/pin.json": "real-weight-pin",
    "bench/out/r3-1-31b-real-weights/file_hashes.txt": "real-weight-hash-manifest",
    "bench/out/r3-1-31b-real-weights/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-real-weight-smoke-extraction/receipt.json": "real-weight-smoke-extraction",
    "bench/out/r3-1-31b-real-weight-smoke-extraction/audit.json": "real-weight-smoke-extraction",
    (
        "bench/out/r3-1-tsir-cross-backend/real-canary-with-transcripts/"
        "nightly-tsir-parity-canary.json"
    ): "tsir-cross-backend-canary",
    **{
        (
            "bench/out/r3-1-tsir-cross-backend/"
            "real-canary-with-transcripts/receipts/"
            f"{kernel}.{backend}/{kernel}.parity.json"
        ): "tsir-real-canary-parity-receipt"
        for kernel in TSIR_REAL_CANARY_KERNELS
        for backend in TSIR_REAL_CANARY_BACKENDS
    },
    "bench/out/cerebras-evidence-bundle/summary.json": "rollup",
}


def git_output(args: list[str]) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + args,
            capture_output=True, text=True, check=False, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_commit() -> str:
    return git_output(["rev-parse", "HEAD"]) or "unknown"


def git_dirty_tree() -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if r.returncode != 0:
            return True
        return bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        # A timed-out or unreadable status must not produce a clean-
        # looking archive. Dirty is the conservative external signal.
        return True


def git_short_sha(commit: str) -> str:
    return commit[:12] if commit and commit != "unknown" else "nogit"


SDK_VERSION_FROM_ROOT_RE = re.compile(r"cerebras-sdk-(?P<version>[0-9][0-9.]*[0-9])")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_cs_python_availability() -> dict:
    # Availability is useful signal (bundling host CAN run live CSL);
    # the literal path leaks the bundler's home dir so redact it always.
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    cs_python = os.environ.get("DOE_CSL_CS_PYTHON", f"{sdk_root}/cs_python")
    available = Path(cs_python).is_file()
    return {
        "csPythonAvailableOnBundler": available,
        "csPythonPath": "redacted",
        "sdkRootPath": "redacted",
    }


def detect_sdk_version_metadata() -> dict:
    # Returned-receipt verification needs to bind hardware-side cslc/SDK
    # versions to the bundle that produced the ask. Capture the SDK label
    # parsed from the root directory name plus content sha256 of cslc and
    # cs_python (read from sha256sum.txt when present, otherwise hashed
    # directly). Path strings are redacted so the bundler's home dir does
    # not leak; only version label and content hashes ship.
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    sdk_root_path = Path(sdk_root)
    metadata: dict[str, object] = {
        "sdkVersionLabel": "unknown",
        "sdkRootBasename": "redacted",
        "cslcSha256": "unknown",
        "csPythonSha256": "unknown",
        "sdkSifSha256": "unknown",
        "sdkSifFilename": "unknown",
        "sha256sumFileSha256": "unknown",
    }
    if not sdk_root_path.is_dir():
        return metadata

    try:
        resolved = sdk_root_path.resolve()
    except OSError:
        resolved = sdk_root_path
    basename = resolved.name
    match = SDK_VERSION_FROM_ROOT_RE.match(basename)
    if match:
        metadata["sdkVersionLabel"] = match.group("version")
    metadata["sdkRootBasename"] = basename
    sdk_root_path = resolved

    sha_file = sdk_root_path / "sha256sum.txt"
    sums: dict[str, str] = {}
    if sha_file.is_file():
        try:
            for line in sha_file.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if len(parts) == 2 and len(parts[0]) == 64:
                    sums[parts[1]] = parts[0]
            metadata["sha256sumFileSha256"] = _sha256_file(sha_file)
        except OSError:
            pass
    cslc = sdk_root_path / "cslc"
    if "cslc" in sums:
        metadata["cslcSha256"] = sums["cslc"]
    elif cslc.is_file():
        try:
            metadata["cslcSha256"] = _sha256_file(cslc)
        except OSError:
            pass
    cs_python = sdk_root_path / "cs_python"
    if "cs_python" in sums:
        metadata["csPythonSha256"] = sums["cs_python"]
    elif cs_python.is_file():
        try:
            metadata["csPythonSha256"] = _sha256_file(cs_python)
        except OSError:
            pass
    for entry in sdk_root_path.iterdir():
        name = entry.name
        if name.startswith("sdk-cbcore-") and name.endswith(".sif"):
            metadata["sdkSifFilename"] = name
            if name in sums:
                metadata["sdkSifSha256"] = sums[name]
            else:
                try:
                    metadata["sdkSifSha256"] = _sha256_file(entry)
                except OSError:
                    pass
            break
    return metadata


def detect_host_os() -> dict:
    # Release/version can leak host identity on multi-tenant boxes.
    # Keep high-level only.
    return {
        "system": platform.system(),
        "python": platform.python_version(),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out",
        default="",
        help=(
            "Archive output path. When unset, uses "
            "bench/out/doe-cerebras-evidence-YYYYMMDD-HHMM-<shortSha>[-dirty].tar.gz"
        ),
    )
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "Allow packing from a dirty work tree. By default the packer "
            "refuses to produce an external bundle when `git status --porcelain` "
            "reports any changes, since reviewers cannot rebuild bundle "
            "identity from a commit-only state. Pass this flag to override "
            "(BUNDLE_META still records gitDirtyTree=true and the archive name "
            "is still tagged with -dirty)."
        ),
    )
    p.add_argument(
        "--skip-canary-fingerprint",
        action="store_true",
        help=(
            "Skip the pre-pack TSIR canary fingerprint check. Off by default: "
            "pack reruns nightly_tsir_parity_canary and refuses to pack if any "
            "fixture receipt's identity-chain status fails. This catches the "
            "case where TSIR / doe_wgsl source edits invalidate emitted hashes "
            "but the bundle would still ship the stale receipts. Pass this "
            "flag only when the canary is known-broken for unrelated reasons."
        ),
    )
    return p.parse_args()


def default_out_path(commit: str, dirty: bool) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime())
    short = git_short_sha(commit)
    dirty_tag = "-dirty" if dirty else ""
    return REPO_ROOT / "bench/out" / f"doe-cerebras-evidence-{stamp}-{short}{dirty_tag}.tar.gz"


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def should_exclude(relpath: str) -> str | None:
    for token in EXCLUDE_SUBSTRINGS:
        if token in relpath:
            return token
    return None


def split_section_source(raw: str) -> tuple[str, str | None]:
    if "#" not in raw:
        return raw, None
    path, section = raw.split("#", 1)
    return path, section


def read_include_bytes(source_rel: str) -> bytes:
    source_path, section = split_section_source(source_rel)
    src = REPO_ROOT / source_path
    if section is None:
        return src.read_bytes()

    text = src.read_text(encoding="utf-8")
    start = f"<!-- archive:{section}:start -->"
    end = f"<!-- archive:{section}:end -->"
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx < 0 or end_idx < 0 or end_idx <= start_idx:
        raise ValueError(
            f"missing or invalid section markers for {section} in "
            f"{source_path}"
        )
    body = text[start_idx + len(start):end_idx].strip() + "\n"
    return body.encode("utf-8")


def main() -> int:
    args = parse_args()

    commit = git_commit()
    dirty = git_dirty_tree()

    if dirty and not args.allow_dirty:
        sys.stderr.write(
            "pack_cerebras_validation_archive: refusing to pack from a dirty "
            "work tree.\n"
            "  Reviewers cannot reproduce the bundle from gitCommit alone "
            "when uncommitted changes exist.\n"
            "  Commit (or stash) the listed changes, then re-run. To override "
            "deliberately, pass --allow-dirty (BUNDLE_META still records "
            "gitDirtyTree=true and the archive name is still -dirty tagged).\n"
        )
        return 2

    if not args.skip_canary_fingerprint:
        canary_gate = REPO_ROOT / "bench/gates/nightly_tsir_parity_canary.py"
        if canary_gate.is_file():
            canary_proc = subprocess.run(
                [sys.executable, str(canary_gate)],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if canary_proc.returncode != 0:
                sys.stderr.write(
                    "pack_cerebras_validation_archive: pre-pack canary "
                    "fingerprint check failed.\n"
                    "  TSIR / doe_wgsl edits may have invalidated emitted "
                    "hashes. Refusing to pack so the bundle does not ship "
                    "stale receipts.\n"
                    "  Re-run nightly_tsir_parity_canary directly to see the "
                    "failing fixtures, regenerate, then pack again. Pass "
                    "--skip-canary-fingerprint only when the canary is known-"
                    "broken for unrelated reasons.\n"
                )
                sys.stderr.write(canary_proc.stdout)
                sys.stderr.write(canary_proc.stderr)
                return 2

    if args.out:
        out_path = resolve(args.out)
    else:
        out_path = default_out_path(commit, dirty)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    utc_built = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    host_os = detect_host_os()
    cs_py = detect_cs_python_availability()
    sdk_meta = detect_sdk_version_metadata()
    bundle_meta = {
        "schemaVersion": 1,
        "artifactKind": "doe_cerebras_evidence_bundle_meta",
        "builtUtc": utc_built,
        "archiveFilename": out_path.name,
        "gitCommit": commit,
        "gitShortSha": git_short_sha(commit),
        "gitDirtyTree": dirty,
        "hostOs": host_os,
        "csPython": cs_py,
        "sdkVersion": sdk_meta,
        "claimScopeSource": "docs/claim-discipline.md",
        "hardwareValidationAppendix": "docs/hardware-validation-appendix.md",
        "scope": (
            "Evidence + hashes + commands. NO SDK binaries, weight bytes, "
            "simulator logs, or raw trace data. See docs/claim-discipline.md "
            "for the allowed/rejected claim boundary this bundle evidences."
        ),
    }

    manifest_lines = [
        "Cerebras hardware-validation archive",
        f"Built: {utc_built}  commit: {git_short_sha(commit)}"
        + ("  (dirty tree)" if dirty else ""),
        "",
        "Scope: evidence + hashes + commands only. No SDK binaries, no weight",
        "bytes, no simulator logs. See docs/claim-discipline.md for the",
        "allowed/rejected claim boundary this archive evidences.",
        "",
        "Every file carries a claim-role indicating what it is evidence FOR.",
        "",
        f"{'SHA256':<64}  {'CLAIM-ROLE':<28}  PATH",
    ]

    included: list[tuple[str, bytes]] = []
    missing: list[str] = []
    excluded: list[tuple[str, str]] = []

    for entry in INCLUDE_FILES:
        if isinstance(entry, tuple):
            source_rel, archive_rel = entry
        else:
            source_rel = archive_rel = entry
        source_path, _section = split_section_source(source_rel)
        reason = should_exclude(source_path) or should_exclude(archive_rel)
        if reason:
            excluded.append((archive_rel, f"deny-list token: {reason}"))
            continue
        src = REPO_ROOT / source_path
        if not src.is_file():
            missing.append(source_rel)
            continue
        try:
            data = read_include_bytes(source_rel)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            missing.append(f"{source_rel} ({exc})")
            continue
        included.append((archive_rel, data))
        sha = sha256_bytes(data)
        role = CLAIM_ROLE.get(archive_rel, "UNLABELED")
        manifest_lines.append(f"{sha}  {role:<28}  {archive_rel}")

    if missing:
        manifest_lines.append("")
        manifest_lines.append("Missing at archive time (not fatal, recorded for transparency):")
        for m in missing:
            manifest_lines.append(f"  {m}")
    if excluded:
        manifest_lines.append("")
        manifest_lines.append("Explicitly excluded:")
        for path, reason in excluded:
            manifest_lines.append(f"  {path} ({reason})")

    manifest_text = "\n".join(manifest_lines) + "\n"
    bundle_meta_bytes = (
        json.dumps(bundle_meta, indent=2) + "\n"
    ).encode("utf-8")

    # Write the tarball. Every entry is normalized to mode 0o644, uid/gid 0,
    # mtime = now, owner "cerebras-ask" so the archive is reproducibly
    # structured and doesn't leak local uid info.
    now = int(time.time())
    owner = "cerebras-ask"

    def add_bytes(tf: tarfile.TarFile, name: str, data: bytes) -> None:
        ti = tarfile.TarInfo(name)
        ti.size = len(data)
        ti.mode = 0o644
        ti.mtime = now
        ti.uname = owner
        ti.gname = owner
        tf.addfile(ti, io.BytesIO(data))

    with tarfile.open(out_path, "w:gz") as tf:
        # Bundle metadata first — reviewers open this to know what the
        # bundle IS before deciding whether to read the manifest.
        add_bytes(tf, "BUNDLE_META.json", bundle_meta_bytes)
        # Manifest second — hash + claim-role + path for every file.
        add_bytes(tf, "MANIFEST.txt", manifest_text.encode("utf-8"))
        for relpath, data in included:
            add_bytes(tf, relpath, data)

    out_size = out_path.stat().st_size
    print(f"wrote {rel(out_path)}  ({out_size} bytes, {len(included)} files)")
    if missing:
        print(f"  missing: {len(missing)} file(s)")
        for m in missing:
            print(f"    {m}")
    if excluded:
        print(f"  excluded by deny-list: {len(excluded)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
