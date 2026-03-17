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

const { GPUTextureUsage, GPUShaderStage } = full.globals;

// ---------------------------------------------------------------------------
// a. createSampler with default parameters
// ---------------------------------------------------------------------------

console.log("\n--- a. createSampler with default parameters ---");
try {
  const sampler = device.createSampler();
  assert(sampler != null, "sampler created with defaults");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// b. createSampler with empty descriptor
// ---------------------------------------------------------------------------

console.log("\n--- b. createSampler with empty descriptor ---");
try {
  const sampler = device.createSampler({});
  assert(sampler != null, "sampler created with empty descriptor");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// c. createSampler with explicit filter modes
// ---------------------------------------------------------------------------

console.log("\n--- c. createSampler with explicit filter modes ---");
try {
  const sampler = device.createSampler({
    magFilter: "linear",
    minFilter: "linear",
    mipmapFilter: "linear",
  });
  assert(sampler != null, "sampler with linear filters created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// d. createSampler with nearest filter modes
// ---------------------------------------------------------------------------

console.log("\n--- d. createSampler with nearest filter modes ---");
try {
  const sampler = device.createSampler({
    magFilter: "nearest",
    minFilter: "nearest",
    mipmapFilter: "nearest",
  });
  assert(sampler != null, "sampler with nearest filters created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// e. createSampler with address modes
// ---------------------------------------------------------------------------

console.log("\n--- e. createSampler with address modes ---");
try {
  const sampler = device.createSampler({
    addressModeU: "repeat",
    addressModeV: "repeat",
    addressModeW: "repeat",
  });
  assert(sampler != null, "sampler with repeat address mode created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// f. createSampler with clamp-to-edge address mode
// ---------------------------------------------------------------------------

console.log("\n--- f. createSampler with clamp-to-edge address mode ---");
try {
  const sampler = device.createSampler({
    addressModeU: "clamp-to-edge",
    addressModeV: "clamp-to-edge",
    addressModeW: "clamp-to-edge",
  });
  assert(sampler != null, "sampler with clamp-to-edge address mode created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// g. createSampler with mirror-repeat address mode
// ---------------------------------------------------------------------------

console.log("\n--- g. createSampler with mirror-repeat address mode ---");
try {
  const sampler = device.createSampler({
    addressModeU: "mirror-repeat",
    addressModeV: "mirror-repeat",
  });
  assert(sampler != null, "sampler with mirror-repeat address mode created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// h. createSampler with compare function
// ---------------------------------------------------------------------------

console.log("\n--- h. createSampler with compare function ---");
try {
  const sampler = device.createSampler({
    compare: "less",
  });
  assert(sampler != null, "comparison sampler created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// i. createSampler with lodMinClamp and lodMaxClamp
// ---------------------------------------------------------------------------

console.log("\n--- i. createSampler with LOD clamp ---");
try {
  const sampler = device.createSampler({
    lodMinClamp: 0,
    lodMaxClamp: 4,
  });
  assert(sampler != null, "sampler with LOD clamp created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// j. createSampler with maxAnisotropy
// ---------------------------------------------------------------------------

console.log("\n--- j. createSampler with maxAnisotropy ---");
try {
  const sampler = device.createSampler({
    magFilter: "linear",
    minFilter: "linear",
    maxAnisotropy: 4,
  });
  assert(sampler != null, "sampler with maxAnisotropy created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// k. Sampler in bind group layout (filtering type)
// ---------------------------------------------------------------------------

console.log("\n--- k. Sampler in bind group layout (filtering type) ---");
try {
  const layout = device.createBindGroupLayout({
    entries: [
      {
        binding: 0,
        visibility: GPUShaderStage.COMPUTE,
        sampler: { type: "filtering" },
      },
    ],
  });
  assert(layout != null, "bind group layout with sampler binding created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// l. Sampler in bind group layout (non-filtering type)
// ---------------------------------------------------------------------------

console.log("\n--- l. Sampler in bind group layout (non-filtering type) ---");
try {
  const layout = device.createBindGroupLayout({
    entries: [
      {
        binding: 0,
        visibility: GPUShaderStage.FRAGMENT,
        sampler: { type: "non-filtering" },
      },
    ],
  });
  assert(layout != null, "bind group layout with non-filtering sampler created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// m. Sampler in bind group layout (comparison type)
// ---------------------------------------------------------------------------

console.log("\n--- m. Sampler in bind group layout (comparison type) ---");
try {
  const layout = device.createBindGroupLayout({
    entries: [
      {
        binding: 0,
        visibility: GPUShaderStage.FRAGMENT,
        sampler: { type: "comparison" },
      },
    ],
  });
  assert(layout != null, "bind group layout with comparison sampler created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// n. Sampler used in a bind group
// ---------------------------------------------------------------------------

console.log("\n--- n. Sampler used in a bind group ---");
try {
  const sampler = device.createSampler({ magFilter: "linear", minFilter: "linear" });
  const texture = device.createTexture({
    size: [4, 4, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.TEXTURE_BINDING,
  });
  const view = texture.createView();

  const layout = device.createBindGroupLayout({
    entries: [
      {
        binding: 0,
        visibility: GPUShaderStage.COMPUTE,
        sampler: { type: "filtering" },
      },
      {
        binding: 1,
        visibility: GPUShaderStage.COMPUTE,
        texture: { sampleType: "float", viewDimension: "2d", multisampled: false },
      },
    ],
  });

  const bindGroup = device.createBindGroup({
    layout,
    entries: [
      { binding: 0, resource: sampler },
      { binding: 1, resource: view },
    ],
  });
  assert(bindGroup != null, "bind group with sampler + texture view created");

  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// o. Multiple samplers in a single bind group layout
// ---------------------------------------------------------------------------

console.log("\n--- o. Multiple samplers in a single bind group layout ---");
try {
  const layout = device.createBindGroupLayout({
    entries: [
      {
        binding: 0,
        visibility: GPUShaderStage.FRAGMENT,
        sampler: { type: "filtering" },
      },
      {
        binding: 1,
        visibility: GPUShaderStage.FRAGMENT,
        sampler: { type: "non-filtering" },
      },
    ],
  });
  assert(layout != null, "bind group layout with two sampler bindings created");

  const samplerA = device.createSampler({ magFilter: "linear", minFilter: "linear" });
  const samplerB = device.createSampler({ magFilter: "nearest", minFilter: "nearest" });
  const bindGroup = device.createBindGroup({
    layout,
    entries: [
      { binding: 0, resource: samplerA },
      { binding: 1, resource: samplerB },
    ],
  });
  assert(bindGroup != null, "bind group with two different samplers created");
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

console.log(`\nSampler integration: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
