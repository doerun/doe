# Doe product strategy contract

`config/doe-product-strategy.json` is the schema-validated projection of
[`thesis.md`](thesis.md), beneath the durable goals in [`GOALS.md`](../GOALS.md).
It is the machine-readable source for milestone order, the binding proving set,
and development-effectiveness recording. Status routes evidence; it does not
maintain another roadmap.

## Migration to independent compiler and runtime adoption

Schema version 6 and strategy version 5.0.0 explicitly distinguish independently
adoptable WGSL compilation and native WebGPU execution. Either may earn adoption
without the other; each requires separate evidence. `surfaces` adds `doecompiler`
as a primary surface with compiler-specific acceptance. This is an intended
adoption boundary, not a claim of a released standalone compiler package.

The existing ordered milestone IDs remain stable: ordinary application advantage,
independent framework integration, binding transfer, and optionally selected
Chromium integration. These are acceptance dependencies, not a requirement to
postpone correctness, packaging, or consumer discovery until a performance win.
The ONNX milestone now builds on established pinned execution, lifecycle checks,
and local isolated package acceptance. Broader compatibility, external deployment
reproduction, material replacement value, and retained use remain unestablished.
Start at the [installation guide](onnx-vulkan-installation.md) and
[delivery report](../reports/releases/20261009-onnx-vulkan-evaluation/README.md).

`executionOwnership.workSelection` replaces fixed percentage allocations and the
minimum application count with bounded batches, Vulkan focus, explicit Metal
handoff, deferred D3D12, and optional browser selection. Commercial emphasis is
independent installation, one real consumer requirement, and retained use.
Supported embedding, binaries, and maintenance remain commercial hypotheses;
payment is not a prerequisite for technical progress.

`comparisonLaw` now names the comparison classes and their measurement authority.
This is a prospective policy clarification, not a benchmark harness migration.
Existing workload schemas, checks, thresholds, and rejected results are unchanged.
A new campaign must implement any required contract/check extensions before
claiming application-level elimination. No runtime API or numerical behavior
changes. The prior schema migration and removed milestone IDs remain historical;
old receipts never acquire new meanings or promotion.

## Product roles

| Surface | Role | Acceptance |
| --- | --- | --- |
| WGSL compiler | Independently adoptable primary surface | Compilation latency, diagnostics, supported semantics, and generated-program performance; separate consumer adoption and retention |
| DoeRuntime | Independently adoptable primary surface | Resources, submission, completion, memory, and application integration; material advantage and retained independent adoption |
| DoeProof | Supporting feature | Independently qualifies incumbent and Doe without interfering with execution |
| Fawn | Retained experimental distribution | Optional browser route requiring explicit selection, native wins, transfer, and separate browser admission |
| DoeLab | Operating model | Turns retained failures into minimized regressions and qualified corrections |

A new compiler campaign needs a concrete opportunity. Independent compiler
adoption does not reopen closed browser optimization experiments.

## Comparison and adoption law

Freeze the strongest eligible incumbent, exact application/WGSL/inputs, independent
oracle, hardware and driver, fallback policy, application-level cache/preparation
conditions, timing scope, reliability
gates, and material threshold. Preserve I0, I1, W0, D0, and credible eligible P0
controls. A W0 qualification alone is feature value, not runtime adoption. D0
testing does not require a preceding paid DoeProof engagement.

Vulkan is the current engineering focus. Work proceeds in bounded batches.
Switching to Metal requires an explicit prioritization decision and handoff;
D3D12 remains deferred. Existing regression checks do not constitute parallel
optimization campaigns. A customer requirement informs selection without silently
changing this boundary. Each host and backend earns support independently. Distinguish unchanged provider
integration from a frozen declared-program treatment. Require parity, lifecycle
and recovery, raw measurements, an external
maintainer's adoption decision, and repeat retention. Payment, internal
benchmarks, compiler breadth, receipts, and Doppler interoperability cannot
substitute for these evidence fields; the schema enforces their presence.

For unchanged-application replacement, require equivalent application work,
outputs, validation, and complete boundaries; verified elimination of unnecessary
internal allocations, copies, submissions, or preparation can be the advantage.
Fixed-operation/shader experiments preserve the declared execution shape and
controls needed to isolate their treatment. Both follow
[the performance contract](performance-strategy.md#comparison-classes), with
no hidden fallback, omitted work, asymmetric warmup, or shifted costs.

The browser comparison policy preserves A/B/C/D causal meanings and separate
K0 eligibility. Its version 2 changes product priority, not comparison semantics.
Fawn's B-over-A result does not grant DoeRuntime C-over-B credit. D-over-C still
isolates Direct Protocol. Ineligible K0 work never becomes a Fawn win.
`doe-gpu/browser` is an incumbent wrapper until Doe occupies the Chromium seam.

## Evidence custody and current state

Customer content never crosses products by default. Customer-derived knowledge
requires explicit authorization; only sanitized failures or reproducible backend
defects enter shared learning under the declared custody rules.

The strategy records intended admission rules, not achieved support or adoption.
[`doe-support-matrix.md`](doe-support-matrix.md), `reports/claim-index.json`, and
Fawn milestone artifacts remain the evidence authorities. Reordered milestones
retain their unestablished or diagnostic assessments. No result is promoted by
this intent change.

Validate with:

```bash
python3 bench/gates/schema_gate.py
python3 bench/gates/catscan_gate.py
python3 -m unittest bench.tests.test_config_schemas bench.tests.test_browser_product_comparison_policy bench.tests.test_doc_link_coverage
```

The policy tests reject loss of the independent compiler role, implicit backend
expansion, missing comparison classes, and reordered acceptance milestones.
Historical evidence and numerical thresholds remain untouched. Schema and
component checks validate this strategy migration; GPU qualification is separate.

The operating objective now selects Doppler-driven Vulkan engineering. Existing
fields and ordered adoption milestones are unchanged: independent correctness
evidence does not require an external customer. The published ONNX evaluation
remains available while current-source generation correctness and dominant costs
guide the next implementation. This changes work selection, not historical verdicts.
