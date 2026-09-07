# Async pipeline and Node worker ownership

This correction preserves the existing compiler arithmetic and public program
contracts. It repairs deferred request ownership, callback leases, addon
initialization and independent-device concurrency on Linux AMD Vulkan.

## Failure and correction

`reproduce.c` invokes the public async render-pipeline API, immediately releases
its callback result, and checks final device cleanup. The original native binary
from `../20260907-multi-dot-qualified/summary.json` crashes after that callback
in `original-retained-cleanup.log`. The Debug reproduction additionally exposes
retained DRM descriptors in `original-debug-cleanup.log`. These are failure
records, not passing qualification.

The corrected async requests retain strings, constant keys and values, vertex
attributes, blend and depth state, and native resources until completion.
Allocation failure unwinds through the request's allocator. Exact descriptor
comparison protects hash lookup; every callback gets an independent pipeline
reference. Failed worker initialization releases partially acquired storage and
threads. Fake creation markers no longer populate a separate pipeline cache.

Concurrent package work exposed native-library reload while another Node worker
used its function pointers. A stronger native-direct test also exposed shared
JavaScript references and device callback registration. The corrected addon
keeps its loaded library stable, owns JavaScript state per N-API environment,
and unregisters native callbacks before environment finalization. Native device
callback registration replaces or removes existing entries under its registry
lock. Notification detaches before invoking user code. Intermediate diagnostic
logs preserve the sequence; only final retained-package results qualify the fix.

## Final evidence

- `concurrency-tests-debug.log` and `concurrency-release-build-tests.log`: canonical
  Zig regressions, allocation failures, exact request identity, callback leases,
  worker-start rollback and device callback replacement/concurrency/reentry.
- `../20260907-concurrent-qualified/summary.json`: the same retained archives
  installed with scripts in clean Node, Bun and Electron main-process projects.
  Node additionally checks ordinary and recorded programs, native-direct copying,
  recreated worker environments, and a surviving parent device.
- `retained-native-c.log`: the canonical `runtime/zig/tests/native_async_pipeline.c`
  linked against the native library extracted from those archives. It exercises
  invalid descriptors, callback release, caller teardown and final DRM cleanup
  with Khronos validation and synchronization checking active.
- `library-selection.mjs` and `library-selection.log`: failed-load retry, loaded
  library aliases, conflicting-build rejection and surviving instance release.
- `package-independent-verification.log`: retained schema and artifact hashes,
  archive members, staged binary equality, and host native-library identities.
- `../../external-projects/doppler/20260907-concurrent-p0-qualified/result.json`:
  canonical Electron model acceptance using these packages and explicit P0.
  Its independent verifier recomputes the unchanged oracle and native identities.
- `../20260907-concurrent-applications/summary.json` and
  `application-verification.log`: frozen applications with accepted outputs,
  complete useful-operation measurements and structural execution checks.
- `tooling-tests.log`: package identity and documentation-link regressions.

The failed candidate at `../20260907-async-pipeline-qualified/summary.json` remains
failed. It is not interchangeable with the final qualified archives. The initial
qualifier omitted subprocess output on timeout; the corrected runner retains it.

## Reproduction

From the repository root, build the addon with
`node packages/doe-gpu/scripts/build-addon.js`, then run `zig build test-full`
and `zig build -Doptimize=ReleaseFast` from `runtime/zig`. Stage using the platform
package's existing `stage` script. Run `python3 bench/cli.py program qualify-package
--help` for controlled-host selection and a fresh output directory. Use a
disk-backed `TMPDIR` when the host's temporary filesystem lacks capacity.

Extract `package/bin/libwebgpu_doe.so` from the retained platform archive to an
empty directory. Compile the canonical C fixture with `cc -std=c11 -Wall -Wextra
-Werror -I runtime/zig/vendor/webgpu-headers runtime/zig/tests/native_async_pipeline.c
-L <extracted-directory> -Wl,-rpath,<absolute-extracted-directory> -lwebgpu_doe
-o <executable>`. Run with the Khronos validation layer enabled and reject any
validation error or synchronization hazard, regardless of process exit status.

Recheck the matrix with `python3 bench/cli.py program verify
bench/out/compute-program/20260907-concurrent-applications/summary.json --policy
bench/out/compute-program/20260907-concurrent-applications/policy.json`.
`baseline.txt`, `source.patch`, source snapshots and `SHA256SUMS` bind this change.
Generated installed packages and build trees are not retained evidence.

## Scope

These checks do not qualify shared-device mutation, arbitrary worker termination
with live GPU work, physical driver failure, general object garbage collection,
or peak GPU residency. Sampled resource observations and explicit device
teardown retain their existing scope. Metal and D3D12 physical testing remain
excluded. Application rows remain diagnostic; suspicious Deno ratios and
incumbent tail losses do not establish performance leadership.

Component: native runtime, N-API bridge, retained-package qualification
Intent: preserved
Acceptance evidence: canonical Zig tests, public C fixture, retained host/model/application artifacts above
Boundary effects: environment-owned bridge state; existing package and report contracts preserved
