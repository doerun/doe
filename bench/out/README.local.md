Local bench output mirror

Most of this directory is intentionally ignored by git.
Tracked stable mirrors live under `bench/out/cube/latest/` and
`bench/out/visualization/latest/`.
Small compare/release/smoke summary JSONs and HTML reports under `bench/out/`
can also be committed; bulky NDJSON workspaces and large harvested benchmark
JSON corpora stay ignored unless promoted deliberately.

Layout

- `apple-metal-full-greedy-16step/`
  Mirrored archive copy from `models2`. Treat as read-only.
- `apple-metal-dawn-full-greedy-16step/`
  Mirrored archive copy from `models2`. Treat as read-only.
- `apple-metal-webkit-full-greedy-16step/`
  Mirrored archive copy from `models2`. Treat as read-only.
- `amd-vulkan-full-greedy-16step/`
  Mirrored archive copy from `models2`. Treat as read-only. This tree contains historical reruns for some batches.
- `amd-vulkan-*/`, `apple-metal-*.json`
  Mirrored analysis artifacts and operator-level receipts copied from `models2`.
- `_wip/amd-vulkan-dawn-full-greedy-16step-partial-20260403/`
  Quarantined partial local rerun for `AMD Dawn / gemma270m / 16step`. Not part of the canonical mirrored archive set.

Current intent

- Keep the mirrored archive roots stable for analysis and blog work.
- Keep partial or failed reruns under `_wip/`.
- If `AMD Dawn / 16step` is rerun cleanly, write it to `amd-vulkan-dawn-full-greedy-16step/` at the top level and then move or delete the partial `_wip/` copy.
