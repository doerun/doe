import * as full from "../../src/index.js";

let passed = 0, failed = 0, skipped = 0;

function assert(condition, msg) {
  if (condition) { passed++; }
  else { failed++; console.error(`  FAIL: ${msg}`); }
}

function skip(msg) {
  skipped++;
  console.log(`  SKIP: ${msg}`);
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

let gpu, adapter, device;
try {
  gpu = full.create();
  adapter = await gpu.requestAdapter();
  device = await adapter.requestDevice();
} catch (err) {
  console.error(`Setup failed: ${err?.message ?? err}`);
  process.exit(1);
}

const { GPUBufferUsage } = full.globals;
const querySupportUnavailable = (err) => /timestamp query sets are not supported|unsupported|not supported|not available|unavailable/i.test(err?.message ?? String(err));

// ---------------------------------------------------------------------------
// a. createQuerySet with type "timestamp"
// ---------------------------------------------------------------------------

console.log("\n--- a. createQuerySet with type timestamp ---");
let querySet = null;
let querySupportMissing = false;
try {
  querySet = device.createQuerySet({ type: "timestamp", count: 2 });
  assert(querySet != null, "timestamp query set created");
  assert(querySet.type === "timestamp", `querySet.type === "timestamp" (got "${querySet.type}")`);
  assert(querySet.count === 2, `querySet.count === 2 (got ${querySet.count})`);
} catch (err) {
  if (querySupportUnavailable(err)) {
    querySupportMissing = true;
    skip(`timestamp query sets unavailable: ${err?.message ?? err}`);
  } else {
    failed++;
    console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
  }
}

// ---------------------------------------------------------------------------
// b. createQuerySet with count=1
// ---------------------------------------------------------------------------

console.log("\n--- b. createQuerySet with count=1 ---");
try {
  if (querySupportMissing) {
    skip("query set support unavailable on this backend/device");
  } else {
    const qs = device.createQuerySet({ type: "timestamp", count: 1 });
    assert(qs != null, "query set with count=1 created");
    assert(qs.count === 1, `querySet.count === 1 (got ${qs.count})`);
    qs.destroy();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// c. createQuerySet with larger count
// ---------------------------------------------------------------------------

console.log("\n--- c. createQuerySet with count=16 ---");
try {
  if (querySupportMissing) {
    skip("query set support unavailable on this backend/device");
  } else {
    const qs = device.createQuerySet({ type: "timestamp", count: 16 });
    assert(qs != null, "query set with count=16 created");
    assert(qs.count === 16, `querySet.count === 16 (got ${qs.count})`);
    qs.destroy();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// d. querySet.destroy()
// ---------------------------------------------------------------------------

console.log("\n--- d. querySet.destroy() ---");
try {
  if (querySupportMissing) {
    skip("query set support unavailable on this backend/device");
  } else {
    const qs = device.createQuerySet({ type: "timestamp", count: 4 });
    assert(typeof qs.destroy === "function", "querySet has destroy method");
    qs.destroy();
    assert(true, "querySet.destroy() completed without error");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// e. querySet double destroy — does not crash
// ---------------------------------------------------------------------------

console.log("\n--- e. querySet double destroy ---");
try {
  if (querySupportMissing) {
    skip("query set support unavailable on this backend/device");
  } else {
    const qs = device.createQuerySet({ type: "timestamp", count: 2 });
    qs.destroy();
    let secondOk = false;
    try {
      qs.destroy();
      secondOk = true;
    } catch {
      secondOk = true; // throwing is also acceptable
    }
    assert(secondOk, "double destroy on querySet does not crash");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// f. createQuerySet with invalid type — throws
// ---------------------------------------------------------------------------

console.log("\n--- f. createQuerySet with invalid type ---");
try {
  let threw = false;
  try {
    device.createQuerySet({ type: "occlusion", count: 2 });
  } catch {
    threw = true;
  }
  assert(threw, "createQuerySet with unsupported type throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// g. createQuerySet with count=0 — throws
// ---------------------------------------------------------------------------

console.log("\n--- g. createQuerySet with count=0 ---");
try {
  let threw = false;
  try {
    device.createQuerySet({ type: "timestamp", count: 0 });
  } catch {
    threw = true;
  }
  assert(threw, "createQuerySet with count=0 throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// h. writeTimestamp into query set
// ---------------------------------------------------------------------------

console.log("\n--- h. writeTimestamp into query set ---");
try {
  if (!querySet) {
    skip("querySet not available");
  } else {
    const encoder = device.createCommandEncoder();
    encoder.writeTimestamp(querySet, 0);
    encoder.writeTimestamp(querySet, 1);
    const commandBuffer = encoder.finish();
    assert(commandBuffer != null, "command buffer with writeTimestamp finished");
    device.queue.submit([commandBuffer]);
    await device.queue.onSubmittedWorkDone();
    assert(true, "writeTimestamp submitted without error");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// i. writeTimestamp — queryIndex out of bounds throws
// ---------------------------------------------------------------------------

console.log("\n--- i. writeTimestamp — queryIndex out of bounds ---");
try {
  if (!querySet) {
    skip("querySet not available");
  } else {
    const encoder = device.createCommandEncoder();
    let threw = false;
    try {
      // querySet has count=2, so index 2 is out of bounds
      encoder.writeTimestamp(querySet, 2);
    } catch {
      threw = true;
    }
    assert(threw, "writeTimestamp with out-of-bounds queryIndex throws");
    // Encoder may be in invalid state; do not finish
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// j. resolveQuerySet into buffer
// ---------------------------------------------------------------------------

console.log("\n--- j. resolveQuerySet into buffer ---");
try {
  if (!querySet) {
    skip("querySet not available");
  } else {
    // Timestamp query results are uint64 (8 bytes each)
    const QUERY_RESULT_SIZE = 8;
    const resolveBuffer = device.createBuffer({
      size: 2 * QUERY_RESULT_SIZE,
      usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC,
    });

    const encoder = device.createCommandEncoder();
    encoder.writeTimestamp(querySet, 0);
    encoder.writeTimestamp(querySet, 1);
    encoder.resolveQuerySet(querySet, 0, 2, resolveBuffer, 0);
    const commandBuffer = encoder.finish();
    assert(commandBuffer != null, "command buffer with resolveQuerySet finished");
    device.queue.submit([commandBuffer]);
    await device.queue.onSubmittedWorkDone();
    assert(true, "resolveQuerySet submitted without error");

    resolveBuffer.destroy();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// k. resolveQuerySet — firstQuery + queryCount exceeds count throws
// ---------------------------------------------------------------------------

console.log("\n--- k. resolveQuerySet — range exceeds query count ---");
try {
  if (!querySet) {
    skip("querySet not available");
  } else {
    const resolveBuffer = device.createBuffer({
      size: 64,
      usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC,
    });
    const encoder = device.createCommandEncoder();
    let threw = false;
    try {
      // querySet has count=2, so firstQuery=1 + queryCount=2 = 3 > 2
      encoder.resolveQuerySet(querySet, 1, 2, resolveBuffer, 0);
    } catch {
      threw = true;
    }
    assert(threw, "resolveQuerySet with range exceeding count throws");
    resolveBuffer.destroy();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// l. Timestamp query readback — values are plausible
// ---------------------------------------------------------------------------

console.log("\n--- l. Timestamp query readback ---");
try {
  if (!querySet) {
    skip("querySet not available");
  } else {
    const QUERY_RESULT_SIZE = 8;
    const resolveBuffer = device.createBuffer({
      size: 2 * QUERY_RESULT_SIZE,
      usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC,
    });
    const readbackBuffer = device.createBuffer({
      size: 2 * QUERY_RESULT_SIZE,
      usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
    });

    const encoder = device.createCommandEncoder();
    encoder.writeTimestamp(querySet, 0);
    encoder.writeTimestamp(querySet, 1);
    encoder.resolveQuerySet(querySet, 0, 2, resolveBuffer, 0);
    encoder.copyBufferToBuffer(resolveBuffer, 0, readbackBuffer, 0, 2 * QUERY_RESULT_SIZE);
    device.queue.submit([encoder.finish()]);
    await device.queue.onSubmittedWorkDone();

    await readbackBuffer.mapAsync(full.globals.GPUMapMode.READ);
    const timestamps = new BigUint64Array(readbackBuffer.getMappedRange(0, 2 * QUERY_RESULT_SIZE));
    const t0 = timestamps[0];
    const t1 = timestamps[1];

    // Both timestamps should be non-zero (GPU clock values)
    assert(t0 > 0n || t1 > 0n, `at least one timestamp is non-zero (t0=${t0}, t1=${t1})`);
    // t1 should be >= t0 (time moves forward)
    assert(t1 >= t0, `t1 >= t0 (t0=${t0}, t1=${t1})`);

    readbackBuffer.unmap();
    resolveBuffer.destroy();
    readbackBuffer.destroy();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

if (querySet) { try { querySet.destroy(); } catch { /* ok */ } }
if (typeof device.destroy === "function") { device.destroy(); }

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nQuery set integration: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
