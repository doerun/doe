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

function isUnsupportedError(err) {
  return /unsupported|not supported|not implemented|not available|not wired|is not a function|unavailable/i.test(err?.message ?? String(err));
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

const { GPUTextureUsage, GPUBufferUsage } = full.globals;
const SHOULD_SKIP_TEXTURE_COPY =
  process.platform === "linux"
  && full.providerInfo?.().libraryFlavor === "doe-dropin";

// ---------------------------------------------------------------------------
// a. createTexture with rgba8unorm format
// ---------------------------------------------------------------------------

console.log("\n--- a. createTexture with rgba8unorm format ---");
try {
  const texture = device.createTexture({
    size: [16, 16, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.TEXTURE_BINDING,
  });
  assert(texture != null, "rgba8unorm texture created");
  assert(typeof texture.createView === "function", "texture has createView");
  assert(typeof texture.destroy === "function", "texture has destroy");
  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// b. createTexture with various formats
// ---------------------------------------------------------------------------

console.log("\n--- b. createTexture with various formats ---");
{
  const formats = ["rgba8unorm", "rgba16float", "r32float", "rg32float", "rgba32float"];
  for (const format of formats) {
    try {
      const texture = device.createTexture({
        size: [4, 4, 1],
        format,
        usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.TEXTURE_BINDING,
      });
      assert(texture != null, `createTexture with format ${format} succeeds`);
      texture.destroy();
    } catch (err) {
      failed++;
      console.error(`  FAIL: createTexture with format ${format}: ${err?.message ?? err}`);
    }
  }
}

// ---------------------------------------------------------------------------
// c. createTexture with RENDER_ATTACHMENT usage
// ---------------------------------------------------------------------------

console.log("\n--- c. createTexture with RENDER_ATTACHMENT usage ---");
try {
  const texture = device.createTexture({
    size: [32, 32, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
  });
  assert(texture != null, "render attachment texture created");
  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// d. createTexture with STORAGE_BINDING usage
// ---------------------------------------------------------------------------

console.log("\n--- d. createTexture with STORAGE_BINDING usage ---");
try {
  const texture = device.createTexture({
    size: [8, 8, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.STORAGE_BINDING | GPUTextureUsage.COPY_SRC,
  });
  assert(texture != null, "storage binding texture created");
  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// e. createView — default parameters
// ---------------------------------------------------------------------------

console.log("\n--- e. createView — default parameters ---");
try {
  const texture = device.createTexture({
    size: [16, 16, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.TEXTURE_BINDING,
  });
  const view = texture.createView();
  assert(view != null, "default texture view created");
  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// f. texture.destroy() — double destroy does not crash
// ---------------------------------------------------------------------------

console.log("\n--- f. texture.destroy() — double destroy does not crash ---");
try {
  const texture = device.createTexture({
    size: [4, 4, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.TEXTURE_BINDING,
  });
  texture.destroy();
  let secondDestroyOk = false;
  try {
    texture.destroy();
    secondDestroyOk = true;
  } catch {
    secondDestroyOk = true; // throwing is also acceptable
  }
  assert(secondDestroyOk, "double destroy does not crash the process");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// g. createTexture with array size variants
// ---------------------------------------------------------------------------

console.log("\n--- g. createTexture with array size variants ---");
try {
  // size as [width]
  const t1 = device.createTexture({
    size: [32],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST,
    dimension: "1d",
  });
  assert(t1 != null, "texture with 1D size array created");
  t1.destroy();

  // size as [width, height]
  const t2 = device.createTexture({
    size: [16, 16],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST,
  });
  assert(t2 != null, "texture with 2-element size array created");
  t2.destroy();

  // size as { width, height, depthOrArrayLayers }
  const t3 = device.createTexture({
    size: { width: 8, height: 8, depthOrArrayLayers: 1 },
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST,
  });
  assert(t3 != null, "texture with object size created");
  t3.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// h. createTexture — invalid usage (0) should throw
// ---------------------------------------------------------------------------

console.log("\n--- h. createTexture — invalid usage (0) should throw ---");
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
// i. createTexture — invalid size (0 width) should throw
// ---------------------------------------------------------------------------

console.log("\n--- i. createTexture — invalid size (0 width) should throw ---");
try {
  let threw = false;
  try {
    device.createTexture({
      size: [0, 4, 1],
      format: "rgba8unorm",
      usage: GPUTextureUsage.COPY_DST,
    });
  } catch {
    threw = true;
  }
  assert(threw, "createTexture with 0 width throws");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// j. copyBufferToTexture — write pixel data into a texture
// ---------------------------------------------------------------------------

console.log("\n--- j. copyBufferToTexture ---");
if (SHOULD_SKIP_TEXTURE_COPY) {
  skip("texture copy paths are not yet wired on the Linux Doe drop-in surface");
} else try {
  const WIDTH = 4;
  const HEIGHT = 4;
  const BYTES_PER_PIXEL = 4; // rgba8unorm
  const dataSize = WIDTH * HEIGHT * BYTES_PER_PIXEL;
  const pixelData = new Uint8Array(dataSize);
  for (let i = 0; i < dataSize; i += BYTES_PER_PIXEL) {
    pixelData[i] = 255;     // R
    pixelData[i + 1] = 0;   // G
    pixelData[i + 2] = 0;   // B
    pixelData[i + 3] = 255; // A
  }

  const srcBuffer = device.createBuffer({
    size: dataSize,
    usage: GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(srcBuffer, 0, pixelData);

  const texture = device.createTexture({
    size: [WIDTH, HEIGHT, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.COPY_SRC,
  });

  const encoder = device.createCommandEncoder();
  encoder.copyBufferToTexture(
    { buffer: srcBuffer, bytesPerRow: WIDTH * BYTES_PER_PIXEL, rowsPerImage: HEIGHT },
    { texture: texture },
    { width: WIDTH, height: HEIGHT },
  );
  device.queue.submit([encoder.finish()]);
  await device.queue.onSubmittedWorkDone();
  assert(true, "copyBufferToTexture completed without error");

  srcBuffer.destroy();
  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// k. copyTextureToBuffer — read pixel data back from a texture
// ---------------------------------------------------------------------------

console.log("\n--- k. copyTextureToBuffer ---");
if (SHOULD_SKIP_TEXTURE_COPY) {
  skip("texture copy paths are not yet wired on the Linux Doe drop-in surface");
} else try {
  const WIDTH = 4;
  const HEIGHT = 4;
  const BYTES_PER_PIXEL = 4;
  const dataSize = WIDTH * HEIGHT * BYTES_PER_PIXEL;
  const pixelData = new Uint8Array(dataSize);
  for (let i = 0; i < dataSize; i += BYTES_PER_PIXEL) {
    pixelData[i] = 0;
    pixelData[i + 1] = 255;
    pixelData[i + 2] = 0;
    pixelData[i + 3] = 255;
  }

  const uploadBuffer = device.createBuffer({
    size: dataSize,
    usage: GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(uploadBuffer, 0, pixelData);

  const texture = device.createTexture({
    size: [WIDTH, HEIGHT, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.COPY_SRC,
  });

  // Upload to texture
  const encoder1 = device.createCommandEncoder();
  encoder1.copyBufferToTexture(
    { buffer: uploadBuffer, bytesPerRow: WIDTH * BYTES_PER_PIXEL, rowsPerImage: HEIGHT },
    { texture: texture },
    { width: WIDTH, height: HEIGHT },
  );
  device.queue.submit([encoder1.finish()]);
  await device.queue.onSubmittedWorkDone();

  // Read back from texture
  const readbackBuffer = device.createBuffer({
    size: dataSize,
    usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });

  const encoder2 = device.createCommandEncoder();
  encoder2.copyTextureToBuffer(
    { texture: texture },
    { buffer: readbackBuffer, bytesPerRow: WIDTH * BYTES_PER_PIXEL, rowsPerImage: HEIGHT },
    { width: WIDTH, height: HEIGHT },
  );
  device.queue.submit([encoder2.finish()]);
  await device.queue.onSubmittedWorkDone();

  await readbackBuffer.mapAsync(full.globals.GPUMapMode.READ);
  const result = new Uint8Array(readbackBuffer.getMappedRange(0, dataSize));

  // Verify first pixel is green (0, 255, 0, 255)
  assert(result[0] === 0, "readback pixel R = 0");
  assert(result[1] === 255, "readback pixel G = 255");
  assert(result[2] === 0, "readback pixel B = 0");
  assert(result[3] === 255, "readback pixel A = 255");

  readbackBuffer.unmap();
  uploadBuffer.destroy();
  texture.destroy();
  readbackBuffer.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// l. copyTextureToTexture — copy pixels between textures
// ---------------------------------------------------------------------------

console.log("\n--- l. copyTextureToTexture ---");
if (SHOULD_SKIP_TEXTURE_COPY) {
  skip("texture copy paths are not yet wired on the Linux Doe drop-in surface");
} else try {
  const WIDTH = 4;
  const HEIGHT = 4;
  const BYTES_PER_PIXEL = 4;
  const dataSize = WIDTH * HEIGHT * BYTES_PER_PIXEL;
  const pixelData = new Uint8Array(dataSize);
  for (let i = 0; i < dataSize; i += BYTES_PER_PIXEL) {
    pixelData[i] = 32;
    pixelData[i + 1] = 64;
    pixelData[i + 2] = 128;
    pixelData[i + 3] = 255;
  }

  const uploadBuffer = device.createBuffer({
    size: dataSize,
    usage: GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(uploadBuffer, 0, pixelData);

  const srcTexture = device.createTexture({
    size: [WIDTH, HEIGHT, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.COPY_SRC,
  });
  const dstTexture = device.createTexture({
    size: [WIDTH, HEIGHT, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.COPY_SRC,
  });

  const encoder1 = device.createCommandEncoder();
  encoder1.copyBufferToTexture(
    { buffer: uploadBuffer, bytesPerRow: WIDTH * BYTES_PER_PIXEL, rowsPerImage: HEIGHT },
    { texture: srcTexture },
    { width: WIDTH, height: HEIGHT },
  );
  device.queue.submit([encoder1.finish()]);
  await device.queue.onSubmittedWorkDone();

  const encoder2 = device.createCommandEncoder();
  if (typeof encoder2.copyTextureToTexture !== "function") {
    skip("copyTextureToTexture is not exposed on this backend");
  } else {
    try {
      encoder2.copyTextureToTexture(
        { texture: srcTexture },
        { texture: dstTexture },
        { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
      );

      const readbackBuffer = device.createBuffer({
        size: dataSize,
        usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
      });

      encoder2.copyTextureToBuffer(
        { texture: dstTexture },
        { buffer: readbackBuffer, bytesPerRow: WIDTH * BYTES_PER_PIXEL, rowsPerImage: HEIGHT },
        { width: WIDTH, height: HEIGHT },
      );
      device.queue.submit([encoder2.finish()]);
      await device.queue.onSubmittedWorkDone();

      await readbackBuffer.mapAsync(full.globals.GPUMapMode.READ);
      const result = new Uint8Array(readbackBuffer.getMappedRange(0, dataSize));
      assert(result[0] === 32, "copied pixel R = 32");
      assert(result[1] === 64, "copied pixel G = 64");
      assert(result[2] === 128, "copied pixel B = 128");
      assert(result[3] === 255, "copied pixel A = 255");
      readbackBuffer.unmap();
      readbackBuffer.destroy();
    } catch (err) {
      if (isUnsupportedError(err)) {
        skip(`copyTextureToTexture unavailable: ${err?.message ?? err}`);
      } else {
        failed++;
        console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
      }
    }
  }

  uploadBuffer.destroy();
  srcTexture.destroy();
  dstTexture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// m. createTexture with mipLevelCount
// ---------------------------------------------------------------------------

console.log("\n--- m. createTexture with mipLevelCount ---");
try {
  // 16x16 supports up to 5 mip levels (16, 8, 4, 2, 1)
  const texture = device.createTexture({
    size: [16, 16, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST,
    mipLevelCount: 5,
  });
  assert(texture != null, "texture with mipLevelCount=5 created");
  texture.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// n. createTexture — dimension "2d" (default)
// ---------------------------------------------------------------------------

console.log("\n--- n. createTexture — dimension 2d ---");
try {
  const texture = device.createTexture({
    size: [8, 8, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.COPY_DST,
    dimension: "2d",
  });
  assert(texture != null, "texture with explicit dimension 2d created");
  texture.destroy();
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

console.log(`\nTexture integration: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
