// Gaussian splat viewer — browser entry point.
//
// Wires together the .splat loader, CPU depth sort in a worker, WebGPU
// rendering of the instanced billboard pipeline, and an optional webcam
// overlay. Uses the browser's native WebGPU API; the `doe-gpu` package
// powers the underlying runtime when users install Doe as their WebGPU
// implementation, but the demo does not require it at call-time.

import { parseSplatBuffer, fetchAndParseSplat } from "./splat-loader.js";
import { createOrbitCamera, multiply4x4 } from "./camera.js";

const ALPHA_CLEAR = [0.031, 0.035, 0.063, 1.0];
const SHADER_URL = new URL("./splat-render.wgsl", import.meta.url);

const canvas = document.getElementById("c");
const statusEl = document.getElementById("status");
const hudCount = document.getElementById("hud-count");
const hudFps = document.getElementById("hud-fps");
const hudSort = document.getElementById("hud-sort");
const fileInput = document.getElementById("file");
const urlInput = document.getElementById("url");
const loadUrlBtn = document.getElementById("load-url");
const videoToggleBtn = document.getElementById("video-toggle");
const videoEl = document.getElementById("video");

let gpuState = null;
let splats = null;
let sortedIndices = null;
let sortWorker = null;
let sortGeneration = 0;
let sortInFlight = false;
let pendingSortRequest = null;
let lastViewMatrix = null;
let fpsAcc = 0;
let fpsCount = 0;
let fpsLastTime = performance.now();
let lastSortMs = 0;
let videoStream = null;

const camera = createOrbitCamera();
camera.attach(canvas);

async function setup() {
  if (!navigator.gpu) {
    setStatus("WebGPU not available in this browser; enable it and reload");
    return;
  }
  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) {
    setStatus("no WebGPU adapter available");
    return;
  }
  const device = await adapter.requestDevice();
  const context = canvas.getContext("webgpu");
  const format = navigator.gpu.getPreferredCanvasFormat();
  context.configure({ device, format, alphaMode: "premultiplied" });

  const shaderSource = await (await fetch(SHADER_URL)).text();
  const module = device.createShaderModule({ code: shaderSource });

  const bindGroupLayout = device.createBindGroupLayout({
    entries: [
      { binding: 0, visibility: GPUShaderStage.VERTEX, buffer: { type: "uniform" } },
      { binding: 1, visibility: GPUShaderStage.VERTEX, buffer: { type: "read-only-storage" } },
      { binding: 2, visibility: GPUShaderStage.VERTEX, buffer: { type: "read-only-storage" } },
      { binding: 3, visibility: GPUShaderStage.VERTEX, buffer: { type: "read-only-storage" } },
      { binding: 4, visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT, buffer: { type: "read-only-storage" } },
      { binding: 5, visibility: GPUShaderStage.VERTEX, buffer: { type: "read-only-storage" } },
    ],
  });

  const pipeline = device.createRenderPipeline({
    layout: device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] }),
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

  const frameUBO = device.createBuffer({
    size: 4 * (16 + 16 + 4 + 4),  // 2 mat4x4f + vec2f + vec2f (padded to 16B each)
    usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
  });

  gpuState = { device, context, format, module, pipeline, bindGroupLayout, frameUBO };

  sortWorker = new Worker(new URL("./splat-sort-worker.js", import.meta.url), { type: "module" });
  sortWorker.addEventListener("message", onWorkerMessage);

  setStatus("ready — drop a .splat file or paste a URL");

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

function setStatus(msg) {
  statusEl.textContent = msg;
}

async function loadArrayBuffer(buf) {
  try {
    const parsed = parseSplatBuffer(buf);
    adoptSplats(parsed);
  } catch (err) {
    console.error(err);
    setStatus(`load failed: ${err.message}`);
  }
}

async function loadUrl(url) {
  try {
    setStatus(`loading ${url} …`);
    const parsed = await fetchAndParseSplat(url, (received, total) => {
      setStatus(`loading ${url} … ${(received / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB`);
    });
    adoptSplats(parsed);
  } catch (err) {
    console.error(err);
    setStatus(`load failed: ${err.message}`);
  }
}

function adoptSplats(parsed) {
  splats = parsed;

  const device = gpuState.device;

  // Upload position / scale / rotation / color as planar storage buffers.
  // Pad vec3f fields to vec4f per std430 layout; the shader reads vec3f but
  // each element is 16-byte aligned in an array<vec3f>.
  const positionsPadded = pad3To4(parsed.positions, parsed.count);
  const scalesPadded = pad3To4(parsed.scales, parsed.count);
  const colorsF32 = new Float32Array(parsed.count * 4);
  for (let i = 0; i < parsed.count; i = i + 1) {
    colorsF32[i * 4 + 0] = parsed.colors[i * 4 + 0] / 255;
    colorsF32[i * 4 + 1] = parsed.colors[i * 4 + 1] / 255;
    colorsF32[i * 4 + 2] = parsed.colors[i * 4 + 2] / 255;
    colorsF32[i * 4 + 3] = parsed.colors[i * 4 + 3] / 255;
  }

  gpuState.positionsBuf = uploadStorage(device, positionsPadded);
  gpuState.scalesBuf = uploadStorage(device, scalesPadded);
  gpuState.rotationsBuf = uploadStorage(device, parsed.rotations);
  gpuState.colorsBuf = uploadStorage(device, colorsF32);
  gpuState.sortOrderBuf = device.createBuffer({
    size: Math.max(16, parsed.count * 4),
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
  });

  gpuState.bindGroup = device.createBindGroup({
    layout: gpuState.bindGroupLayout,
    entries: [
      { binding: 0, resource: { buffer: gpuState.frameUBO } },
      { binding: 1, resource: { buffer: gpuState.positionsBuf } },
      { binding: 2, resource: { buffer: gpuState.scalesBuf } },
      { binding: 3, resource: { buffer: gpuState.rotationsBuf } },
      { binding: 4, resource: { buffer: gpuState.colorsBuf } },
      { binding: 5, resource: { buffer: gpuState.sortOrderBuf } },
    ],
  });

  // Initial identity sort order so the first frame renders without waiting for
  // the worker.
  const identity = new Uint32Array(parsed.count);
  for (let i = 0; i < parsed.count; i = i + 1) identity[i] = i;
  gpuState.device.queue.writeBuffer(gpuState.sortOrderBuf, 0, identity);
  sortedIndices = identity;

  // Bounds & recenter.
  const bounds = computeBounds(parsed.positions, parsed.count);
  camera.recenter(bounds.centroid, bounds.radius);

  // Hand positions to the worker so it can sort.
  sortWorker.postMessage({
    kind: "splats",
    positions: parsed.positions.buffer.slice(0),
  });

  hudCount.textContent = String(parsed.count);
  setStatus(`loaded ${parsed.count.toLocaleString()} splats`);
}

function uploadStorage(device, floatArray) {
  const buffer = device.createBuffer({
    size: floatArray.byteLength,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    mappedAtCreation: true,
  });
  new Float32Array(buffer.getMappedRange()).set(floatArray);
  buffer.unmap();
  return buffer;
}

function pad3To4(src, count) {
  const dst = new Float32Array(count * 4);
  for (let i = 0; i < count; i = i + 1) {
    dst[i * 4 + 0] = src[i * 3 + 0];
    dst[i * 4 + 1] = src[i * 3 + 1];
    dst[i * 4 + 2] = src[i * 3 + 2];
    dst[i * 4 + 3] = 0;
  }
  return dst;
}

function computeBounds(positions, count) {
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < count; i = i + 1) {
    cx = cx + positions[i * 3 + 0];
    cy = cy + positions[i * 3 + 1];
    cz = cz + positions[i * 3 + 2];
  }
  cx = cx / count; cy = cy / count; cz = cz / count;
  let r2 = 0;
  for (let i = 0; i < count; i = i + 1) {
    const dx = positions[i * 3 + 0] - cx;
    const dy = positions[i * 3 + 1] - cy;
    const dz = positions[i * 3 + 2] - cz;
    const d = dx * dx + dy * dy + dz * dz;
    if (d > r2) r2 = d;
  }
  return { centroid: [cx, cy, cz], radius: Math.sqrt(r2) };
}

function scheduleSort(viewMatrix) {
  if (!splats) return;
  if (sortInFlight) {
    pendingSortRequest = viewMatrix.slice(0);
    return;
  }
  sortGeneration = sortGeneration + 1;
  sortInFlight = true;
  const t0 = performance.now();
  sortWorker.postMessage({
    kind: "sort",
    view: viewMatrix,
    generation: sortGeneration,
    _t0: t0,
  });
}

function onWorkerMessage(ev) {
  const msg = ev.data;
  if (msg.kind === "splats-ready") {
    scheduleSort(camera.viewMatrix());
    return;
  }
  if (msg.kind === "sorted") {
    sortInFlight = false;
    if (msg.generation === sortGeneration) {
      const indices = new Uint32Array(msg.indices);
      gpuState.device.queue.writeBuffer(gpuState.sortOrderBuf, 0, indices);
      sortedIndices = indices;
    }
    if (pendingSortRequest) {
      const v = pendingSortRequest;
      pendingSortRequest = null;
      scheduleSort(v);
    }
  }
}

function frame(now) {
  if (!gpuState) {
    requestAnimationFrame(frame);
    return;
  }
  const dt = now - fpsLastTime;
  fpsLastTime = now;
  fpsAcc = fpsAcc + dt;
  fpsCount = fpsCount + 1;
  if (fpsAcc > 250) {
    hudFps.textContent = (1000 * fpsCount / fpsAcc).toFixed(0);
    fpsAcc = 0; fpsCount = 0;
  }

  const view = camera.viewMatrix();
  const aspect = canvas.width / canvas.height;
  const proj = camera.projectionMatrix(aspect);

  // Re-sort on view change.
  if (splats && !sortInFlight) {
    if (!lastViewMatrix || viewChanged(lastViewMatrix, view)) {
      lastViewMatrix = new Float32Array(view);
      scheduleSort(view);
    }
  }

  if (splats) {
    const focalX = proj[0] * canvas.width * 0.5;
    const focalY = proj[5] * canvas.height * 0.5;
    const ubo = new Float32Array(40);
    ubo.set(view, 0);
    ubo.set(proj, 16);
    ubo[32] = canvas.width;
    ubo[33] = canvas.height;
    ubo[34] = 0; ubo[35] = 0;
    ubo[36] = focalX;
    ubo[37] = focalY;
    ubo[38] = 0; ubo[39] = 0;
    gpuState.device.queue.writeBuffer(gpuState.frameUBO, 0, ubo);

    const encoder = gpuState.device.createCommandEncoder();
    const pass = encoder.beginRenderPass({
      colorAttachments: [{
        view: gpuState.context.getCurrentTexture().createView(),
        loadOp: "clear",
        storeOp: "store",
        clearValue: { r: ALPHA_CLEAR[0], g: ALPHA_CLEAR[1], b: ALPHA_CLEAR[2], a: ALPHA_CLEAR[3] },
      }],
    });
    pass.setPipeline(gpuState.pipeline);
    pass.setBindGroup(0, gpuState.bindGroup);
    pass.draw(4, splats.count, 0, 0);
    pass.end();
    gpuState.device.queue.submit([encoder.finish()]);
  } else {
    // Clear-only frame before any splat is loaded.
    const encoder = gpuState.device.createCommandEncoder();
    const pass = encoder.beginRenderPass({
      colorAttachments: [{
        view: gpuState.context.getCurrentTexture().createView(),
        loadOp: "clear",
        storeOp: "store",
        clearValue: { r: ALPHA_CLEAR[0], g: ALPHA_CLEAR[1], b: ALPHA_CLEAR[2], a: ALPHA_CLEAR[3] },
      }],
    });
    pass.end();
    gpuState.device.queue.submit([encoder.finish()]);
  }

  hudSort.textContent = lastSortMs > 0 ? `${lastSortMs.toFixed(0)} ms` : "—";
  requestAnimationFrame(frame);
}

function viewChanged(a, b) {
  for (let i = 0; i < 16; i = i + 1) {
    if (Math.abs(a[i] - b[i]) > 1e-4) return true;
  }
  return false;
}

// --- wiring ---

fileInput.addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  setStatus(`loading ${file.name} …`);
  const buf = await file.arrayBuffer();
  await loadArrayBuffer(buf);
});

loadUrlBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) return;
  await loadUrl(url);
});

// Drag-and-drop splat files onto the stage.
const stage = document.getElementById("stage");
stage.addEventListener("dragover", (e) => e.preventDefault());
stage.addEventListener("drop", async (e) => {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (!file) return;
  setStatus(`loading ${file.name} …`);
  const buf = await file.arrayBuffer();
  await loadArrayBuffer(buf);
});

videoToggleBtn.addEventListener("click", async () => {
  if (videoStream) {
    videoStream.getTracks().forEach((t) => t.stop());
    videoStream = null;
    videoEl.srcObject = null;
    videoEl.classList.remove("on");
    videoToggleBtn.textContent = "webcam overlay: off";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    videoStream = stream;
    videoEl.srcObject = stream;
    videoEl.classList.add("on");
    videoToggleBtn.textContent = "webcam overlay: on";
  } catch (err) {
    console.error(err);
    setStatus(`webcam denied: ${err.message}`);
  }
});

setup();
