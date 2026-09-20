# Metal sampler repair and resource-port checkpoint

Batch base: `5e0e4dd969ea88bc3755e268a193f6c6b5c0fb59`.
The base is available on `origin/main`; the preceding
[Metal examination](../20260920-zig-metal-ports-audit/README.md) and its original
base, findings and acceptance logs remain intact. This checkpoint prioritizes a
shared wrong-output defect while continuing the next file examination.

## Repair and responsibility

The Metal sampler bridge owns canonical WebGPU filter, address and comparison
translation. Both command execution and ordinary native sampler creation now
consume that entrypoint. Sampler cache identity includes comparison mode and a
nonempty cache rejects a different device owner. Native construction uses a
call-local descriptor instead of process-global mutable state. Invalid enum,
LOD and anisotropy inputs fail before native creation; failed native acquisition
still propagates through the callers' existing failure channel.

The old bridge symbol retains its documented private numeric vocabulary for
compatibility, sharing only the native descriptor factory. Product callers use
the canonical entrypoint. No public descriptor field, schema version, backend
choice or charter boundary changes. This repairs existing sampler semantics and
introduces no fallback execution. Internal bridge declarations, header, stubs and
symbol manifest change together. Accepted packages and performance thresholds
are unchanged. Existing correctness gates in `docs/process.md` remain applicable.

[File examinations](file-reviews.md) distinguish the new resource-port review
from re-examination of sampler ownership and resource commands. Supporting native
and bridge edits grant no additional complete-file credit. The port now states
borrowing, resource ownership and return/completion boundaries. Its review retains
implementation findings for texture admission and truthful submission receipts.
[Open-finding triage](triage.tsv) names the responsible owners and next checks
across the preceding batch instead of reopening an architecture redesign.

## Reproduction and retained evidence

Run from the repository root with pinned Zig on PATH:

```bash
python3 bench/out/maintenance/20260920-zig-metal-sampler-resource/sampler_translation_probe.py
(cd runtime/zig && zig build test --summary all)
(cd runtime/zig && zig build test-core -Doptimize=ReleaseFast --summary all)
(cd runtime/zig && zig build test -Dtest-filter='Metal repair proof' --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref 5e0e4dd969ea88bc3755e268a193f6c6b5c0fb59
python3 runtime/zig/tools/review_log.py --check --base-ref 5e0e4dd969ea88bc3755e268a193f6c6b5c0fb59
```

- [predecessor-translation.log](predecessor-translation.log) records the failing
  checkpoint translation; [current-translation.log](current-translation.log)
  records corrected translation and input admission. The retained C sources
  contain extracted production functions, not a reimplementation. Symbolic native
  enums and a recording factory isolate translation; they do not execute Metal.
- [sampler-host.log](sampler-host.log) exercises comparison identity, device
  separation, acquisition failure, overflow, cache saturation, eviction, uncached
  ownership and teardown through a recording bridge.
- [aggregate-acceptance.log](aggregate-acceptance.log) and
  [core-release-fast-acceptance.log](core-release-fast-acceptance.log) contain final
  host suites plus format, import/source architecture, ABI, bridge-manifest and
  test-inventory gates. Inline and physical tests are explicitly inventoried.
- [physical-availability.log](physical-availability.log) records explicit skips
  on Linux. [The bounded physical plan](physical-validation.md) names executable
  ordering/transfer/teardown checks, independent expected outputs, and remaining
  early GPU-object release, real sampler-output and concurrent-device cases.
- [schema.log](schema.log) and [doc-links.log](doc-links.log) retain repository
  contract and documentation-link checks.

The Linux host has no physical Metal execution evidence. Apple SDK compilation,
real sampling outputs and native retirement qualification remain open. Host
allocation failure and recording tests are distinct from those checks. No speed
or release-readiness claim follows from this checkpoint.

## Continuation

Prioritize texture footprint admission and checked native completion before
another broad examination batch. Keep `metal_deferred_release.zig`,
`metal_resource_commands.zig` and the resource-port implementation review open
for their explicit remaining findings. The next never-examined file is
`runtime/zig/src/backend/ports/spatial.zig`. Do not mass-refresh other stale
reviews merely because supporting bridge bytes changed.

Component: Metal sampler translation/cache, native sampler adapter and resource port.
Intent: preserved.
Acceptance evidence: commands and hash-bound artifacts above.
Boundary effects: internal sampler ABI, cache identity, descriptor ownership,
resource-port contract documentation, test inventory and review history; no
public schema or authority change.
