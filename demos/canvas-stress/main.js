// Canvas stress demo entry point.

const SHADER_URL = new URL("./canvas-stress.wgsl", import.meta.url);

const canvas = document.getElementById("c");
const statusEl = document.getElementById("status");
const fpsEl = document.getElementById("fps");
const countInput = document.getElementById("count");
const countVal = document.getElementById("count-val");
const sizeInput = document.getElementById("size");

let device = null;
let context = null;
let pipeline = null;
let frameUBO = null;
let instanceBuf = null;
let bindGroup = null;
let currentCount = 0;
let lastFpsTime = performance.now();
let fpsAcc = 0;
let fpsCount = 0;
let startTime = performance.now();

async function setup() {
  if (!navigator.gpu) {
    statusEl.textContent = "WebGPU not available";
    return;
  }
  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) {
    statusEl.textContent = "no WebGPU adapter";
    return;
  }
  device = await adapter.requestDevice();
  context = canvas.getContext("webgpu");
  const format = navigator.gpu.getPreferredCanvasFormat();
  context.configure({ device, format, alphaMode: "premultiplied" });

  const shader = await (await fetch(SHADER_URL)).text();
  const module = device.createShaderModule({ code: shader });

  const bgLayout = device.createBindGroupLayout({
    entries: [
      { binding: 0, visibility: GPUShaderStage.VERTEX, buffer: { type: "uniform" } },
      { binding: 1, visibility: GPUShaderStage.VERTEX, buffer: { type: "read-only-storage" } },
    ],
  });

  pipeline = device.createRenderPipeline({
    layout: device.createPipelineLayout({ bindGroupLayouts: [bgLayout] }),
    vertex: { module, entryPoint: "vs_main" },
    fragment: {
      module,
      entryPoint: "fs_main",
      targets: [{
        format,
        blend: {
          color: { srcFactor: "one", dstFactor: "one-minus-src-alpha", operation: "add" },
          alpha: { srcFactor: "one", dstFactor: "one-minus-src-alpha", operation: "add" },
        },
      }],
    },
    primitive: { topology: "triangle-strip" },
  });

  frameUBO = device.createBuffer({
    size: 16,
    usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
  });

  buildInstances(Number(countInput.value), Number(sizeInput.value), bgLayout);
  statusEl.textContent = "running";
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);
  requestAnimationFrame(frame);
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
}

function buildInstances(count, baseSize, bgLayout) {
  currentCount = count;
  countVal.textContent = String(count);
  // Instance layout matches Instance struct in shader:
  //   seed: vec2f, size: vec2f, corner: f32, hue: f32, _pad0: vec2f
  // Total 8 floats = 32 bytes (std430 alignment of struct containing vec2f is 8).
  const data = new Float32Array(count * 8);
  for (let i = 0; i < count; i = i + 1) {
    const o = i * 8;
    data[o + 0] = Math.random();
    data[o + 1] = Math.random();
    const sx = baseSize * (0.6 + Math.random() * 0.8);
    const sy = baseSize * (0.6 + Math.random() * 0.8);
    data[o + 2] = sx;
    data[o + 3] = sy;
    data[o + 4] = Math.min(sx, sy) * (0.3 + Math.random() * 0.4);
    data[o + 5] = Math.random();
    data[o + 6] = 0;
    data[o + 7] = 0;
  }

  if (instanceBuf) instanceBuf.destroy();
  instanceBuf = device.createBuffer({
    size: data.byteLength,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    mappedAtCreation: true,
  });
  new Float32Array(instanceBuf.getMappedRange()).set(data);
  instanceBuf.unmap();

  bindGroup = device.createBindGroup({
    layout: bgLayout,
    entries: [
      { binding: 0, resource: { buffer: frameUBO } },
      { binding: 1, resource: { buffer: instanceBuf } },
    ],
  });
}

function frame(now) {
  if (!device) return;
  const dt = now - lastFpsTime;
  lastFpsTime = now;
  fpsAcc = fpsAcc + dt;
  fpsCount = fpsCount + 1;
  if (fpsAcc > 250) {
    fpsEl.textContent = (1000 * fpsCount / fpsAcc).toFixed(0);
    fpsAcc = 0; fpsCount = 0;
  }

  const time = (now - startTime) / 1000;
  const ubo = new Float32Array(4);
  ubo[0] = canvas.width;
  ubo[1] = canvas.height;
  ubo[2] = time;
  ubo[3] = currentCount;
  device.queue.writeBuffer(frameUBO, 0, ubo);

  const encoder = device.createCommandEncoder();
  const pass = encoder.beginRenderPass({
    colorAttachments: [{
      view: context.getCurrentTexture().createView(),
      loadOp: "clear",
      storeOp: "store",
      clearValue: { r: 0.031, g: 0.035, b: 0.063, a: 1 },
    }],
  });
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.draw(4, currentCount, 0, 0);
  pass.end();
  device.queue.submit([encoder.finish()]);

  requestAnimationFrame(frame);
}

// Rebuild instance buffer when count or size changes.
let rebuildTimer = null;
function scheduleRebuild() {
  if (rebuildTimer) clearTimeout(rebuildTimer);
  rebuildTimer = setTimeout(() => {
    const bgLayout = pipeline.getBindGroupLayout(0);
    buildInstances(Number(countInput.value), Number(sizeInput.value), bgLayout);
  }, 120);
}
countInput.addEventListener("input", scheduleRebuild);
sizeInput.addEventListener("input", scheduleRebuild);

setup();
