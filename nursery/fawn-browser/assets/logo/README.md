# Fawn logo assets (Chromium lane)

Source and compiled brand assets are now centralized here.

- Source SVG: `assets/logo/source/fawn-icon-main.svg`
- macOS compiled: `assets/logo/compiled/macos/fawn-icon-main.icns`
- Linux compiled preview PNGs: `assets/logo/compiled/linux/fawn-icon-main-<size>.png`
  - Generated sizes: 16, 32, 64, 128, 256, 512

Use the lane script to rebuild from source:

```bash
cd /Users/xyz/deco/fawn/nursery/fawn-browser
./scripts/build-fawn-logo-assets.sh
```

The Chromium lane patcher reads the canonical source path and will prefer the
prebuilt macOS `.icns` when available.
