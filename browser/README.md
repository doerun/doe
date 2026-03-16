# Browser

`browser/` contains Chromium-facing integration surfaces:

- `browser/fawn-browser/`
  - docs, contracts, scripts, and browser diagnostics
- `browser/chromium_webgpu_lane/`
  - the Chromium checkout/build workspace when kept in-tree

Keep browser smoke, browser benchmark projection, and Chromium workspace
management separate even when they share scripts or artifacts.
