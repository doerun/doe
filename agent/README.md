# Fawn Agent Module

Purpose:
- ingest upstream quirk/workaround signals
- normalize into schema-valid quirk records

Sources:
- Dawn and wgpu source trees as external references

Current state:
- deterministic miner automation is available:
  - `mine_upstream_quirks.py`
    - scans one or more source roots for `Toggle::<Name>` signals
    - emits `quirks.schema`-valid candidate records (`schemaVersion: 2`)
    - emits a hash-linked mining manifest (`config/quirk-mining-manifest.schema.json`)
    - keeps output reproducible with sorted candidate order and deterministic hash chaining
- legacy MVP parser remains available:
  - `watchdog.py`

Example:

```bash
python3 fawn/agent/mine_upstream_quirks.py \
  --source-root fawn/bench/vendor/dawn/src/dawn/native/vulkan \
  --source-repo dawn/main \
  --source-commit <commit> \
  --vendor amd \
  --api vulkan \
  --output fawn/bench/out/mined-quirks.json \
  --manifest-output fawn/bench/out/mined-quirks.manifest.json
```
