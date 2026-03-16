# Pipeline

`pipeline/` contains the supporting platform pipeline around the Doe runtime:

- `pipeline/agent/`
  - quirk mining and normalization
- `pipeline/lean/`
  - proof artifacts and eliminations
- `pipeline/trace/`
  - trace replay and comparison tooling

`config/` remains top-level for path stability, but it is conceptually part of
the same pipeline family.
