#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../.."
DOe_AUDIT_ROOT="$PWD/bench/out/maintenance/20260919-zig-common-audit"
ZIG_BIN="${ZIG_BIN:-/home/x/.local/zig/zig-x86_64-linux-0.15.2/zig}"
(
  cd runtime/zig
  "$ZIG_BIN" build doe-runtime -Doptimize=ReleaseFast --prefix "$DOe_AUDIT_ROOT/build" --summary all
)
"$DOe_AUDIT_ROOT/build/bin/doe-zig-runtime" \
  --commands "$DOe_AUDIT_ROOT/commands.json" \
  --kernel-root "$DOe_AUDIT_ROOT" \
  --vendor amd --api vulkan --backend native \
  --backend-lane vulkan_doe_comparable --quirk-mode off \
  --gpu-timestamp-mode off --execute --validate-output-oracles \
  --trace-jsonl "$DOe_AUDIT_ROOT/physical.trace.jsonl" \
  --trace-meta "$DOe_AUDIT_ROOT/physical.meta.json"
