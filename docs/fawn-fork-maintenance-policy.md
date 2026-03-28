# Doe Chromium fork maintenance policy

Purpose:
- define how the Doe Chromium lane stays current on Chromium security updates while carrying the minimum Doe integration delta.

Scope:
- this document governs `browser/chromium` operational maintenance.
- it does not relax runtime or benchmark gate policy in `docs/process.md`.

## 1. Integration boundary

Doe-specific Chromium changes must stay isolated to explicit WebGPU runtime integration boundaries:
- runtime selector flags/boot wiring
- Doe library load path handling
- WebGPU runtime identity/diagnostic wiring
- branding/packaging assets

Goal:
- keep the Doe delta reviewable and rebase-conflict surface bounded.

## 2. Patch cadence and SLA

Security cadence targets:
1. Critical Chromium security updates:
- patch/rebase target within 72 hours.
2. High severity updates:
- patch/rebase target within 7 calendar days.
3. Regular stable updates:
- patch/rebase target per Chromium release cycle.

If SLA is missed:
- log deviation reason and recovery ETA in status tracking before next release artifact publication.

## 3. Rebase strategy

Preferred order:
1. fast-forward/cherry-pick security fixes when feasible.
2. full branch rebase for milestone synchronization.
3. resolve integration conflicts only in declared Doe-owned boundary files.

Non-goal:
- broad downstream divergence across unrelated Chromium subsystems.

## 4. Evidence required per Chromium update

Per update cut, record:
1. Chromium base revision and Doe lane revision.
2. security update class (critical/high/regular).
3. changed-file set inside Doe-owned boundary.
4. successful app launch proof artifact.
5. Doe runtime selection proof artifact (`chrome://version` command line or equivalent).

## 5. Release guardrails

Before shipping a patched Chromium lane build:
1. app bundle executable metadata must resolve correctly (`CFBundleExecutable`).
2. runtime flags must preserve Doe launch path in produced wrapper.
3. benchmark evidence claims must remain scoped to published artifact status.

## 6. Ownership model

Roles:
1. lane maintainer:
- rebases patchset and resolves integration boundary conflicts.
2. runtime maintainer:
- validates Doe runtime wiring and backend selection behavior.
3. release maintainer:
- validates packaging/signing/distribution and publishes update notes.

Minimum merge criteria:
- all three responsibilities explicitly acknowledged in release notes or checklist artifacts.
