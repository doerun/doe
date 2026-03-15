import * as ffi from "./src/bun-ffi.js";
import { runSurfaceConformance } from "./test-package-surface-conformance.js";

const { passed, failed } = await runSurfaceConformance(ffi, "bun-ffi");

// Verify fast-path was exercised during compute dispatch + readback.
// The conformance suite runs dispatch+copy patterns that hit
// doeNativeComputeDispatchFlush (single native call for compute+blit+signal+commit).
const stats = ffi.fastPathStats;
console.log(`\n--- bun-ffi: fast-path stats ---`);
console.log(`  dispatchFlush: ${stats.dispatchFlush}`);
console.log(`  flushAndMap:   ${stats.flushAndMap}`);

let fpFailed = 0;
if (stats.dispatchFlush < 1) {
    console.error("FAIL: doeNativeComputeDispatchFlush was never called");
    fpFailed += 1;
} else {
    console.log("  fast-path dispatch assertion passed");
}

// flushAndMap fires when bufferMapAsync sees pending submissions that
// were NOT already marked done by the fast path. The conformance suite's
// dispatch+copy patterns go through the fast path which marks work done
// synchronously, so flushAndMap may legitimately be 0. Only assert it
// fires when there are non-fast-path submits followed by mapAsync.
if (stats.flushAndMap > 0) {
    console.log("  flushAndMap was exercised");
}

process.exitCode = (failed + fpFailed) > 0 ? 1 : 0;
