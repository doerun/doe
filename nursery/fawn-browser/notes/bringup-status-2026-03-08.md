# Bring-up status (2026-03-08)

## Summary

Track A browser evidence is now fresh on this host:

1. Doe and Dawn both pass the Playwright smoke harness.
2. The strict layered browser superset run now has zero required failures.
3. The browser-layered checker passes against the current 80-row projection manifest.

Track B remains contract-only:

1. no `fawn_2d_sdf_renderer` implementation exists,
2. no additional Track B module implementation exists,
3. no Track B artifact lane exists beyond draft contracts.

## What changed today

1. Refreshed `nursery/fawn-browser/bench/generated/browser_projection_manifest.json` to current workload hashes.
2. Fixed `texture_sample_raster` in `scripts/webgpu-playwright-layered-bench.mjs` to use the same deterministic render-target readback model as the passing raster scenario.
3. Updated browser path resolution in nursery wrappers so they prefer:
   - `nursery/chromium_webgpu_lane/out/fawn_release_local`
   - `~/Applications/Fawn.app`
4. Confirmed the lane-local `Fawn.app` previously failed because it wrapped a placeholder `Chromium-real` shell script instead of a real executable. The working host app bundle has a real Mach-O `Chromium-real`.

## Fresh artifacts

### Smoke

Artifact:

- `nursery/fawn-browser/artifacts/20260308T212412Z/dawn-vs-doe.tracka.playwright-smoke.diagnostic.json`

Result:

1. Dawn: pass
2. Doe: pass
3. Classification remains diagnostic by contract.

### Strict layered superset

Artifacts:

1. `nursery/fawn-browser/artifacts/20260308T212237Z/dawn-vs-doe.tracka.browser-layered.superset.diagnostic.json`
2. `nursery/fawn-browser/artifacts/20260308T212237Z/dawn-vs-doe.tracka.browser-layered.superset.summary.json`
3. `nursery/fawn-browser/artifacts/20260308T212237Z/dawn-vs-doe.tracka.browser-layered.superset.check.json`

Result:

1. `requiredL1Failed=0` for Dawn
2. `requiredL1Failed=0` for Doe
3. `requiredL2Failed=0` for Dawn
4. `requiredL2Failed=0` for Doe
5. Checker result: `ok=true`
6. Classification remains:
   - `comparisonStatus=diagnostic`
   - `claimStatus=diagnostic`

## Current blockers

### Track A

1. Chromium seam edits still live in the lane checkout and are not promoted into core governed directories.
2. Browser evidence is fresh, but it is still nursery-local and diagnostic.
3. CTS/browser-suite artifacts are still not wired as required milestone evidence.
4. No browser claim lane is defined; release-claim gating is not satisfied.

### Track B

1. All Track B modules remain contracts only.
2. No schema-backed implementation artifacts exist for M4 or M5.
3. No promotion-ready ownership or rollout exists for M6.

## Conclusion

1. M1 is locally validated on this host.
2. M2 has fresh local browser evidence with zero required failures.
3. M3 has fresh local diagnostic evidence only.
4. M4-M6 are not executable work items yet because the underlying Track B code does not exist.
