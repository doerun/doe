import * as full from "../../src/index.js";

let passed = 0, failed = 0, skipped = 0;

function assert(condition, msg) {
  if (condition) {
    passed++;
  } else {
    failed++;
    console.error(`  FAIL: ${msg}`);
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

const { GPUBufferUsage, GPUTextureUsage } = full.globals;
const SIZE = 32;

// ---------------------------------------------------------------------------
// Render auto layout
// ---------------------------------------------------------------------------

console.log("\n--- render auto layout getBindGroupLayout ---");
try {
  const shader = device.createShaderModule({
    code: `
      struct ColorUniform {
        color: vec4f,
      };

      @group(0) @binding(0) var<uniform> colorUniform: ColorUniform;

      struct VertexOutput {
        @builtin(position) position: vec4f,
      };

      @vertex
      fn vs_main(@builtin(vertex_index) vertexIndex: u32) -> VertexOutput {
        var positions = array<vec2f, 3>(
          vec2f( 0.0,  0.6),
          vec2f(-0.6, -0.6),
          vec2f( 0.6, -0.6),
        );
        var out: VertexOutput;
        out.position = vec4f(positions[vertexIndex], 0.0, 1.0);
        return out;
      }

      @fragment
      fn fs_main() -> @location(0) vec4f {
        return colorUniform.color;
      }
    `,
  });

  const renderTarget = device.createTexture({
    size: [SIZE, SIZE, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
  });
  const renderTargetView = renderTarget.createView();
  const pipeline = device.createRenderPipeline({
    layout: "auto",
    vertex: {
      module: shader,
      entryPoint: "vs_main",
    },
    fragment: {
      module: shader,
      entryPoint: "fs_main",
      targets: [{ format: "rgba8unorm" }],
    },
    primitive: {
      topology: "triangle-list",
      frontFace: "ccw",
      cullMode: "none",
    },
  });

  const layout0 = pipeline.getBindGroupLayout(0);
  assert(layout0 != null, "render pipeline auto layout exposes bind group layout 0");
  assert(pipeline.getBindGroupLayout(0) === layout0, "render pipeline caches bind group layout 0");

  const uniformBuffer = device.createBuffer({
    size: 16,
    usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(uniformBuffer, 0, new Float32Array([0.0, 1.0, 0.0, 1.0]));
  const bindGroup = device.createBindGroup({
    layout: layout0,
    entries: [
      {
        binding: 0,
        resource: { buffer: uniformBuffer },
      },
    ],
  });

  const encoder = device.createCommandEncoder();
  const pass = encoder.beginRenderPass({
    colorAttachments: [{
      view: renderTargetView,
      clearValue: { r: 0, g: 0, b: 0, a: 1 },
      loadOp: "clear",
      storeOp: "store",
    }],
  });
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.draw(3);
  pass.end();
  device.queue.submit([encoder.finish()]);
  await device.queue.onSubmittedWorkDone();
  assert(true, "render pass submitted successfully with auto-layout bind group");

  renderTarget.destroy();
  uniformBuffer.destroy();
  shader.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

if (typeof device?.destroy === "function") {
  try { device.destroy(); } catch { /* ok */ }
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nRender auto layout: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
