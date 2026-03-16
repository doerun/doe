# Browser lane

The browser family is split into two layers:

- `browser/fawn-browser`
  - docs, contracts, scripts, and diagnostics for Chromium integration
- `browser/chromium_webgpu_lane`
  - the actual Chromium checkout/build workspace when stored in-tree

Keep those layers distinct:

- `fawn-browser` is the control and evidence layer
- `chromium_webgpu_lane` is the heavyweight build workspace

Browser smoke and browser benchmark projection remain separate benchmark
contracts even when they share scripts or projection manifests.
