# Browser

`browser/` contains exploratory Chromium-facing integration surfaces:

- `browser/chromium/`
  - docs, contracts, scripts, and browser diagnostics
- `browser/chromium_webgpu_lane/`
  - the Chromium checkout/build workspace when kept in-tree

Keep browser smoke, browser benchmark projection, and Chromium workspace
management separate even when they share scripts or artifacts.

This directory is not the current Doe product center. It exists for future
Chromium-lane integration work while Dawn remains the incumbent browser
runtime.
