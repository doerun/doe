# Vulkan and port examination batch

Component: Zig backend ports and Vulkan command runtime
Intent: preserved
Acceptance evidence: `acceptance.log`, `focused-lower.log`, `focused-upper.log`, `abi.log`, `schema.log`, `doc-links.log` and the source-bound file reviews in this directory.
Boundary effects: command input admission, native allocation publication, compute/indirect visibility and graphics entrypoint/color-mask conversion. No component authority moved; no public ABI or serialized field was added.

## Scope and continuation

The fixed starting commit is in `base-commit.txt`. `file-reviews.json` lists each
fully examined file, its responsibility, outcome, resolved and unresolved
findings, semantic dependencies and next action. The canonical append-only review
ledger owns history; this artifact retains the batch explanation. The generated
`runtime/zig/reviews/queue.tsv` owns current coverage. Supporting test, generator
and architecture-metadata edits receive no additional file-review credit.

The batch begins at `src/backend/ports/telemetry.zig`, includes the transfer port,
and examines the Vulkan files through `vk_runtime_probe_ops.zig` in queue order.
The next never-examined file is `src/backend/vulkan/vk_runtime_surface_ops.zig`.
No directory, within-directory, cross-directory or system scope was completed.

## Repairs and unchanged responsibilities

Command write sizing uses checked addition before device/resource acquisition.
Indirect argument writes validate native allocation capacity before modifying
mapped bytes. Deferred command allocation reserves host ownership capacity before
acquiring a native command buffer, so allocation failure cannot lose the handle.
Whole-buffer descriptors reject empty tails as well as overflowing explicit ranges.

Compute visibility keeps indirect-only dependencies separate from subsequent
shader consumption. Incomplete current binding tracking forces the conservative
barrier. A global compute/transfer barrier covers compute and indirect consumers
before discharging the shared hazard state. The obsolete individual hazard-removal
helper was deleted. This follows the destination-stage/access scope specified by
[Khronos](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdPipelineBarrier.html).
The descriptor boundary follows the nonempty range requirements for
[VkDescriptorBufferInfo](https://docs.vulkan.org/refpages/latest/refpages/source/VkDescriptorBufferInfo.html).

Graphics entrypoints are allocator-owned sentinel strings, preserving the full
requested name; empty or embedded-NUL names and allocation failure remain errors.
The caller releases those names after pipeline creation. A zero color-write mask
preserves disabled writes instead of substituting all channels. Diagnostic texture
format conversion now preserves rejection instead of substituting RGBA8.

The small ports, artifact adapter, ABI declarations, descriptor identity,
format mapping, memory selector and canonical metrics alias retain their existing
owners. Their conclusions do not qualify every upstream capability or downstream
execution path. Passing checks are evidence for exercised cases, not certification
of the complete Vulkan backend.

## Contract and process impact

These are repairs to existing validation, ownership, synchronization and render
semantics, with no new policy knobs, trace fields, schemas or acceptance thresholds.
The test inventory remains schema version 2 and generated roots were regenerated
with its canonical tool. Source-layout decisions were re-examined for edited
modules, preserving their owner/layer and explicitly retaining unfinished findings.
No shared style/process rule was changed to make a review current.

`docs/process.md` continues to require schema, correctness, trace and verification
gates. Existing declared invalid inputs now fail at the affected admission boundary;
valid long entrypoints and disabled color writes keep their requested meanings.
No accepted package, workload, reference output, calibration procedure, comparator,
release artifact or performance claim was changed. Broader timing/count defects
remain open rather than being presented as improvements in this batch.

## Verification and reproduction

Use the pinned Zig 0.15.2 toolchain from `runtime/zig`:

```bash
zig build test -Dtest-filter=Vulkan --summary all
zig build test -Dtest-filter=vulkan --summary all
zig build test test-core test-full test-wgsl doe-runtime -Doptimize=ReleaseFast --summary all
```

The uppercase focused run passed its selected tests but initially failed the
architecture gate because edited module-decision hashes were stale. That original
log remains intact; the subsequent lowercase and complete acceptance runs include
the refreshed, re-examined decisions. Logs own counts, skips and command results;
suite totals overlap and must not be added as independent tests.

`abi-probe.zig` is a retained independent comparison with the installed Khronos C
header, not another production registry. Copy it temporarily to
`runtime/zig/.review_abi_probe.zig`, run `zig test .review_abi_probe.zig -lc
-I/usr/include`, then remove that temporary copy. The probe checks exported
capability struct sizes, alignments, offsets and field sizes, plus matching numeric
Vulkan/format constants. `host.json` binds the local header and toolchain identity.
It does not establish ABI compatibility on every target architecture.

From the repository root:

```bash
python3 runtime/zig/tools/generate_test_suites.py --check
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref 227b672751c3fba93afa686c996d642f545be8c3
python3 runtime/zig/tools/review_log.py --check --base-ref 227b672751c3fba93afa686c996d642f545be8c3
```

The native Vulkan tests exercise their existing descriptor/program fixtures on
this Linux host; host recording tests establish admission and lifetime bookkeeping.
No new physical graphics proof, stalled-device qualification, Apple/Windows
qualification or performance calibration was executed.

## Consequential open work

The per-file artifact supplies exact symbols and next actions. The shared repair
priorities are:

- Queue completion must own submitted resources before waits can fail. Program,
  probe, render and temporary-copy cleanup must not free unknown work.
- Inline render index data needs an owner through submission; shared indirect
  argument data must not be overwritten before prior use retires.
- Device limits and feature claims must describe enabled, supported behavior.
  Native maxima cannot be raised to WebGPU minima, and hardware alignment cannot
  be weakened. Diagnostic names need actual feature semantics and output checks.
- Graphics layout/attachment admission must reject invalid or missing resources
  before encoding, preserve complete binding identity and propagate bundle errors.
- Cache retention needs an explicit total capacity/full policy, and persistent
  writers need independent temporary-file ownership and meaningful reload evidence.
- Submission counts must come from submissions; timing phases must not double-count
  the same interval. Those measurement repairs precede any renewed performance claim.

Continue the queue without granting these files verification from unrelated passing
tests. The existing Metal liveness and physical-qualification findings remain open.
