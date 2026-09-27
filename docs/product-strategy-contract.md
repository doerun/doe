# Doe product strategy contract

`config/doe-product-strategy.json` is the schema-validated projection of
[`thesis.md`](thesis.md), beneath the durable goals in [`GOALS.md`](../GOALS.md).
It is the machine-readable source for milestone order, the binding proving set,
and development-effectiveness recording. Status routes evidence; it does not
maintain another roadmap.

## Migration to ordinary execution and independent integration

Schema version 5 and strategy version 4.0.0 replace the former sequence of
provider qualification, declared plans, agent-assisted applications, corrections,
and embedding expansion. The current order is ordinary execution, ONNX Runtime
substitution feasibility, binding application transfer, and bounded Chromium
integration toward browser replacement. The schema enforces milestone identity
and order. The new `provingSet` requires inference, general computation, and
interactive rendering; `developmentEffectiveness` records reproduction-to-verified-
improvement time using existing evidence rather than new infrastructure.

The retained provider milestone ID keeps its ordinary-execution meaning. Removed
milestone IDs remain readable in historical receipts; they must not be relabeled
as new achievements. Reuse, refactoring, and agent assistance become supporting
work. No runtime API or comparison law changes, and no evidence is promoted.
The separate ONNX plugin EP remains an experiment while the existing-provider
substitution seam is investigated. Browser destination does not imply browser
readiness or a requirement to ship a browser before native adoption.

## Product roles

| Surface | Role | Acceptance |
| --- | --- | --- |
| DoeRuntime | Primary product | Ordinary execution earns material application advantage; binding transfer and independent retained adoption follow |
| DoeProof | Supporting feature | Independently qualifies incumbent and DoeRuntime without interfering with execution |
| Fawn | Experimental distribution channel | Browser replacement destination; bounded Chromium integration follows independent native wins and binding transfer, with separate browser admission |
| DoeLab | Operating model | Turns retained failures into minimized regressions and qualified corrections |

## Comparison and adoption law

Freeze the strongest eligible incumbent, exact application/WGSL/inputs, independent
oracle, hardware and driver, fallback policy, cache state, timing scope, reliability
gates, and material threshold. Preserve I0, I1, W0, D0, and credible eligible P0
controls. A W0 qualification alone is feature value, not runtime adoption. D0
testing does not require a preceding paid DoeProof engagement.

Start with AMD/Vulkan unless a real customer supplies a stronger target.
Each host and backend earns support independently. Distinguish unchanged provider
integration from a frozen declared-program treatment. Require parity, lifecycle
and recovery, raw measurements, an external
maintainer's adoption decision, and repeat retention. Payment, internal
benchmarks, compiler breadth, receipts, and Doppler interoperability cannot
substitute for these evidence fields; the schema enforces their presence.

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

The config-schema test loader now treats JSON row arrays like the canonical
schema gate, validating each record rather than the collection as one object.
This repairs a pre-existing compiler-report check without changing its schema
or evidence. Positive checks cover every record; adversarial checks retain
the existing representative-record scope.

Validate with:

```bash
python3 bench/gates/schema_gate.py
python3 bench/gates/catscan_gate.py
python3 -m unittest bench.tests.test_config_schemas bench.tests.test_browser_product_comparison_policy bench.tests.test_doc_link_coverage
```

Component: Doe strategy, configuration, documentation, and integration guidance.
Intent: changed — ordered execution milestones replace reuse-first expansion.
Acceptance evidence: schema, CATSCAN, policy, and documentation checks above;
manual schema mutations reject reordered milestones, missing proving families,
and optional transfer.
Boundary effects: ONNX bridge work prioritizes existing-provider substitution;
compiler, backend, host API, comparison, and release-gate ownership are preserved.
No GPU experiment, integration prototype, or release qualification ran in this
strategy synchronization.
