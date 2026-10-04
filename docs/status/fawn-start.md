# Fawn start-page preview

The start page at `browser/chromium/resources/fawn-start.html` now opens an
interactive GPU particle field. Its configurations share the particle simulation
and trail renderer. Each seven-second interval holds for six seconds, then eases
into the next field over one second, including the final-to-first transition.
The active clock pauses with the page; transitions preserve particles and trails.
Pause, reset, touch cancellation, keyboard attraction, and reduced-motion
startup belong to the page. Search remains available, with workload settings,
adapter information, and links to the fluid demonstrations under Details.

Frame measurements count completed frames with a bounded submission loop.
They include browser scheduling and GPU waits, not GPU-only execution time.
The graph uses a zero-based scale; pause and visibility changes reset sampling.
The original Fawn mark appears in the header without the playground label.
The matching SVG favicon is included in both website sync and installed-app packaging. The
page makes no inferred Doe/Dawn provider claim. Resource disposal runs on
page exit; hidden pages stop scheduling frames. No native runtime or Vulkan
campaign behavior changed.

Validation: inline JavaScript syntax and whitespace checks passed. Extracted
WGSL translated through the local `doe-emit-msl` tool. A DOM harness with mock
WebGPU exercised dispatch, continuous field changes, pause/resume, pointer cancellation,
reset cleanup, workload changes, teardown, reduced motion, and unavailable-GPU
handling. Deterministic clocks and delayed queue completion additionally checked
frame-rate accuracy, submission backpressure, and pausing during GPU work. These checks do not establish rendered appearance or physical GPU
execution. The existing browser lifecycle probe follows the new status and
Details control but was not run: the user requested personal review without
agent browser use or screenshots.

The user approved publication through D4DA at `/doe/fawn-start.html`; its Doe
navigation links there directly. This page is not browser release qualification.
`node browser/chromium/scripts/test-fawn-start-cycle.mjs` verifies the cycle
boundaries, eased endpoints, and repeat behavior without browser automation.
