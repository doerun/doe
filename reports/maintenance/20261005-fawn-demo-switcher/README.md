# Local Fawn demo switcher

The unpublished candidate adds a compact Demos disclosure in each page's header.
It marks the current demo and navigates through ordinary relative links. Escape
closes the disclosure and restores focus; outside interaction dismisses it.
The main page retains its automatic particle-field cycle. Other menu choices
open separate simulator implementations. There is no address field and no new
animation loop.

The local cycle probe also exposed a negative initial elapsed time: an animation
frame's timestamp can precede `performance.now()` recorded at initialization.
The main cycle then selected a negative phase, and other simulations received a
negative step. The candidate clamps elapsed frame time at zero across the
animation demos. Positive frame timing and all shaders remain unchanged.

[Application results](results.json) retain Chrome/adapter identity, source hashes,
the failing baseline and corrected uniform values, navigation, keyboard and
outside dismissal, desktop/mobile menu bounds, GPU errors, and the observed
particle-field cycle. [Standalone page results](pages.json) additionally preserve matched GPU state
and exact pixels while checking existing controls and lifecycle.
[Custody](custody.json) binds the reports, source, and
[local visual preview](mobile.png). These are stock Chrome application checks,
not Doe-versus-Dawn performance evidence. No website deployment occurred.

Before future CanvasContext publication, D4DA's packaging allowlist must include
Image Lab, which is currently repository-only. Local previews and Fawn's resource
packaging include that page.

## Reproduction

Run from the Doe project root with Chrome and Playwright installed:

```sh
export FAWN_PLAYWRIGHT_MODULE="$PWD/../d4da/node_modules/playwright/index.mjs"
node browser/chromium/scripts/test-fawn-demo-switcher.mjs
```

`FAWN_REPORT_DIR` selects the generated report and screenshots directory. The
check drives an early RAF timestamp on the frozen baseline and candidate, then
uses unmodified animation scheduling to observe a complete particle-field cycle.
