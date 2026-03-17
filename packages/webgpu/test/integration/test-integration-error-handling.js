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

async function assertRejects(fn, msg) {
  try {
    await fn();
    failed++;
    console.error(`  FAIL (no throw): ${msg}`);
  } catch {
    passed++;
  }
}

async function assertRejectsMatching(fn, pattern, msg) {
  try {
    await fn();
    failed++;
    console.error(`  FAIL (no throw): ${msg}`);
  } catch (err) {
    if (pattern.test(err?.message ?? String(err))) {
      passed++;
    } else {
      failed++;
      console.error(`  FAIL (wrong error "${err?.message}"): ${msg}`);
    }
  }
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

const { GPUBufferUsage, GPUMapMode, GPUTextureUsage } = full.globals;

// ---------------------------------------------------------------------------
// a. createShaderModule with invalid WGSL — throws with structured fields
// ---------------------------------------------------------------------------

console.log("\n--- a. createShaderModule with invalid WGSL ---");
try {
  let caughtError = null;
  try {
    device.createShaderModule({
      code: `fn main() -> @location(0) vec4f { let x = !!!; return vec4f(0); }`,
    });
    failed++;
    console.error("  FAIL (no throw): invalid WGSL should throw");
  } catch (err) {
    caughtError = err;
    passed++;
  }
  if (caughtError) {
    assert(caughtError instanceof Error, "shader error is an Error instance");
    assert(caughtError.message.length > 0, "shader error has a message");
    assert(
      typeof caughtError.stage === "string" && caughtError.stage.length > 0,
      `shader error.stage is a non-empty string (got ${JSON.stringify(caughtError.stage)})`
    );
    assert(
      typeof caughtError.line === "number" && caughtError.line > 0,
      `shader error.line is a positive number (got ${JSON.stringify(caughtError.line)})`
    );
    assert(
      typeof caughtError.column === "number" && caughtError.column > 0,
      `shader error.column is a positive number (got ${JSON.stringify(caughtError.column)})`
    );
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// b. preflightShaderSource — rejection has structured fields
// ---------------------------------------------------------------------------

console.log("\n--- b. preflightShaderSource — rejection ---");
try {
  const result = full.preflightShaderSource(`fn main() { let x = !!!; }`);
  assert(result.ok === false, "preflight rejects invalid WGSL");
  assert(result.message.length > 0, "preflight rejection has a message");
  assert(typeof result.stage === "string" && result.stage.length > 0, "preflight rejection has stage");
  assert(typeof result.line === "number" && result.line > 0, "preflight rejection has line");
  assert(typeof result.column === "number" && result.column > 0, "preflight rejection has column");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// c. preflightShaderSource — acceptance
// ---------------------------------------------------------------------------

console.log("\n--- c. preflightShaderSource — acceptance ---");
try {
  const result = full.preflightShaderSource(`
    @compute @workgroup_size(1)
    fn main(@builtin(global_invocation_id) gid: vec3u) {}
  `);
  assert(result.ok === true, "preflight accepts valid WGSL");
  assert(result.reasons.length === 0, "preflight acceptance has no reasons");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// d. createBuffer — invalid size (0) throws
// ---------------------------------------------------------------------------

console.log("\n--- d. createBuffer — size 0 throws ---");
try {
  let threw = false;
  try {
    device.createBuffer({ size: 0, usage: GPUBufferUsage.STORAGE });
  } catch {
    threw = true;
  }
  assert(threw, "createBuffer with size 0 throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// e. createBuffer — negative size throws
// ---------------------------------------------------------------------------

console.log("\n--- e. createBuffer — negative size throws ---");
try {
  let threw = false;
  try {
    device.createBuffer({ size: -1, usage: GPUBufferUsage.STORAGE });
  } catch {
    threw = true;
  }
  assert(threw, "createBuffer with negative size throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// f. createBuffer — invalid usage flags throw
// ---------------------------------------------------------------------------

console.log("\n--- f. createBuffer — invalid usage flags throw ---");
try {
  let threw = false;
  try {
    // 0x80000000 is not a valid buffer usage bit
    device.createBuffer({ size: 16, usage: 0x80000000 });
  } catch {
    threw = true;
  }
  assert(threw, "createBuffer with unknown usage flag throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// g. mapAsync on destroyed buffer — throws
// ---------------------------------------------------------------------------

console.log("\n--- g. mapAsync on destroyed buffer ---");
try {
  const buf = device.createBuffer({
    size: 16,
    usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST,
  });
  buf.destroy();
  await assertRejectsMatching(
    async () => buf.mapAsync(GPUMapMode.READ),
    /destroy/i,
    "mapAsync on destroyed buffer throws with destroy-related message"
  );
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// h. writeBuffer to destroyed buffer — throws
// ---------------------------------------------------------------------------

console.log("\n--- h. writeBuffer to destroyed buffer ---");
try {
  const buf = device.createBuffer({
    size: 16,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
  });
  buf.destroy();
  let threw = false;
  try {
    device.queue.writeBuffer(buf, 0, new Uint8Array([1, 2, 3, 4]));
  } catch {
    threw = true;
  }
  assert(threw, "writeBuffer to destroyed buffer throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// i. Double destroy on buffer — does not crash
// ---------------------------------------------------------------------------

console.log("\n--- i. Double destroy on buffer ---");
try {
  const buf = device.createBuffer({
    size: 16,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
  });
  buf.destroy();
  let secondOk = false;
  try {
    buf.destroy();
    secondOk = true;
  } catch {
    secondOk = true; // throwing is also acceptable
  }
  assert(secondOk, "double destroy on buffer does not crash");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// j. createShaderModule with empty code — throws
// ---------------------------------------------------------------------------

console.log("\n--- j. createShaderModule with empty code ---");
try {
  let threw = false;
  try {
    device.createShaderModule({ code: "" });
  } catch {
    threw = true;
  }
  assert(threw, "createShaderModule with empty code throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// k. createComputePipeline with invalid entry point — throws
// ---------------------------------------------------------------------------

console.log("\n--- k. createComputePipeline with invalid entry point ---");
try {
  const shader = device.createShaderModule({
    code: `
      @compute @workgroup_size(1)
      fn main(@builtin(global_invocation_id) gid: vec3u) {}
    `,
  });
  let threw = false;
  try {
    device.createComputePipeline({
      layout: "auto",
      compute: { module: shader, entryPoint: "nonexistent_entry_xyz" },
    });
  } catch {
    threw = true;
  }
  assert(threw, "createComputePipeline with invalid entry point throws");
  shader.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// l. createTexture with invalid usage (0) — throws
// ---------------------------------------------------------------------------

console.log("\n--- l. createTexture with invalid usage (0) ---");
try {
  let threw = false;
  try {
    device.createTexture({
      size: [4, 4, 1],
      format: "rgba8unorm",
      usage: 0,
    });
  } catch {
    threw = true;
  }
  assert(threw, "createTexture with usage 0 throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// m. createBindGroupLayout with invalid sampler type — throws
// ---------------------------------------------------------------------------

console.log("\n--- m. createBindGroupLayout with invalid sampler type ---");
try {
  let threw = false;
  try {
    device.createBindGroupLayout({
      entries: [
        {
          binding: 0,
          visibility: full.globals.GPUShaderStage.COMPUTE,
          sampler: { type: "invalid_sampler_type" },
        },
      ],
    });
  } catch {
    threw = true;
  }
  assert(threw, "createBindGroupLayout with invalid sampler type throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// n. createRenderPipeline without vertex descriptor — throws
// ---------------------------------------------------------------------------

console.log("\n--- n. createRenderPipeline without vertex descriptor ---");
try {
  let threw = false;
  try {
    device.createRenderPipeline({
      layout: "auto",
      // missing vertex
      fragment: {
        module: device.createShaderModule({
          code: `@fragment fn main() -> @location(0) vec4f { return vec4f(1.0); }`,
        }),
        entryPoint: "main",
        targets: [{ format: "rgba8unorm" }],
      },
    });
  } catch {
    threw = true;
  }
  assert(threw, "createRenderPipeline without vertex descriptor throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// o. createQuerySet with invalid type — throws
// ---------------------------------------------------------------------------

console.log("\n--- o. createQuerySet with invalid type ---");
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
// p. Finish already-finished command encoder — throws
// ---------------------------------------------------------------------------

console.log("\n--- p. Finish already-finished command encoder ---");
try {
  const encoder = device.createCommandEncoder();
  encoder.finish();
  let threw = false;
  try {
    encoder.finish();
  } catch {
    threw = true;
  }
  assert(threw, "finish on already-finished encoder throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// q. beginComputePass on finished encoder — throws
// ---------------------------------------------------------------------------

console.log("\n--- q. beginComputePass on finished encoder ---");
try {
  const encoder = device.createCommandEncoder();
  encoder.finish();
  let threw = false;
  try {
    encoder.beginComputePass();
  } catch {
    threw = true;
  }
  assert(threw, "beginComputePass on finished encoder throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// r. mappedAtCreation — size not multiple of 4 throws
// ---------------------------------------------------------------------------

console.log("\n--- r. mappedAtCreation — size not multiple of 4 throws ---");
try {
  let threw = false;
  try {
    device.createBuffer({
      size: 7,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      mappedAtCreation: true,
    });
  } catch {
    threw = true;
  }
  assert(threw, "createBuffer with mappedAtCreation and size not multiple of 4 throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// s. getMappedRange beyond buffer size — throws
// ---------------------------------------------------------------------------

console.log("\n--- s. getMappedRange beyond buffer size ---");
try {
  const buf = device.createBuffer({
    size: 16,
    usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST,
    mappedAtCreation: true,
  });
  let threw = false;
  try {
    buf.getMappedRange(0, 32); // exceeds buffer size of 16
  } catch {
    threw = true;
  }
  assert(threw, "getMappedRange with offset+size > buffer.size throws");
  buf.unmap();
  buf.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

if (typeof device.destroy === "function") { device.destroy(); }

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nError handling: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
