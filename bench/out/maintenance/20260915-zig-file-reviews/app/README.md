# Application request and preparation reviews

Version-1 maintenance receipt for the complete `src/app/` file examinations,
followed by separate directory-organization and within-directory relationship
passes. The review ledger records each scope and its prerequisites independently.
This is source and CPU contract evidence; it does not qualify physical execution
or application performance.

## File examinations

| File | Responsibility and result |
| --- | --- |
| `mod.zig` | Existing facade exports the request, preparation, and execution entrypoints. Aliases remain direct and introduce no state, ownership, error conversion, or allocation. Source is unchanged. |
| `request.zig` | Application request alternatives now reuse the canonical dispatch and direct-write types. The duplicate compute payload could not represent the existing output oracle. Removed its separate defaults/field inventory and an unused import. |
| `prepare.zig` | Pure synchronous classification and identity assignment delegate to canonical command conversion and direct-write construction. This preserves the full request and does not acquire resource ownership or validate device limits. Removed the duplicate field mapping and unused import. |
| `runner.zig` | The exhaustive prepared-operation switch delegates to the matching typed port; specialized compute/transfer entrypoints preserve port errors and reports. There is no catch/fallback, allocation, retained state, or unsafe cast here. Removed an unused import. |

[Predecessor rejection](request-before.log) shows that the canonical dispatch
request could not enter the application API because it had a separate struct
type. The regression supplies the existing output oracle and nondefault dispatch
controls, then checks the entire prepared command. The transfer regression
checks destination capacity independently of write length, a nonzero offset,
pointer identity, and mutation visible through the synchronous borrowed view.
These tests do not evaluate the oracle numerically or exercise a GPU.

[The initial test fixture failure](request-fixture-error.log) used a nonexistent
oracle scope enum; the fixture was corrected to the existing `command_graph`
contract. That was a test-author error, not a runtime finding. The original
[application tests](tests-before.log) passed before the repair; the intermediate
[post-repair run](tests-after.log) preceded the borrowed-subrange test.

## Directory organization

The direct files belong together as the application-facing request facade,
canonical preparation adapters, and outbound-port routing. `mod.zig` exposes
these concerns without adding logic. `request.zig` names the existing convenience
request alternatives; it does not need another complete command taxonomy.
`prepare.zig` covers canonical commands for the other domains. `runner.zig`
routes those prepared domains without introducing a universal native object API.
There are no child directories or additional files needed for this responsibility.
Tests remain in the existing core suite, where mock ports and production
composition can be checked together. The small modules retain distinct existing
entrypoints; this change does not create new folders or utility modules.

## Relationships within the directory

The facade imports each leaf directly. Preparation consumes request aliases;
the runner consumes canonical prepared operations and named port contracts.
There is no internal import cycle or duplicate payload/default registry after
the repair. Compute conversion has one authority in `contracts/compute.zig`;
direct-write fields have one authority in `contracts/prepared_operation.zig`.
The application layer does not own allocations, caches, configuration, callbacks,
or native handles. Borrowed slices must remain alive through synchronous port
execution; work retained beyond that extent requires the existing owned snapshot.
Port context lifetime belongs to its enclosing backend/session owner.

The exhaustive routing switch preserves explicit alternatives. Preparation
selects a domain and computes identity through the existing contract; the
prepared type alone does not prove validation. Backend/device checks retain
their authority. Canonical conversions, backend adapters, session cleanup, and
native API lifetimes remain dependencies to examine in their own queue scopes;
this local relationship pass does not complete cross-directory review.

## Internal source migration

`app.ComputeRequest` is `contracts.compute.DispatchRequest`: replace
`kernel_source` with `kernel`. This is the existing kernel name/path contract,
not inline WGSL source support. Its existing `output_oracle` now survives app
preparation. `app.TransferRequest` is `prepared.DirectBufferWrite`: replace
`buffer_handle` with `handle` and `size_bytes` with `buffer_size`. Capacity is
independent of `data.len`. Repository callers were searched and migrated.

The runtime direct-write constructor and test provider harness change only the
field spellings; values, operation identity, receipts, and ownership retain their
meaning. These companion deltas are not full-file review credit for either
caller. Serialized command/trace schemas, native ABI, npm contract, policy
values, and accepted package inputs retain their prior definitions. No new
serialized field or schema version is introduced. Existing STYLE requirements
for canonical types, explicit ownership, imports, and exhaustive routing apply;
no additional global style rule is needed.

## Validation and reproduction

Use Zig 0.15.2 from `runtime/zig/`:

```bash
zig build test-core -Dtest-filter='hexagonal application layer' -j2 --summary all
zig build test -Dtest-filter='hexagonal application layer' -Doptimize=ReleaseFast -j2 --summary all
zig build test-core -Dtest-filter='production execution context' -j2 --summary all
zig build test-bench-metal-compute test-bench-metal-staged-write -j2 --summary all
zig build dropin -Dtier=full -Doptimize=ReleaseFast --prefix ../../bench/out/maintenance/app-reproduce/full -j2 --summary all
zig build doe-runtime -Doptimize=ReleaseFast --prefix ../../bench/out/maintenance/app-reproduce/runtime -j2 --summary all
```

[Debug payload/lifetime checks](tests-final.log),
[ReleaseFast aggregate checks](aggregate-release-tests.log), and
[production routing/observer checks](composition-tests.log) ran through the
registered suites. The composition check covers command and direct-write
routing, receipt observation, trace-only status, and a backend error result
using CPU mocks. It does not claim complete domain correctness.
[Metal consumer tests](metal-consumer-tests.log) recheck the unchanged reviewed
benchmark sources after their shared execution constructor migrated. Prior
Metal execution limitations remain: no Apple framework build or GPU run here.

[Full native library build](full-build.log) and
[runtime executable build](runtime-build.log) compile actual consumers into
isolated output prefixes. Installed bytes are identified in `binaries.tsv` and
remain reproducible local outputs. The builds do not replace accepted package
binaries and were not executed against physical hardware.

`source-before.tsv`, `source-files.tsv`, and `SHA256SUMS` bind predecessor,
reviewed inputs, and retained evidence. `accepted-inputs.tsv` confirms preserved
package binaries and storage policy. Documentation and structural checks retain
the authority of the existing process gates; trace/replay schema and physical
calibration procedures are unchanged.

## Component handoff

Component: Zig application requests, preparation, and port routing
Intent: preserved
Acceptance evidence: linked payload, borrowed-lifetime, composition, consumer,
structural checks and isolated native builds, with source/artifact hashes
Boundary effects: internal Zig request aliases and caller field migration;
existing command, trace, native ABI, policy, and retained-ownership contracts
retain their authority
