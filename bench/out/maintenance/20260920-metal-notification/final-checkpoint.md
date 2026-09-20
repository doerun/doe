# Final Metal notification checkpoint

Component: Zig Metal command runtime
Intent: preserved
Acceptance evidence: [final canonical run](acceptance-final.log), [focused Debug run](focused-accepted.log), [schema gate](schema.log), [documentation links](doc-links.log), and [Apple host availability](physical-availability.log).
Boundary effects: private bridge notifications and command-provider wait controls; supporting kernel/presentation submission adapters. No package release or ordinary native callback qualification.

The [batch record](README.md) explains the proposal integration, examined scopes,
regressions, schema migration and remaining findings. Its evidence stays intact.
During final diff examination, the immediate barrier's reported duration was
restored to cover the complete flush, including cleanup and error checks, rather
than returning only the flush's inner submission interval. The retirement budget
still belongs to exactly one pass. No timing field or operation boundary changes.

`acceptance-final.log` runs aggregate, core, full and WGSL suites plus the Linux
runtime after that correction. Earlier `acceptance.log` belongs to the earlier
working-tree version. The final appended ledger entries supersede the initial
batch records and bind the corrected queue source plus this final run; history
and earlier evidence are not rewritten. Structural decision metadata refreshes
only the reviewed affected source owners and grants no file-review status.

The examination batch covers completion, queue operations and command dispatch.
All retain `needs_changes`: blocking/reentrant destruction, remaining void
encoder boundaries, aggregate retention, broad dispatch context and unavailable
Apple/Metal acceptance remain concrete obligations. Host checks establish the
exercised ownership and policy behavior, not hardware qualification.

Next physical work: compile the changed bridge with Apple SDK/ARC/blocks and run
the existing repair proof fixtures, including timeout under both modes, late
completion, independent readback guards, native failure and early release. Use
an isolated build and retain accepted packages. Next never-examined queue file:
`runtime/zig/src/backend/ports/telemetry.zig`.
