import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import * as compute from "./src/compute.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

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

// Run a snippet in a child process and return { ok, stdout, stderr, exitCode, signal }
function runInSubprocess(snippet) {
  try {
    const out = execFileSync(process.execPath, ["--input-type=module", "-e", snippet], {
      cwd: __dirname,
      encoding: "utf8",
      timeout: 8000,
      stdio: ["ignore", "pipe", "pipe"],
    });
    return { ok: true, stdout: out, stderr: "", exitCode: 0, signal: null };
  } catch (err) {
    return {
      ok: false,
      stdout: err.stdout ?? "",
      stderr: err.stderr ?? "",
      exitCode: err.status ?? -1,
      signal: err.signal ?? null,
    };
  }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const gpu = await compute.doe.requestDevice();

// ---------------------------------------------------------------------------
// a. Indirect dispatch via kernel
//    Run in a subprocess so the published package surface is exercised the same
//    way as consumers, while still isolating hard native failures if they recur.
// ---------------------------------------------------------------------------

console.log("\n--- a. Indirect dispatch via kernel (subprocess) ---");
{
  // Use single-quoted WGSL to avoid nested backtick issues in the subprocess snippet
  const INDIRECT_WGSL = [
    "@group(0) @binding(0) var<storage, read> src: array<f32>;",
    "@group(0) @binding(1) var<storage, read_write> dst: array<f32>;",
    "@compute @workgroup_size(4)",
    "fn main(@builtin(global_invocation_id) gid: vec3u) { dst[gid.x] = src[gid.x] * 2.0; }",
  ].join("\n");

  const SNIPPET = `
    import * as compute from "./src/compute.js";
    const gpu = await compute.doe.requestDevice();
    const indirectData = new Uint32Array([2, 1, 1]);
    const indirectBuf = gpu.device.createBuffer({
      size: indirectData.byteLength,
      usage: compute.globals.GPUBufferUsage.INDIRECT | compute.globals.GPUBufferUsage.COPY_DST,
    });
    gpu.device.queue.writeBuffer(indirectBuf, 0, indirectData);
    const src = gpu.buffer.create({ data: new Float32Array([1, 2, 3, 4, 5, 6, 7, 8]) });
    const dst = gpu.buffer.create({ size: 8 * 4, usage: "storageReadWrite" });
    const shader = gpu.device.createShaderModule({ code: ${JSON.stringify(INDIRECT_WGSL)} });
    const pipeline = gpu.device.createComputePipeline({
      layout: "auto",
      compute: { module: shader, entryPoint: "main" },
    });
    const bindGroup = gpu.device.createBindGroup({
      layout: pipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: { buffer: src } },
        { binding: 1, resource: { buffer: dst } },
      ],
    });
    const encoder = gpu.device.createCommandEncoder();
    const pass = encoder.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bindGroup);
    pass.dispatchWorkgroupsIndirect(indirectBuf, 0);
    pass.end();
    gpu.device.queue.submit([encoder.finish()]);
    await gpu.device.queue.onSubmittedWorkDone();
    const result = await gpu.buffer.read({ buffer: dst, type: Float32Array });
    const ok = result[0] === 2 && result[7] === 16;
    console.log(ok ? "PASS" : "FAIL:" + Array.from(result));
  `;

  const res = runInSubprocess(SNIPPET);
  if (res.ok && res.stdout.trim() === "PASS") {
    assert(true, "indirect dispatch: result[0]=2 and result[7]=16");
  } else if (res.ok) {
    failed++;
    console.error(`  FAIL: indirect dispatch unexpected output: ${res.stdout.trim()}`);
  } else {
    failed++;
    console.error(`  FAIL: indirect dispatch subprocess failed (exit ${res.exitCode}, signal ${res.signal}): ${res.stderr.slice(0, 200)}`);
  }
}

// ---------------------------------------------------------------------------
// b. Kernel reuse with varying workgroups
// ---------------------------------------------------------------------------

console.log("\n--- b. Kernel reuse with varying workgroups ---");
try {
  const src1 = gpu.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
  const src2 = gpu.buffer.create({ data: new Float32Array([10, 20, 30, 40, 50, 60, 70, 80]) });
  const src3 = gpu.buffer.create({ data: new Float32Array([100, 200]) });
  const dst1 = gpu.buffer.create({ size: src1.size, usage: "storageReadWrite" });
  const dst2 = gpu.buffer.create({ size: src2.size, usage: "storageReadWrite" });
  const dst3 = gpu.buffer.create({ size: src3.size, usage: "storageReadWrite" });

  const kernel = gpu.kernel.create({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(4)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        let i = gid.x;
        dst[i] = src[i] + 1.0;
      }
    `,
    bindings: [src1, dst1],
  });

  await kernel.dispatch({ bindings: [src1, dst1], workgroups: 1 });
  const r1 = await gpu.buffer.read({ buffer: dst1, type: Float32Array });
  assert(r1[0] === 2 && r1[3] === 5, "kernel reuse dispatch 1: 4 elements, result correct");

  await kernel.dispatch({ bindings: [src2, dst2], workgroups: 2 });
  const r2 = await gpu.buffer.read({ buffer: dst2, type: Float32Array });
  assert(r2[0] === 11 && r2[7] === 81, "kernel reuse dispatch 2: 8 elements, 2 workgroups correct");

  await kernel.dispatch({ bindings: [src3, dst3], workgroups: 1 });
  const r3 = await gpu.buffer.read({ buffer: dst3, type: Float32Array });
  assert(r3[0] === 101 && r3[1] === 201, "kernel reuse dispatch 3: 2 elements, oversized workgroup correct");

  if (typeof src1.destroy === "function") src1.destroy();
  if (typeof src2.destroy === "function") src2.destroy();
  if (typeof src3.destroy === "function") src3.destroy();
  if (typeof dst1.destroy === "function") dst1.destroy();
  if (typeof dst2.destroy === "function") dst2.destroy();
  if (typeof dst3.destroy === "function") dst3.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// c. compute with likeInput
// ---------------------------------------------------------------------------

console.log("\n--- c. compute with likeInput ---");
try {
  const inputData = new Float32Array([3, 6, 9, 12]);
  const result = await gpu.compute({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(4)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        dst[gid.x] = src[gid.x];
      }
    `,
    inputs: [inputData],
    output: { type: Float32Array, likeInput: 0 },
    workgroups: 1,
  });
  assert(result.length === 4, "likeInput: output length matches input length (4)");
  assert(result[0] === 3 && result[3] === 12, "likeInput: output values copied from input");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// d. compute with explicit output size different from input size
// ---------------------------------------------------------------------------

console.log("\n--- d. compute with explicit output size ---");
try {
  const inputData = new Float32Array([1, 2, 3, 4]);
  // Output has 2 elements (8 bytes) while input has 4 elements — explicitly different size
  const result = await gpu.compute({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(1)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        dst[0] = src[0] + src[1];
        dst[1] = src[2] + src[3];
      }
    `,
    inputs: [inputData],
    output: { type: Float32Array, size: 2 * 4 },
    workgroups: 1,
  });
  assert(result.length === 2, "explicit output size: output has 2 elements");
  assert(result[0] === 3, "explicit output size: result[0] = 1+2 = 3");
  assert(result[1] === 7, "explicit output size: result[1] = 3+4 = 7");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// e. compute with mixed input types (uniform + storageRead + output)
// ---------------------------------------------------------------------------

console.log("\n--- e. compute with mixed input types ---");
try {
  const result = await gpu.compute({
    code: `
      struct Scale {
        value: f32,
      };
      @group(0) @binding(0) var<uniform> scale: Scale;
      @group(0) @binding(1) var<storage, read> src: array<f32>;
      @group(0) @binding(2) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(4)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        let i = gid.x;
        dst[i] = src[i] * scale.value;
      }
    `,
    inputs: [
      { data: new Float32Array([3.0]), usage: "uniform", access: "uniform" },
      new Float32Array([1, 2, 3, 4]),
    ],
    output: { type: Float32Array, likeInput: 1 },
    workgroups: 1,
  });
  assert(result.length === 4, "mixed inputs: output length = 4");
  assert(result[0] === 3 && result[3] === 12, "mixed inputs: uniform scale=3 applied correctly");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// f. Multiple entry points — two kernels from one shader
// ---------------------------------------------------------------------------

console.log("\n--- f. Multiple entry points ---");
try {
  const MULTI_ENTRY_WGSL = `
    @group(0) @binding(0) var<storage, read> src: array<f32>;
    @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main1(@builtin(global_invocation_id) gid: vec3u) {
      dst[gid.x] = src[gid.x] * 2.0;
    }

    @compute @workgroup_size(4)
    fn main2(@builtin(global_invocation_id) gid: vec3u) {
      dst[gid.x] = src[gid.x] * 10.0;
    }
  `;

  const srcBuf = gpu.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
  const dstBuf1 = gpu.buffer.create({ size: srcBuf.size, usage: "storageReadWrite" });
  const dstBuf2 = gpu.buffer.create({ size: srcBuf.size, usage: "storageReadWrite" });

  const kernel1 = gpu.kernel.create({ code: MULTI_ENTRY_WGSL, bindings: [srcBuf, dstBuf1], entryPoint: "main1" });
  const kernel2 = gpu.kernel.create({ code: MULTI_ENTRY_WGSL, bindings: [srcBuf, dstBuf2], entryPoint: "main2" });

  await kernel1.dispatch({ bindings: [srcBuf, dstBuf1], workgroups: 1 });
  await kernel2.dispatch({ bindings: [srcBuf, dstBuf2], workgroups: 1 });

  const res1 = await gpu.buffer.read({ buffer: dstBuf1, type: Float32Array });
  const res2 = await gpu.buffer.read({ buffer: dstBuf2, type: Float32Array });

  assert(res1[0] === 2 && res1[3] === 8, "multiple entry points: main1 doubles values");
  assert(res2[0] === 10 && res2[3] === 40, "multiple entry points: main2 multiplies by 10");
  assert(res1[0] !== res2[0], "multiple entry points: two kernels produce different results");

  if (typeof srcBuf.destroy === "function") srcBuf.destroy();
  if (typeof dstBuf1.destroy === "function") dstBuf1.destroy();
  if (typeof dstBuf2.destroy === "function") dstBuf2.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// g. kernel.run with custom entryPoint
// ---------------------------------------------------------------------------

console.log("\n--- g. kernel.run with custom entryPoint ---");
try {
  const src = gpu.buffer.create({ data: new Float32Array([5, 10, 15, 20]) });
  const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });

  await gpu.kernel.run({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

      @compute @workgroup_size(4)
      fn default_entry(@builtin(global_invocation_id) gid: vec3u) {
        dst[gid.x] = src[gid.x] + 1000.0;
      }

      @compute @workgroup_size(4)
      fn my_entry(@builtin(global_invocation_id) gid: vec3u) {
        dst[gid.x] = src[gid.x] * 3.0;
      }
    `,
    bindings: [src, dst],
    workgroups: 1,
    entryPoint: "my_entry",
  });

  const result = await gpu.buffer.read({ buffer: dst, type: Float32Array });
  assert(result[0] === 15, "custom entryPoint: result[0] = 5*3 = 15");
  assert(result[3] === 60, "custom entryPoint: result[3] = 20*3 = 60");

  if (typeof src.destroy === "function") src.destroy();
  if (typeof dst.destroy === "function") dst.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// h. Large buffer round-trip (1 MB)
// ---------------------------------------------------------------------------

console.log("\n--- h. Large buffer round-trip (1 MB) ---");
try {
  const COUNT = 1024 * 1024 / 4; // 1 MB as Float32 elements (262144 floats)
  const hostData = new Float32Array(COUNT);
  for (let i = 0; i < COUNT; i++) hostData[i] = i % 256;

  const src = gpu.buffer.create({ data: hostData });
  const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });

  // workgroup_size(256) → COUNT/256 = 1024 workgroups (within maxComputeWorkgroupsPerDimension)
  // Note: Doe validation checks workgroup count against maxComputeWorkgroupSizeX (1024), so
  // we stay at exactly 1024 which is the limit.
  const WGSIZE = 256;
  const workgroups = COUNT / WGSIZE;  // = 1024, within the validation limit
  await gpu.kernel.run({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(256)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        dst[gid.x] = src[gid.x] + 1.0;
      }
    `,
    bindings: [src, dst],
    workgroups,
  });

  const result = await gpu.buffer.read({ buffer: dst, type: Float32Array });
  assert(result.length === COUNT, `large buffer: result length = ${COUNT}`);

  // Sample every 1024th element to verify correctness
  let correct = true;
  for (let i = 0; i < COUNT; i += 1024) {
    if (result[i] !== (i % 256) + 1) { correct = false; break; }
  }
  assert(correct, "large buffer: sampled values all incremented by 1");

  if (typeof src.destroy === "function") src.destroy();
  if (typeof dst.destroy === "function") dst.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// i. Buffer create with mappedAtCreation
// ---------------------------------------------------------------------------

console.log("\n--- i. Buffer create with mappedAtCreation ---");
try {
  const DATA = new Float32Array([7, 14, 21, 28]);
  // mappedAtCreation with raw numeric usage flags
  const rawUsage = compute.globals.GPUBufferUsage.STORAGE
    | compute.globals.GPUBufferUsage.COPY_DST
    | compute.globals.GPUBufferUsage.COPY_SRC;

  const mappedBuf = gpu.buffer.create({
    size: DATA.byteLength,
    usage: rawUsage,
    mappedAtCreation: true,
  });

  assert(typeof mappedBuf.getMappedRange === "function", "mappedAtCreation: getMappedRange is a function");
  // Write data into the mapped range and unmap — API must not throw
  const range = mappedBuf.getMappedRange(0, DATA.byteLength);
  assert(range instanceof ArrayBuffer && range.byteLength === DATA.byteLength,
    "mappedAtCreation: getMappedRange returns ArrayBuffer of correct size");
  new Float32Array(range).set(DATA);
  mappedBuf.unmap();

  const dstBuf = gpu.buffer.create({ size: DATA.byteLength, usage: "storageReadWrite" });
  await gpu.kernel.run({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(4)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        dst[gid.x] = src[gid.x] * 2.0;
      }
    `,
    bindings: [
      { buffer: mappedBuf, access: "storageRead" },
      dstBuf,
    ],
    workgroups: 1,
  });

  const result = await gpu.buffer.read({ buffer: dstBuf, type: Float32Array });
  assert(result[0] === 14, "mappedAtCreation writeback: result[0] = 7*2 = 14");
  assert(result[3] === 56, "mappedAtCreation writeback: result[3] = 28*2 = 56");

  if (typeof mappedBuf.destroy === "function") mappedBuf.destroy();
  if (typeof dstBuf.destroy === "function") dstBuf.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// j. buffer.read with offset and size
// ---------------------------------------------------------------------------

console.log("\n--- j. buffer.read with offset and size ---");
try {
  const DATA = new Float32Array([1, 2, 3, 4, 5, 6, 7, 8]);
  const src = gpu.buffer.create({ data: DATA });
  const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });

  // Identity copy to populate dst
  await gpu.kernel.run({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;
      @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
      @compute @workgroup_size(8)
      fn main(@builtin(global_invocation_id) gid: vec3u) {
        dst[gid.x] = src[gid.x];
      }
    `,
    bindings: [src, dst],
    workgroups: 1,
  });

  // Read only elements at indices 2, 3, 4 — offset=8 bytes (2 floats), size=12 bytes (3 floats)
  const slice = await gpu.buffer.read({ buffer: dst, type: Float32Array, offset: 8, size: 12 });
  assert(slice.length === 3, "read with offset/size: 3 elements");
  assert(slice[0] === 3 && slice[1] === 4 && slice[2] === 5, "read with offset/size: slice=[3,4,5]");

  if (typeof src.destroy === "function") src.destroy();
  if (typeof dst.destroy === "function") dst.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// k. Invalid WGSL in kernel.run — error is thrown with structured fields
// ---------------------------------------------------------------------------

console.log("\n--- k. Invalid WGSL in kernel.run ---");
try {
  let caughtError = null;
  try {
    await gpu.kernel.run({
      code: `fn main() { let x = !!!; }`,
      bindings: [],
      workgroups: 1,
    });
    failed++;
    console.error("  FAIL (no throw): invalid WGSL should throw");
  } catch (err) {
    caughtError = err;
    passed++;
  }
  if (caughtError) {
    assert(caughtError instanceof Error, "invalid WGSL: error is an Error instance");
    assert(caughtError.message.length > 0, "invalid WGSL: error has a message");
    // Doe emits structured shader errors with stage, line, column fields (no 'kind' on kernel errors)
    assert(
      typeof caughtError.stage === "string" && caughtError.stage.length > 0,
      `invalid WGSL: error.stage is a non-empty string (got ${JSON.stringify(caughtError.stage)})`
    );
    assert(
      typeof caughtError.line === "number" && caughtError.line > 0,
      `invalid WGSL: error.line is a positive number (got ${JSON.stringify(caughtError.line)})`
    );
    assert(
      typeof caughtError.column === "number" && caughtError.column > 0,
      `invalid WGSL: error.column is a positive number (got ${JSON.stringify(caughtError.column)})`
    );
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// l. Binding without access metadata — raw buffer without Doe helper usage
// ---------------------------------------------------------------------------

console.log("\n--- l. Binding without access metadata ---");
try {
  // A buffer created via gpu.device.createBuffer (raw numeric usage, no Doe metadata)
  // requires explicit { buffer, access } to be used in a kernel binding.
  const rawBuf = gpu.device.createBuffer({
    size: 16,
    usage: compute.globals.GPUBufferUsage.STORAGE | compute.globals.GPUBufferUsage.COPY_DST,
  });

  await assertRejectsMatching(
    async () => {
      await gpu.kernel.run({
        code: `
          @group(0) @binding(0) var<storage, read> src: array<f32>;
          @compute @workgroup_size(1)
          fn main(@builtin(global_invocation_id) gid: vec3u) { _ = src[gid.x]; }
        `,
        bindings: [rawBuf],  // no Doe metadata, no explicit access
        workgroups: 1,
      });
    },
    /Doe binding access is required/,
    "raw buffer without metadata: error mentions 'Doe binding access is required'"
  );

  if (typeof rawBuf.destroy === "function") rawBuf.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// m. Invalid entry point name
// ---------------------------------------------------------------------------

console.log("\n--- m. Invalid entry point name ---");
try {
  await assertRejects(async () => {
    await gpu.kernel.run({
      code: `
        @compute @workgroup_size(1)
        fn main(@builtin(global_invocation_id) gid: vec3u) {}
      `,
      bindings: [],
      workgroups: 1,
      entryPoint: "nonexistent_entry_point_xyz",
    });
  }, "invalid entryPoint: should throw");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// n. Zero-size buffer
// ---------------------------------------------------------------------------

console.log("\n--- n. Zero-size buffer ---");
try {
  // validatePositiveInteger requires size >= 1, so size: 0 must throw
  let threw = false;
  try {
    gpu.buffer.create({ size: 0, usage: "storageReadWrite" });
  } catch {
    threw = true;
  }
  assert(threw, "zero-size buffer: create({ size: 0 }) throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// o. Attempt to use a destroyed buffer
// ---------------------------------------------------------------------------

console.log("\n--- o. Destroyed buffer: mapAsync throws ---");
try {
  const readbackBuf = gpu.buffer.create({
    size: 16,
    usage: "readback",
  });
  readbackBuf.destroy();

  // Mapping a destroyed buffer should throw
  await assertRejects(async () => {
    await readbackBuf.mapAsync(compute.globals.GPUMapMode.READ);
  }, "destroyed buffer: mapAsync throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// p. Double destroy — verify no crash
// ---------------------------------------------------------------------------

console.log("\n--- p. Double destroy ---");
try {
  const buf = gpu.buffer.create({ size: 16, usage: "storageReadWrite" });
  buf.destroy();
  // Second destroy should not crash the process (no-op or harmless throw both pass)
  let secondDestroyOk = false;
  try {
    buf.destroy();
    secondDestroyOk = true; // no-op is fine
  } catch {
    secondDestroyOk = true; // throwing is also acceptable
  }
  assert(secondDestroyOk, "double destroy: second destroy does not crash the process");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected outer error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

if (typeof gpu.device.destroy === "function") {
  gpu.device.destroy();
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nDoe API: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
