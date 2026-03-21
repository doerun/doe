import * as full from "../../src/node-runtime.js";

let passed = 0;
let failed = 0;
let skipped = 0;

function assert(condition, message) {
  if (condition) {
    passed += 1;
  } else {
    failed += 1;
    console.error(`  FAIL: ${message}`);
  }
}

function skip(message) {
  skipped += 1;
  console.log(`  SKIP: ${message}`);
}

if (process.platform !== "darwin") {
  skip("native Metal GPUCanvasContext is macOS-only");
  console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`);
  process.exit(0);
}

let gpu;
let adapter;
let device;
try {
  gpu = full.create();
  adapter = await gpu.requestAdapter();
  device = await adapter.requestDevice();
} catch (error) {
  console.error(`Setup failed: ${error?.message ?? error}`);
  process.exit(1);
}

console.log("\n--- a. exported canvas surface API ---");
assert(typeof full.createCanvasContext === "function", "createCanvasContext export exists");

console.log("\n--- b. configure GPUCanvasContext ---");
const canvas = { width: 64, height: 64 };
let context = null;
try {
  context = full.createCanvasContext(canvas);
  assert(context?.canvas === canvas, "context.canvas returns the original canvas object");
  const preferredFormat = typeof gpu.getPreferredCanvasFormat === "function"
    ? gpu.getPreferredCanvasFormat()
    : "bgra8unorm";
  context.configure({
    device,
    format: preferredFormat,
    alphaMode: "opaque",
  });
  const configuration = context.getConfiguration();
  assert(configuration?.device === device, "getConfiguration().device matches");
  assert(configuration?.format === preferredFormat, "getConfiguration().format matches");
  assert(configuration?.alphaMode === "opaque", "getConfiguration().alphaMode matches");
} catch (error) {
  failed += 1;
  console.error(`  FAIL (unexpected error): ${error?.message ?? error}`);
}

console.log("\n--- c. acquire surface texture and present a clear ---");
try {
  const texture = context.getCurrentTexture();
  assert(texture != null, "getCurrentTexture returns a texture");
  assert(texture.width === 64, "surface texture width matches canvas");
  assert(texture.height === 64, "surface texture height matches canvas");

  const view = texture.createView();
  assert(view != null, "surface texture view created");

  const encoder = device.createCommandEncoder();
  const pass = encoder.beginRenderPass({
    colorAttachments: [
      {
        view,
        clearValue: { r: 0.25, g: 0.5, b: 0.75, a: 1.0 },
        loadOp: "clear",
        storeOp: "store",
      },
    ],
  });
  pass.end();
  device.queue.submit([encoder.finish()]);
  await device.queue.onSubmittedWorkDone();

  const nextTexture = context.getCurrentTexture();
  assert(nextTexture != null, "surface texture can be reacquired after present");
} catch (error) {
  failed += 1;
  console.error(`  FAIL (unexpected error): ${error?.message ?? error}`);
}

console.log("\n--- d. unconfigure ---");
try {
  context.unconfigure();
  assert(context.getConfiguration() === null, "getConfiguration() is null after unconfigure");
} catch (error) {
  failed += 1;
  console.error(`  FAIL (unexpected error): ${error?.message ?? error}`);
}

device.destroy?.();

console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exitCode = failed > 0 ? 1 : 0;
