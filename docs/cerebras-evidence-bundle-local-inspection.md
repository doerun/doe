# Bundle — local inspection

Commands for a reviewer who has unpacked the bundle into a repo
checkout and wants to browse the evidence with the same browser
tools the bundler uses. All commands assume the repo root is the
current directory.

## Pre-flight

```bash
python3 bench/tools/verify_cerebras_validation_archive.py \
  --archive <the tarball you received>
```

Must PASS before acting on anything inside. The verifier re-checks
every manifest sha, BUNDLE_META shape, claim-role taxonomy, and
runs the claim-discipline regex scan against every doc in the
archive.

## Status dashboard (static)

Shows the rollup of target matrix + claim badges in one view.

```bash
# No server needed — static HTML
open demos/doe-status-dashboard/index.html
```

Or behind any static HTTP server if the browser refuses `file://`
relative fetches.

## E2B side-by-side demo (static OR with local CSL)

Shows WebGPU + CSL simfabric + CSL-WebGPU-emulator output
comparisons with the evidence cockpit strip (identity, speed,
per-layer accuracy, real-weight criteria, hardware-pending badges).

**Static-only mode** (no cs_python needed — loads stored receipts):

```bash
python3 -m http.server 8020
# then open http://localhost:8020/demos/gemma4-e2b-csl-sim/
# click "Load Stored CSL" to fetch the pinned L=1 reference trace
```

**Live mode** (requires `cs_python` on PATH — runs simfabric):

```bash
python3 demos/gemma4-e2b-csl-sim/server.py --port 8020
# then open http://localhost:8020/demos/gemma4-e2b-csl-sim/
# "Run CSL Simulator" now dispatches a live cs_python invocation
```

## SDK-GUI-style viewer (browser SDK GUI facsimile)

```bash
python3 demos/gemma4-e2b-csl-sim/server.py --port 8030
# then open http://localhost:8030/demos/doe-sdk-gui-viewer/
# default path auto-loads compile-L1; paste another artifact dir
# into the work-directory input to inspect that compile output
```

The viewer is shaped after the Cerebras SDK GUI reference screenshots:
work-directory bar, route/color selector, scalable fabric viewport,
PE coordinate selector and drilldown, instruction/source/wavelet
timeline panes, debug pane, timeline navigation controls, and a
terminal drawer for exported commands.

It inspects repo-relative artifact directories through the same
metadata-only server routes used by the E2B side-by-side demo. It
maps colors.json, host-I/O streams, stream telemetry, trace status,
and Doe evidence-bundle verdicts into the GUI without returning
`.elf`, `.map`, `.symbols`, `.viz`, or other SDK-owned file bytes.

The command strip also exposes copyable local commands for:

- `sdk_debug_shell visualize --artifact_dir ...` once the artifact
  directory is validated
- `python3 bench/tools/run_cerebras_evidence_bundle.py`
- `python3 bench/tools/pack_cerebras_validation_archive.py`
- `python3 bench/tools/verify_cerebras_validation_archive.py --archive ...`

On LAN HTTP origins where `navigator.clipboard` is blocked, the
viewer falls back to the browser's user-gesture copy path. When
path redaction is enabled, local-path commands are shown but not
copyable.

## `sdk_debug_shell visualize` command

If the bundler's `BUNDLE_META.csPython.csPythonAvailableOnBundler`
is `true`, Cerebras SDK was reachable at pack time. The matching
native visualize command on a Cerebras-SDK-equipped host:

```bash
sdk_debug_shell visualize --artifact_dir <path-to-compile-artifact-dir>
```

The `<path-to-compile-artifact-dir>` is whichever directory the
runner wrote `.elf` / `.lst` / `.map` / `.symbols` / `.viz` into
during compilation. These files are **explicitly excluded** from
this bundle (see the deny-list in
`bench/tools/pack_cerebras_validation_archive.py`) — they contain
SDK-internal binary artifacts that a reviewer should not be handed
through a shared archive.

If `BUNDLE_META.csPython.csPythonAvailableOnBundler` is `false`,
the bundler had no Cerebras SDK installed; the visualize command
is **not available via this bundle**. Reviewers with their own SDK
installation can re-run the runner (see `CEREBRAS_ASK.md`) against
the pinned manifest/graph/kernel hashes in this bundle to produce
their own compile artifact dir, then visualize it locally.

## Quick archive summary

```bash
bench/tools/summarize_cerebras_evidence_archive.sh <archive>
```

Prints E2B/31B/MoE status, bundle gate verdict, and emulator
verdicts — entirely from inside the tarball via `tar -xzO | jq`,
no unpack needed.

## Evidence-bundle regen (on the bundler's tree)

```bash
python3 bench/tools/run_cerebras_evidence_bundle.py
```

Runs the 5 gates the bundle's `rollup/cerebras-evidence-bundle/summary.json`
captures. Useful if a reviewer wants to confirm the same `verdict=passed`
the archive records still holds on the current repo state.

## Closing the loop

After a hardware_success receipt lands (hypothetical — none exists
today): re-run `pack_cerebras_validation_archive.py` to produce a
new archive whose BUNDLE_META's gitCommit postdates the receipt and
whose `claim-discipline` gate state flips to INACTIVE for hardware-
gated rules. The claim-scope doc automatically expands its
"claimable" list when the receipt is present in-repo.
