# Product-intent alignment

Starting commit: `528f65ee368feb78810a651fe47becb97881b4cd`.

Component: Doe, Zig runtime, doe-gpu, and documentation.
Intent: changed by making the user's product direction normative; existing
compiler/runtime authority and qualification requirements are preserved.
Boundary effects: ordinary execution is explicitly independent of evidence
tooling; compiler meaning, runtime execution, and offline improvement remain
separate. No executable behavior, API fields, schemas, packages, workloads,
oracles, thresholds, or support claims change.

## Requirement ownership

| Requested commitment | Canonical location |
| --- | --- |
| One portable product, ordinary provider first, optional reusable programs | `GOALS.md`, root `CATSCAN.md`, `packages/doe-gpu/CATSCAN.md` |
| Compiler meaning separated from execution and host adaptation | `INTENT.md`, `docs/architecture.md`, runtime and package charters |
| Immutable descriptions, device resources, invocation state, exact reuse identity, generations and transactional updates | `INTENT.md`, `docs/architecture.md`; existing `docs/reusable-compute-programs.md` retains API details |
| Timeout does not terminate GPU ownership | Root and Zig charters, `INTENT.md`, `runtime/zig/STYLE.md` |
| Compile-time completeness with independent behavioral evidence | `GOALS.md`, Zig charter, `docs/architecture.md`, existing style rules |
| Accurate optional diagnostics and offline frozen evaluation | `GOALS.md`, `docs/architecture.md`, `docs/process.md` |
| Numerical requirements, honest dependencies, allocation and platform promises | `GOALS.md`, `docs/thesis.md` |

Existing product-strategy configuration already declares ordinary substitution,
optional programs, independent evaluation, and separately qualified platforms.
Its fields and policy values are unchanged. Existing prepared-program API and
execution-mode limits remain in their canonical contract, not redefined here.

The former universal exact-numerical-results wording and receipt-ending ordinary
execution diagram were corrected. Command-oriented prepared-operation parity
still applies, without imposing that interpreter on native objects or package
programs. This is a statement of obligations, not proof that unfinished runtime
paths satisfy them.

## Acceptance evidence

Commands run from the repository root; inspect the retained logs for outcomes:

```sh
python3 bench/gates/catscan_gate.py --write-index
python3 -m unittest bench.tests.test_doc_link_coverage
python3 bench/gates/schema_gate.py
python3 runtime/zig/tools/review_log.py --write --base-ref 528f65ee368feb78810a651fe47becb97881b4cd
python3 runtime/zig/tools/review_log.py --check --base-ref 528f65ee368feb78810a651fe47becb97881b4cd
git diff --check
```

Logs: `charters.log`, `doc-links.log`, `schema.log`, `review.log`,
`whitespace.log`. No runtime or GPU tests are required to establish a prose-only
change, and none are claimed. Charter checks validate structure and references;
semantic correspondence was examined against the requested commitments above.

The canonical queue was regenerated. Shared-guidance changes invalidate earlier
fingerprints honestly; `log.json` remains byte-for-byte unchanged. No file review
credit is granted by this work. Next never-examined file:
`runtime/zig/src/backend/vulkan/vk_runtime_surface_ops.zig`. Resume the planned
batch there; stale scopes require examination of affected assumptions before
new review records can restore verified status.
