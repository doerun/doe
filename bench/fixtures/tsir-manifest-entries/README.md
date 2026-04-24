# TSIR manifest lowering entries

These fixtures bind the Phase A bootstrap kernels to schema-valid
`integrityExtensions.lowerings[]` rows. Regenerate them with:

```sh
env PYTHONDONTWRITEBYTECODE=1 python3 bench/tools/generate_tsir_manifest_fixtures.py
```

The generator lowers the pinned WGSL bootstrap kernels through Doe IR, TSIR
semantic, and target realization planning, then calls the schema-backed
`bench/tools/tsir_manifest_lowering.py` builder to write the manifest entries.
