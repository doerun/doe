# Doe Support Matrix

## Purpose

This document defines explicit capability tiers for Doe with hard contracts per tier.

Every tier has: a deployment surface, a supported API set, required gates, conformance requirements, SLA/support commitments, and allowed marketing claims. Claims that exceed a tier's contract are disallowed regardless of directional evidence.

Tier names are tied to deployment surface and guarantees, not vague quality labels.

## Tiers

| Tier | Deployment Surface | Buyer |
|------|-------------------|-------|
| **doe-core** | Node/Bun/CLI headless | AI/ML infra, CI/perf teams |
| **doe-runtime** | Native apps, engines, embedded | Teams replacing Dawn/wgpu in applications |
| **fawn-browser** | Managed Chromium distribution | Enterprise/regulated browser deployments |

Each tier is additive: doe-runtime includes all doe-core commitments; fawn-browser includes all doe-runtime commitments.

---

## Tier 1: doe-core

### Scope

Headless compute, benchmarking, and evidence infrastructure via Node/Bun/CLI.

### Deployment Surface

- `@fawn/webgpu-node` (Node runtime, Bun FFI)
- `doe-zig-runtime` CLI binary
- `libdoe_webgpu.{dylib,so,dll}` via FFI (compute-focused paths)

### Supported API

From `@fawn/webgpu-node` API contract v1:

| API | Status | Notes |
|-----|--------|-------|
| `create(createArgs?)` | Required | Returns provider-backed GPU object with `requestAdapter` |
| `globals` | Required | Provider globals for `globalThis` bootstrap |
| `setupGlobals(target?, createArgs?)` | Required | Installs `navigator.gpu` + enum bootstrap |
| `requestAdapter(adapterOptions?, createArgs?)` | Required | Returns `Promise<GPUAdapter \| null>` when provider supports in-process adapter callbacks |
| `requestDevice(options?)` | Required | Returns `Promise<GPUDevice>` when provider supports in-process adapter/device callbacks |
| `createDoeRuntime(options?)` | Required | CLI orchestration: `runRaw`, `runBench` |
| `runDawnVsDoeCompare(options)` | Required | Wraps `bench/compare_dawn_vs_doe.py` |
| `providerInfo()` | Required | Module/load diagnostics |

CLI tools:

| Tool | Status |
|------|--------|
| `fawn-webgpu-bench` | Required |
| `fawn-webgpu-compare` | Required |

### Not Supported

- Full browser-parity `navigator.gpu` object model emulation
- Full WebGPU enum surface (only constants required by real integrations)
- `GPUCanvasContext`, presentation/swapchain APIs
- Full object lifetime/event parity (`device lost` events, full error scopes, full mapping semantics)
- npm `webgpu` drop-in compatibility guarantee for arbitrary packages
- Doe-native Bun FFI callback trampoline for `wgpuInstanceRequestAdapter`/`wgpuAdapterRequestDevice` (in progress)

### Required Gates

| Gate | Mode | Script |
|------|------|--------|
| Schema | Blocking | `bench/schema_gate.py` |
| Correctness | Blocking | `bench/check_correctness.py` |
| Trace/replay | Blocking | `bench/trace_gate.py` |
| Comparability | Blocking | `bench/compare_dawn_vs_doe.py --strict` |
| Claim | Blocking for claim artifacts | `bench/claim_gate.py` |
| Performance | Advisory | `gates.json` ratchet |

### Conformance Requirements

- No CTS publication requirement.
- Correctness is validated by internal trace replay and comparability gates, not external CTS.
- Behavioral correctness for supported operations (buffer upload, copy, barrier, dispatch, render) must pass internal gate suite.

### SLA / Support Commitments

- Artifact reproducibility: any published benchmark artifact must be reproducible from the same inputs, config, and runtime version.
- Gate stability: blocking gates must not regress (pass→fail) without a tracked config or code change.
- API stability: `@fawn/webgpu-node` API contract v1 surface is stable; breaking changes require version bump.
- No uptime/availability SLA (headless tooling, not a service).

### Allowed Marketing Claims

| Claim | Allowed | Condition |
|-------|---------|-----------|
| "Strict apples-to-apples Dawn comparison on [N] workloads" | Yes | Cite artifact path, `comparisonStatus=comparable`, `claimStatus=claimable` |
| "Deterministic trace and replay for GPU workloads" | Yes | Trace gate passes |
| "Hash-linked benchmark artifacts" | Yes | Artifacts conform to trace-meta schema |
| "Faster than Dawn on [specific workloads]" | Yes | Per claim discipline rules (artifact, workload set, backend, timing class, claimStatus) |
| "Dawn replacement" | No | Requires doe-runtime tier |
| "Production WebGPU runtime" | No | Requires doe-runtime tier |
| "Conformant WebGPU implementation" | No | Requires doe-runtime tier with CTS publication |

---

## Tier 2: doe-runtime

### Scope

Drop-in native WebGPU runtime for applications, engines, and embedded systems. Replaces Dawn or wgpu as the `webgpu.h` provider.

### Deployment Surface

- `libdoe_webgpu.so` / `libdoe_webgpu.dylib` as shared library
- Static linking for embedded targets
- All doe-core surfaces (Node/Bun/CLI)

### Supported API

All of doe-core, plus:

| API | Status | Notes |
|-----|--------|-------|
| `webgpu.h` ABI | Required | Full symbol set verified by `dropin_gate.py` |
| `wgpuCreateInstance` | Required | Via shared library export |
| `wgpuInstanceRequestAdapter` | Required | Callback-based per `webgpu.h` spec |
| `wgpuAdapterRequestDevice` | Required | Callback-based per `webgpu.h` spec |
| Buffer operations | Required | Create, map, unmap, write, copy |
| Texture operations | Required | Create, write, copy, view |
| Render pipeline | Required | Create, bind, draw, draw indexed |
| Compute pipeline | Required | Create, bind, dispatch |
| Command encoding | Required | Full `GPUCommandEncoder` surface |
| Queue operations | Required | Submit, writeBuffer, writeTexture, onSubmittedWorkDone |

### Expanded Scope vs doe-core

| Capability | doe-core | doe-runtime |
|-----------|----------|-------------|
| `webgpu.h` ABI completeness | Partial (compute paths) | Full (verified by gate) |
| Render pipeline | Not required | Required |
| Texture operations | Not required | Required |
| Presentation/swapchain | Not required | Required only for windowed/browser-integrated targets |
| Error scopes | Not required | Required |
| Device lost events | Not required | Required |
| Shader module creation | Via CLI | In-process via `webgpu.h` |

### Not Supported

- Browser-specific presentation integration (swapchain is native-window, not `GPUCanvasContext`)
- Chromium GPU process integration
- Browser security sandbox enforcement (that is fawn-browser)

### Required Gates

All doe-core gates, plus:

| Gate | Mode | Script |
|------|------|--------|
| Drop-in ABI | Blocking | `bench/dropin_gate.py` |
| CTS subset | Blocking | Target: selected CTS subset at published pass rate |
| Backend selection | Blocking | `run_blocking_gates.py --with-backend-selection-gate` |
| Sync conformance | Blocking per backend | Metal: `--with-metal-sync-conformance-gate`; Vulkan: `--with-vulkan-sync-conformance-gate` |
| Timing policy | Blocking per backend | Metal: `--with-metal-timing-policy-gate`; Vulkan: `--with-vulkan-timing-policy-gate` |
| Shader artifact | Blocking | `--with-shader-artifact-gate` |

### Conformance Requirements

- **CTS subset publication required.** Select a meaningful CTS subset covering implemented operations. Publish pass/fail counts per backend per release. Track trend.
- **Minimum pass rate target:** To be established after first CTS run. Initial publication of any number (even low) is required; trend direction matters more than absolute value.
- **Regression policy:** CTS pass rate must not regress between releases. Any regression blocks release until fixed or explicitly waived with tracking in `status.md`.

### SLA / Support Commitments

All doe-core commitments, plus:

- ABI stability: `webgpu.h` symbol set does not break between minor versions. Symbol additions are non-breaking; symbol removal or signature change requires major version bump.
- Binary artifact availability: stripped shared library published per release, per backend (Metal, Vulkan), per target (macOS arm64, Linux x86_64, etc.).
- Binary size and build time: published per release, compared against Dawn baseline.
- Conformance trend: CTS subset results published per release.
- Bug response: issues with reproducible trace artifacts get priority triage.

### Allowed Marketing Claims

All doe-core claims, plus:

| Claim | Allowed | Condition |
|-------|---------|-----------|
| "Drop-in Dawn/wgpu replacement" | Yes | `dropin_gate.py` passes, CTS subset published |
| "Lighter than Dawn" | Yes | Only with published binary size + build time + dependency count comparison |
| "Conformance-tracked WebGPU runtime" | Yes | CTS subset results published |
| "Production WebGPU runtime" | Yes | All blocking gates green, CTS published, at least one external consumer validated |
| "Full WebGPU implementation" | No | Until CTS pass rate exceeds threshold (TBD) |
| "Browser-ready" | No | Requires fawn-browser tier |
| "Formally verified" | No | Until Lean proof pipeline is operational in CI with specific scope documented |

---

## Tier 3: fawn-browser

### Scope

Managed Chromium distribution with Doe as the WebGPU runtime. Deployable as an enterprise/regulated browser product.

### Deployment Surface

- Chromium fork binary (macOS, Linux, Windows)
- Doe integrated as `--use-webgpu-runtime=doe`
- All doe-runtime surfaces available via Chromium's GPU process

### Supported API

All of doe-runtime, plus:

| API | Status | Notes |
|-----|--------|-------|
| `navigator.gpu` | Required | Full browser WebGPU API via Doe backend |
| `GPUCanvasContext` | Required | Browser presentation integration |
| Chromium GPU process integration | Required | Doe runs in GPU process with sandbox |
| Chromium flags | Required | `--use-webgpu-runtime=doe`, `--disable-webgpu-doe`, `--doe-webgpu-library-path` |

### Expanded Scope vs doe-runtime

| Capability | doe-runtime | fawn-browser |
|-----------|-------------|--------------|
| Browser `navigator.gpu` | Not supported | Required |
| `GPUCanvasContext` / presentation | Native-window only | Browser tab integration |
| GPU process sandbox | Not applicable | Required |
| Security patch cadence | Not applicable | Required SLA |
| Upstream rebase | Not applicable | Required cadence |
| Rollback to Dawn | Manual (`force_dawn_oracle`) | Managed, policy-driven |

### Not Supported at Launch

- Full WebGPU spec conformance parity with Chrome/Dawn (may lag on edge cases)
- WebGPU extensions not in `webgpu.h` core
- WebCodecs GPU integration (future)

### Required Gates

All doe-runtime gates, plus:

| Gate | Mode | Script |
|------|------|--------|
| Cycle lock/rollback | Blocking | `bench/cycle_gate.py` |
| Cutover verification | Blocking per lane | `--with-local-metal-gates --local-metal-lane metal_app` |
| Claim rehearsal | Required for release claims | `bench/build_claim_rehearsal_artifacts.py` |
| Substantiation | Required for trend publication | `bench/run_release_claim_windows.py` |

### Conformance Requirements

All doe-runtime requirements, plus:

- **Expanded CTS coverage:** CTS subset must cover browser-visible API surface, not just compute/buffer operations.
- **Browser smoke tests:** Standard WebGPU samples (rotating cube, compute boids, deferred rendering) must render correctly in Fawn.
- **Regression gate:** No CTS regression and no browser smoke test regression between releases.

### Operational Commitments

| Commitment | Target | Notes |
|-----------|--------|-------|
| Security patch cadence | Within 72 hours of Chrome stable security update | GPU process CVEs prioritized |
| Upstream rebase cadence | Per Chrome major release (every 4 weeks) | Doe integration isolated to minimize conflict surface |
| Rollback policy | `force_dawn_oracle` available in `backend-runtime-policy.json` | Deterministic recovery to Dawn-oracle baseline |
| Diff size tracking | Published per release | Fawn-vs-upstream Chromium diff LOC tracked; growing diff requires justification |
| Release cadence | Monthly minimum, aligned with Chrome stable | Hotfix releases for security within SLA |

### Fork Maintenance Contracts

| Area | Contract |
|------|----------|
| Isolation boundary | Fawn modifies only: `third_party/dawn/` replacement surface, GPU process initialization/runtime selection, `webgpu.h` binding layer, and packaging/branding/launcher metadata required for distribution. All other Chromium code tracked upstream without modification. |
| Rebase strategy | Cherry-pick security patches immediately. Full rebase per Chrome major release. Merge conflicts in isolation boundary resolved by Fawn team; conflicts outside boundary indicate scope creep. |
| Diff ceiling | If Fawn-vs-upstream diff exceeds 50K LOC (excluding `third_party/dawn/` replacement), trigger architectural review to re-isolate. |
| Security audit | Doe runtime code in GPU process is in-scope for security review. Sandbox boundary behavior must match Dawn's guarantees or explicitly document deviations. |

### Allowed Marketing Claims

All doe-runtime claims, plus:

| Claim | Allowed | Condition |
|-------|---------|-----------|
| "Managed browser with controlled GPU behavior" | Yes | Operational commitments met, at least one release shipped |
| "Independent GPU runtime patching" | Yes | Demonstrated by shipping a Doe fix without waiting for Chrome release |
| "Auditable GPU behavior" | Yes | Trace/replay operational in browser context |
| "Enterprise-grade browser" | Yes | Security patch SLA demonstrated over 3+ release cycles |
| "Regulated/sovereign browser" | Yes | All operational commitments met + hash-linked artifact chain operational |
| "FedRAMP/HIPAA/IL4+ ready" | No | Until actual certification or compliance audit completed |
| "Formally verified browser" | No | Until Lean proof pipeline is operational with documented scope |

---

## Tier Progression

```
doe-core ──────────► doe-runtime ──────────► fawn-browser
  │                     │                       │
  │ Ship now            │ Ship when:            │ Ship when:
  │                     │ - requestAdapter FFI  │ - rebase cadence proven
  │ Headless compute    │   works in-process    │ - security SLA demonstrated
  │ + evidence infra    │ - CTS subset          │ - browser smoke tests pass
  │                     │   published           │ - operational commitments
  │                     │ - dropin gate green   │   documented and met
  │                     │ - binary size         │
  │                     │   measured            │
  │                     │                       │
  ▼                     ▼                       ▼
  CI/perf teams         Engine/embedded teams   Enterprise/regulated
  AI/ML infra           Dawn/wgpu replacers     Government/defense
  Doppler integration   Native app developers   Healthcare/finance
```

### Promotion Criteria

**doe-core → doe-runtime:**

1. `wgpuInstanceRequestAdapter` callback trampoline operational (Bun FFI or synchronous variant)
2. `dropin_gate.py` passes on full `webgpu.h` symbol set
3. First CTS subset run published with pass/fail counts
4. Binary size and build time comparison vs Dawn published
5. At least one external consumer validated (Doppler, game engine, or embedded integrator)

**doe-runtime → fawn-browser:**

1. All doe-runtime promotion criteria met
2. Chromium fork builds and boots with Doe as WebGPU runtime on at least one platform
3. Browser smoke tests (rotating cube, compute boids) render correctly
4. Security patch flow demonstrated: at least one Chrome security patch applied within 72-hour target
5. Rebase cadence demonstrated: at least one full Chrome major version rebase completed
6. Operational commitments documented in shipping artifacts (not just internal docs)
7. Rollback to Dawn-oracle validated end-to-end in browser context

---

## Claim Discipline by Tier

The claim discipline rules from the positioning report apply universally, but the *scope* of allowed claims differs by tier:

| Rule | doe-core | doe-runtime | fawn-browser |
|------|----------|-------------|--------------|
| Performance claims require artifact citation | Yes | Yes | Yes |
| No generalization beyond covered workloads | Yes | Yes | Yes |
| Regression blocks "faster" language | Yes | Yes | Yes |
| "Replacement" language allowed | No | Yes (with CTS) | Yes |
| "Production" language allowed | No | Yes (with gates) | Yes |
| "Enterprise/regulated" language allowed | No | No | Yes (with SLA) |
| "Conformant" language allowed | No | Yes (with CTS trend) | Yes |
| "Sovereign" language allowed | No | No | Yes (full stack) |

---

## Relationship to Doppler

Doppler is a consumer of Doe, not a tier of Doe. Doppler's tier requirements:

| Doppler Use Case | Minimum Doe Tier | Reason |
|-----------------|-----------------|--------|
| Browser inference on stock WebGPU | None (uses Dawn/wgpu via host browser) | Doe not involved |
| Headless inference via `DOPPLER_NODE_WEBGPU_MODULE` | doe-core | Needs `requestAdapter`/`requestDevice` in Node |
| Vertically integrated browser AI (Doppler + Fawn) | fawn-browser | Needs browser-integrated `navigator.gpu` on Doe |
| Sovereign AI stack (all three) | fawn-browser | Full stack requires all tiers |

Doppler can ship value today on stock WebGPU (no Doe dependency). The Doe integration path adds value incrementally as tiers mature.

---

## Current Status (2026-03-01)

| Tier | Status | Blocking Gaps |
|------|--------|--------------|
| doe-core | **Operational (CLI/process-bridge)** | CLI/process orchestration works; provider-module in-process path depends on provider callbacks; Doe-native Bun FFI adapter trampoline remains incomplete |
| doe-runtime | **Not yet shippable** | No CTS publication, no binary size measurements, `dropin_gate.py` needs validation on full symbol set |
| fawn-browser | **Not yet shippable** | No rebase cadence demonstrated, no security patch SLA, no browser smoke tests, operational commitments undocumented |
