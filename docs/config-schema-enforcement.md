# Config and schema enforcement

Runtime behavior, benchmark interpretation, support state, and claim state must
be explainable from versioned config, schema, and artifacts.

Required rules:

- runtime-visible fields have a schema or explicit migration;
- production behavior does not depend on undocumented environment variables or
  benchmark-only switches;
- fallback policy is declared and emits its original cause;
- removed fields and changed defaults carry migration notes;
- proof artifacts either discharge a named obligation or remain advisory;
- archives may preserve old shapes, but current producers must validate against
  current schemas.

The normative stage and gate order lives in [`process.md`](process.md).
Machine-owned tool boundaries live in `config/tool-surfaces.json`.

## Package comparability branch integration

The comparability contract adds package readback-mode, actual readback-scope,
and plan-identity obligations. Strict admission evaluates them alongside the
existing effective-path, shader identity, result-output and structural checks.
Submit-scope comparison groups equivalent command materialization and completion
work without changing selected timing. Each submit bucket uses its largest
reported component as a conservative materiality bound, since aggregate fields
overlap their subfields; these fractions are not additive cost accounting.
Regenerate the Lean contract after
editing the obligation registry; fixture version 2 includes the additional facts.

Trace metadata version 1 gains optional `packageReadbackActualPaths` and
`packageReadbackPathCounts` telemetry. Current package executors emit them;
strict readback-scope admission requires complete observations when applicable.
Historical receipts are preserved, and schema parseability does not establish
eligibility under the updated gate. The repo-only `mapAsync-host-copy` mode is
schema-declared and bypasses combined/native-copy helpers after mapping. Existing
readback selection policies keep their current modes; no production runtime or
package binding changes accompany this integration.

## Implementation peers and benchmark cube migration

`config/implementation-peers.json` introduces the canonical implementation-family
inventory and native provider IDs. Its schema is registered in the blocking
schema gate, which also validates local references and generated documentation.
Edit the registry and regenerate `docs/implementation-peers.md`; do not maintain
a parallel peer inventory in prose or Python.

Benchmark cube policy version 2 replaces the native provider list with
`sourceRegistryPath`. A provider-set entry must contain either that reference
or an explicit `providers` list; native membership must use the reference.
Package provider sets retain explicit membership because bindings describe
different integration surfaces. Cube consumers resolve the reference through
`bench.lib.implementation_peers.resolve_provider_sets`; `compare_axes` derives
native and direct-plan membership from the same registry. Existing profiles,
runtime selection, timing, evidence and claim rules are unchanged. No historical
benchmark receipt is migrated or requalified.

## Schema target registry migration

Registry version 2 preserves fixed `schema` targets and adds `schemasByKind`
for globs containing different report types. Each glob declares exactly one
selection form. The gate reads the report's explicit `kind`, requires a
registered mapping, then validates its complete body with that schema. Missing
or unknown kinds fail; directory suffixes do not establish report type.

The existing compute-program final-summary glob now routes matrices and package
qualification separately. Its scope is unchanged, preserving historical
observations rather than rewriting them to satisfy a different report contract.
Current accepted package and application summaries are registered explicitly.

## Native command storage policy migration

`native-command-storage-policy.json` introduces a build-time bound on an empty
host command array retained by each native device. `maxRetainedBytes` excludes
live encoder and command-buffer storage; zero restores release-on-close behavior.
Only storage allocated by the same allocator is reusable. Completed ownership
releases all resource leases before returning capacity, and final device release
frees retained capacity. No command, resource, prepared recording, public ABI, or
execution receipt is cached or changed by this policy. Rebuild the native binary
after changing the policy; compare complete operations and process memory before
adopting another bound.

## Zig review log introduction

`zig-review-log.schema.json` introduces versioned append-only review records for
files, directories, internal relationships, cross-directory relationships, and
system behavior. Each entry binds its source scope, reviewer, prerequisite
reviews, findings, additional inputs, and verification evidence. The generated
queue derives current coverage and invalidation; it does not own architecture
policy or convert old module decisions into completed code reviews. No runtime,
public API, or existing artifact field changes meaning.
