# Canonical Electron model qualification

`result.json` records the canonical runner's explicitly selected source-built
P0 control and the exact qualified Doe archives. `oracle.json` owns frozen
numerical and application acceptance. This closes the reproduced attention-loop
model discrepancy on the tested Linux AMD Vulkan host. It does not establish
model performance leadership, universal shader support, or another platform.

`preparation.json` binds the pinned upstream, installation, hardware and source
contracts. `package-admission/package-inputs/` retains the original qualified
archives and their evidence; generated installed-package directories are not
retained. Each lane's `native-identity.json` checks Electron's loaded shared
objects before execution and hashes the selected native library. The runner
rechecks its identity after execution. `independent-verification.log` records
archive/member checks, native and transcript hashes, and a separate recomputation
of the unchanged oracle from the retained model data.

P0 uses the previously retained canonical Electron owned-mapping patch. Its
source revision, exact patch, binary and provenance are bound in the model
contract and copied into the result. The oracle retains its historical W0 slot;
`comparisonBaseline: P0` identifies what actually ran. The unmodified npm W0
external-buffer failure remains retained in
`bench/out/compute-program/20260907-model-attention-repro/`. No control silently
falls back and no numerical tolerance, shader, model input or upstream source was
changed by this qualification work.

Reproduce from the repository root with a fresh run ID and output directory:

```sh
export TMPDIR=/path/to/disk-backed-temporary-directory
python3 bench/cli.py external prepare --actor doppler --harness gemma270m-electron --run-id <new-run-id> --offline
node bench/external-projects/doppler/run-gemma270m-electron.mjs \
  --run-id <new-run-id> \
  --upstream-root bench/out/external-projects/doppler/upstream \
  --preparation-receipt bench/out/external-projects/doppler/<new-run-id>/preparation.json \
  --out bench/out/external-projects/doppler/<new-run-id>/result.json \
  --incumbent P0 \
  --package-qualification bench/out/compute-program/20260907-multi-dot-qualified/summary.json
```

Preparation requires the declared local model artifacts and pinned upstream
source. Omit `--offline` only when source fetching is needed. The retained native
control must match this host. `verify.py` independently checks this exact result
from the repository root with `PYTHONPATH=.` after its recorded package has been
installed; it does not execute GPU work. Run `sha256sum -c SHA256SUMS` from this
directory to check the retained bytes without recreating the installation.

`baseline.txt` and `source.patch` bind the runner, schema and test changes before
commit. The implementation remains owned by the existing external-project
harness; the oracle and shared package validation keep their existing owners.
