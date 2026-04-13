# Experimental demos

`demos/` contains experimental or diagnostic sample applications.

Current demos:

- `demos/volume-render`
  - local package-backed volume rendering demo for manual exploration
- `demos/service-worker-compute`
  - service-worker compute sample host

This directory is repo-only and non-canonical:

- demos are not public package contracts
- demos are not runtime support commitments
- installed dependency trees such as `node_modules/` must not be checked in

If a demo becomes an actively supported surface, promote it explicitly in
[`config/tool-surfaces.json`](../config/tool-surfaces.json) and add durable docs
for its workflow and ownership.
