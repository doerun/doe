# Standalone Vulkan generation installation

## Disposition

The [installation summary](summary.json) records successful execution from an
independent consumer directory with the development workspace hidden and external
networking disabled. This is installation and selected-behavior evidence for
the accepted retained Vulkan implementation, not a performance comparison,
registry release, independent adopter, or broader platform qualification.

The [original generation experiment](../20261004-doppler-generation/README.md)
remains unchanged and closed. Its rejected buffer-reuse candidate receives no
credit from this check. The native library retains its original baseline hash;
no compiler, runtime policy, model mathematics, or sampling code changed.

## What executed

The [installation record](installation.json) binds original inputs, exact provider
archives, shipped package versions, the independent dependency lock, and the
copied executable harness. [Provider identities](providers.json) bind native
files. The [lockfile](package-lock.json) records required transitive dependencies;
the compressed [installed inventory](inventory.json.gz) binds their actual files.
All archive members match their installed bytes. No installed dependency symlink
escapes the consumer directory.

The [relocated contract](contract.json) changes only workload/classification
identity and model custody. The [CPU reference](reference.json) changes only its
contract hash. Original contract, provider manifest and CPU reference are retained
under `inputs/`; the audit explicitly compares all other fields. Model artifacts
are copied and verified without reconversion or modifying their manifest.

Bubblewrap hides the workspace and host temporary directories, clears inherited
environment variables, and creates a network namespace with loopback only.
System `/usr`, library directories, `/etc` and `/sys` remain read-only; `/dev`
exposes the host GPU, `/proc` is private, and the consumer directory is writable.
This is checkout/dependency isolation, not a hostile-code security claim.

Offline npm reconstruction passes using the retained cache and exact lockfile.
Fresh Doe runs and the pinned Dawn control exercise complete token IDs, streamed
text, EOS/length/sequence stopping, cancellation settlement, subsequent generation,
unload and device destruction. Each audit verifies the selected native file from
the running process's shared objects, including the Doe addon. Installation
failure checks reject missing native libraries, incompatible package versions,
and missing model assets before inference.

## Limits and retained failures

The first isolation attempt omitted `/sys`; adapter metadata then fell back to
unknown Vulkan vendor/default limits and model loading failed. That
[failed observation](missing-sysfs-failure.json.gz) remains retained. Read-only
hardware metadata restores the physical AMD adapter and supported limits without
changing package bytes or weakening model admission.

Doe's logs retain a buffer-pool warning after explicit device destruction.
The installed Doppler pool's device-loss handler attempts another queue wait;
the rejected wait enters its catch path, which destroys pending buffers. No
pending-buffer-destruction failure is reported. Cleanup credit is limited to the
observed public unload, completion settlement, reuse and device-destruction
boundaries. There is no allocation census proving leak-free native teardown.

Required dependencies are independently installed, while optional automatic
provider packages and npm scripts are explicitly omitted. These source-bound
archives contain the exact baseline library/addon. This does not qualify registry
platform packages, demonstrate semver compatibility with another provider
release, or publish model assets. Native binaries remain host-specific.

Timings in raw generation receipts are incidental. No cohort, optimization,
material advantage, or performance superiority is promoted. Another physical
host and another developer's reproduction remain separate acceptance.

## Reproduce

Use the [standalone runbook](../../../../bench/external-projects/doppler-generation/README.md#standalone-installed-execution)
to prepare from exact archive custody. The [retention manifest](manifest.json)
binds a self-contained local bundle, including native providers, verified model
bytes, required dependency cache, executable harness and qualification outputs.
Large bytes remain local; Git retains compact evidence and checksums.

On a supported Linux x64 Vulkan host, verify the bundle's declared SHA-256,
extract it into a new directory, then run:

```bash
python3 "$CONSUMER/harness/installed-generation.py" run --destination "$CONSUMER"
python3 "$CONSUMER/harness/installed-generation.py" verify --destination "$CONSUMER"
```

The copied tool has no imports into either development checkout. Its `run`
phase reconstructs dependencies offline before executing the workload with the
namespace boundaries above. `verify` authenticates installed files and joins
receipts to the CPU oracle, source inputs and loaded native identities.

Component: `doe.bench.external-projects`, `doe.config`, `doe.reports`, `doe.docs`.

Intent: preserved.

Acceptance evidence: [summary](summary.json), [manifest](manifest.json), retained
raw receipts/audits and focused installation-admission tests.

Boundary effects: repository-only preparation and qualification; no public API,
runtime policy, Doppler source, model or production package changes.
