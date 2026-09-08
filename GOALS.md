# Doe goals

## Mission

DoeRuntime is the primary product in the `doe/` repository: the owned WGSL
compiler, GPU runtime, resources, synchronization, lifecycle, and native
backends. DoeProof is its provider-neutral qualification and evidence feature,
not a separate primary product. Fawn is an experimental distribution surface
for the same runtime, sequenced after demonstrated application wins.

Build the independent GPU compiler and runtime that makes useful computation
easy to create, cheap to repeat, and portable across supported hardware.
Doe makes GPU programs ordinary software: executable, inspectable, reusable,
and reproducible without requiring their authors to become GPU systems engineers.

## Value

Applications should be able to substitute a governed GPU provider beneath a
supported workload, preserve exact or tolerance-bounded results, reject hidden
fallback, diagnose the first failing boundary, and replay the execution. A
receipt is evidence for those properties; it is not itself correctness, trust,
or application value.

## Durable goals

1. **Governed local execution.** Support a deliberately bounded matrix of real
   application workloads on declared runtimes, platforms, adapters, drivers,
   and backends.
2. **Program-identity preservation.** Bind source and inputs through normalized
   representations, lowering policy, backend artifacts, command graphs,
   outputs, and receipts.
3. **Fail-closed control.** Make provider selection, unsupported capability,
   fallback, lifecycle, synchronization, and failure state explicit.
4. **Independent correctness.** Require a semantic oracle and declared
   exactness class before reliability or performance promotion.
5. **Application-earned ownership.** Own a runtime only where matched controls
   prove value beyond a pinned incumbent, Doe's evidence layer around that
   incumbent, or a bounded incumbent patch.
6. **Compounding operational knowledge.** Turn real failures into normalized
   contracts, minimized reproductions, permanent regressions, and maintained
   release gates.
7. **Bounded expansion.** Extend into browsers, accelerators, and formal
   verification only through separately admitted workloads and evidence.

## Immediate operating objective: ordinary execution, then safe reuse

Run one execution-ownership program. First demonstrate that a developer can
replace a Node application's WebGPU provider with a pinned `doe-gpu` package,
preserve its WGSL, inputs, tests, and application logic, gain a repeatable useful
improvement, and immediately revert. Ordinary compiler/runtime value must not
depend on a declared-program interface or bespoke application optimization.
The operating allocation and external portfolio bounds live in
`config/doe-product-strategy.json`.

Next demonstrate interactive editing/simulation with checked activation,
explicit state-reset approval, cancellation, cleanup, and reopening. Then
demonstrate agent-assisted acceleration of an unfamiliar numerical routine
against a researcher's fixed independent tests and resource limits. These
direct demonstrations share the same compiler/runtime. Freeze numerical
requirements, inputs, strongest eligible controls, complete-operation costs,
memory, lifecycle, and material application outcomes before optimization.
A passing internal demonstration is not adoption.

Framework maintainers, equipment manufacturers, and chip-platform teams are
subsequent distribution and improvement paths, not separate products. The
ordered target journeys are in `docs/thesis.md`; none declares an existing
customer or completed support. Hardware, operating systems, ARM packaging,
energy behavior, and non-GPU accelerators require separate qualification.

Compatibility through controlled Node, Bun, Electron, and native provider seams
remains the entry point. An optional reusable-program interface may replace
declared application orchestration. Provider substitution alone cannot remove
arbitrary JavaScript that the application continues executing. Keep these
integration modes separate in comparisons and adoption evidence.

Earn externally owned voluntary adoption and retention after the mechanism
transfers. Preserve I0, I1, W0, D0, and credible eligible P0 ownership controls;
freeze and disclose any declared-program integration. DoeProof qualifies
providers impartially. Preserve negative results and stop expansion when the
advantage does not survive independent repetition.

Browser construction, Flutter replacement, peer networks, distributed training,
and universal accelerator support are outside the first demonstration. Fawn
remains a separately gated possible distribution surface; its existing A/B/C/D
and K0 laws do not become prerequisites for independent runtime progress.

The independence test is binding: DoeRuntime must earn its first adoption
without Doppler. DoeProof remains usable around the strongest eligible incumbent
without requiring DoeRuntime. Supporting-feature value must not be counted as
runtime adoption, and collaborating products receive no provider preference.

## Authority

[`docs/thesis.md`](docs/thesis.md) owns current product strategy and adoption
sequence. [`CATSCAN.md`](CATSCAN.md) and its descendants own component
boundaries and invariants. Registries, tests, reports, and receipts own current
status. Neither current code nor narrative measurements override these
authorities.
