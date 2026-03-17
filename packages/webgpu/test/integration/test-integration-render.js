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

const { GPUTextureUsage, GPUBufferUsage, GPUShaderStage } = full.globals;

// ---------------------------------------------------------------------------
// a. createShaderModule with vertex WGSL
// ---------------------------------------------------------------------------

console.log("\n--- a. createShaderModule with vertex WGSL ---");
try {
  const vertexShader = device.createShaderModule({
    code: `
      @vertex
      fn main(@builtin(vertex_index) vid: u32) -> @builtin(position) vec4f {
        var pos = array<vec2f, 3>(
          vec2f( 0.0,  0.5),
          vec2f(-0.5, -0.5),
          vec2f( 0.5, -0.5),
        );
        return vec4f(pos[vid], 0.0, 1.0);
      }
    `,
  });
  assert(vertexShader != null, "vertex shader module created");
  assert(typeof vertexShader.destroy === "function", "vertex shader has destroy method");
  vertexShader.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// b. createShaderModule with fragment WGSL
// ---------------------------------------------------------------------------

console.log("\n--- b. createShaderModule with fragment WGSL ---");
try {
  const fragmentShader = device.createShaderModule({
    code: `
      @fragment
      fn main() -> @location(0) vec4f {
        return vec4f(1.0, 0.0, 0.0, 1.0);
      }
    `,
  });
  assert(fragmentShader != null, "fragment shader module created");
  fragmentShader.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// c. createShaderModule with combined vertex + fragment WGSL
// ---------------------------------------------------------------------------

console.log("\n--- c. createShaderModule with combined vertex + fragment WGSL ---");
let combinedShader = null;
try {
  combinedShader = device.createShaderModule({
    code: `
      @vertex
      fn vs_main(@builtin(vertex_index) vid: u32) -> @builtin(position) vec4f {
        var pos = array<vec2f, 3>(
          vec2f( 0.0,  0.5),
          vec2f(-0.5, -0.5),
          vec2f( 0.5, -0.5),
        );
        return vec4f(pos[vid], 0.0, 1.0);
      }

      @fragment
      fn fs_main() -> @location(0) vec4f {
        return vec4f(0.0, 1.0, 0.0, 1.0);
      }
    `,
  });
  assert(combinedShader != null, "combined vertex+fragment shader module created");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// d. createTexture for render target
// ---------------------------------------------------------------------------

console.log("\n--- d. createTexture for render target ---");
let renderTarget = null;
try {
  renderTarget = device.createTexture({
    size: [64, 64, 1],
    format: "rgba8unorm",
    usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
  });
  assert(renderTarget != null, "render target texture created");
  assert(typeof renderTarget.createView === "function", "render target has createView method");
  assert(typeof renderTarget.destroy === "function", "render target has destroy method");
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// e. createView on render target texture
// ---------------------------------------------------------------------------

console.log("\n--- e. createView on render target texture ---");
let renderTargetView = null;
try {
  if (!renderTarget) {
    skip("render target not available");
  } else {
    renderTargetView = renderTarget.createView();
    assert(renderTargetView != null, "render target texture view created");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// f. createRenderPipeline with vertex + fragment modules
// ---------------------------------------------------------------------------

console.log("\n--- f. createRenderPipeline with vertex + fragment modules ---");
let renderPipeline = null;
try {
  if (!combinedShader) {
    skip("combined shader not available");
  } else {
    renderPipeline = device.createRenderPipeline({
      layout: "auto",
      vertex: {
        module: combinedShader,
        entryPoint: "vs_main",
      },
      fragment: {
        module: combinedShader,
        entryPoint: "fs_main",
        targets: [{ format: "rgba8unorm" }],
      },
    });
    assert(renderPipeline != null, "render pipeline created");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// g. createRenderPipeline with primitive topology
// ---------------------------------------------------------------------------

console.log("\n--- g. createRenderPipeline with primitive topology ---");
try {
  if (!combinedShader) {
    skip("combined shader not available");
  } else {
    const pipeline = device.createRenderPipeline({
      layout: "auto",
      vertex: {
        module: combinedShader,
        entryPoint: "vs_main",
      },
      fragment: {
        module: combinedShader,
        entryPoint: "fs_main",
        targets: [{ format: "rgba8unorm" }],
      },
      primitive: {
        topology: "triangle-list",
        frontFace: "ccw",
        cullMode: "none",
      },
    });
    assert(pipeline != null, "render pipeline with primitive config created");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// h. beginRenderPass with color attachment
// ---------------------------------------------------------------------------

console.log("\n--- h. beginRenderPass with color attachment ---");
try {
  if (!renderTargetView) {
    skip("render target view not available");
  } else {
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: renderTargetView,
          clearValue: { r: 0, g: 0, b: 0, a: 1 },
          loadOp: "clear",
          storeOp: "store",
        },
      ],
    });
    assert(pass != null, "render pass encoder created");
    assert(typeof pass.setPipeline === "function", "render pass has setPipeline");
    assert(typeof pass.draw === "function", "render pass has draw");
    assert(typeof pass.end === "function", "render pass has end");
    pass.end();
    const commandBuffer = encoder.finish();
    assert(commandBuffer != null, "command buffer finished after render pass");
    device.queue.submit([commandBuffer]);
    await device.queue.onSubmittedWorkDone();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// i. Render pass with pipeline set and draw call
// ---------------------------------------------------------------------------

console.log("\n--- i. Render pass with pipeline set and draw call ---");
try {
  if (!renderPipeline || !renderTargetView) {
    skip("render pipeline or target view not available");
  } else {
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: renderTargetView,
          clearValue: { r: 0.2, g: 0.4, b: 0.6, a: 1.0 },
          loadOp: "clear",
          storeOp: "store",
        },
      ],
    });
    pass.setPipeline(renderPipeline);
    pass.draw(3); // draw a triangle (3 vertices)
    pass.end();
    const commandBuffer = encoder.finish();
    device.queue.submit([commandBuffer]);
    await device.queue.onSubmittedWorkDone();
    assert(true, "render pass with pipeline + draw completed without error");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// j. Render pass — end() prevents further commands
// ---------------------------------------------------------------------------

console.log("\n--- j. Render pass — end() prevents further commands ---");
try {
  if (!renderTargetView || !renderPipeline) {
    skip("render target view or pipeline not available");
  } else {
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: renderTargetView,
          clearValue: { r: 0, g: 0, b: 0, a: 1 },
        },
      ],
    });
    pass.end();

    let threwAfterEnd = false;
    try {
      pass.setPipeline(renderPipeline);
    } catch {
      threwAfterEnd = true;
    }
    assert(threwAfterEnd, "setPipeline after end() throws");
    // Finish the encoder to keep things consistent
    encoder.finish();
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// k. beginRenderPass without colorAttachments — should throw
// ---------------------------------------------------------------------------

console.log("\n--- k. beginRenderPass without colorAttachments ---");
try {
  const encoder = device.createCommandEncoder();
  let threw = false;
  try {
    encoder.beginRenderPass({ colorAttachments: [] });
  } catch {
    threw = true;
  }
  assert(threw, "beginRenderPass with empty colorAttachments throws");
  // Finish the encoder anyway if possible
  try { encoder.finish(); } catch { /* may fail if encoder is in bad state */ }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// l. createRenderPipeline without fragment targets — should throw
// ---------------------------------------------------------------------------

console.log("\n--- l. createRenderPipeline without fragment targets ---");
try {
  if (!combinedShader) {
    skip("combined shader not available");
  } else {
    let threw = false;
    try {
      device.createRenderPipeline({
        layout: "auto",
        vertex: {
          module: combinedShader,
          entryPoint: "vs_main",
        },
        fragment: {
          module: combinedShader,
          entryPoint: "fs_main",
          targets: [],
        },
      });
    } catch {
      threw = true;
    }
    assert(threw, "createRenderPipeline with empty fragment targets throws");
  }
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// m. Render pipeline with vertex buffers descriptor
// ---------------------------------------------------------------------------

console.log("\n--- m. Render pipeline with vertex buffers descriptor ---");
try {
  const vbShader = device.createShaderModule({
    code: `
      struct VertexOutput {
        @builtin(position) pos: vec4f,
      };

      @vertex
      fn vs_main(@location(0) position: vec2f) -> VertexOutput {
        var out: VertexOutput;
        out.pos = vec4f(position, 0.0, 1.0);
        return out;
      }

      @fragment
      fn fs_main() -> @location(0) vec4f {
        return vec4f(1.0, 0.0, 0.0, 1.0);
      }
    `,
  });

  const pipeline = device.createRenderPipeline({
    layout: "auto",
    vertex: {
      module: vbShader,
      entryPoint: "vs_main",
      buffers: [
        {
          arrayStride: 8,
          attributes: [
            { shaderLocation: 0, offset: 0, format: "float32x2" },
          ],
        },
      ],
    },
    fragment: {
      module: vbShader,
      entryPoint: "fs_main",
      targets: [{ format: "rgba8unorm" }],
    },
  });
  assert(pipeline != null, "render pipeline with vertex buffer layout created");
  vbShader.destroy();
} catch (err) {
  failed++;
  console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

if (renderTarget) { try { renderTarget.destroy(); } catch { /* ok */ } }
if (combinedShader) { try { combinedShader.destroy(); } catch { /* ok */ } }
if (typeof device.destroy === "function") { device.destroy(); }

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nRender integration: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exit(failed > 0 ? 1 : 0);
