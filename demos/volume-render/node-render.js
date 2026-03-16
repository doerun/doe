// node-render.js — headless volume ray marcher for Node.js via @simulatte/webgpu.
//
// Usage:
//   node node-render.js [dataset] [frames] [width] [height] [out_dir]
//
//   dataset  : fuel | silicium | hydrogen_atom  (default: fuel)
//   frames   : number of orbit frames to render (default: 120)
//   width    : output image width  (default: 640)
//   height   : output image height (default: 480)
//   out_dir  : directory for PPM frames (default: ./out)
//
// After rendering, stitch with:
//   ffmpeg -framerate 30 -i out/frame_%03d.ppm -vf format=yuv420p orbit.mp4

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { globals, requestDevice } from "@simulatte/webgpu";

const __dirname = dirname(fileURLToPath(import.meta.url));

const DATASETS = {
  fuel:          { w: 64,  h: 64,  d: 64,  file: "fuel_64x64x64_uint8.raw" },
  silicium:      { w: 98,  h: 34,  d: 34,  file: "silicium_98x34x34_uint8.raw" },
  hydrogen_atom: { w: 128, h: 128, d: 128, file: "hydrogen_atom_128x128x128_uint8.raw" },
};

const ALIGN = 256; // WebGPU copyBufferToTexture bytesPerRow alignment

const dsName  = process.argv[2] ?? "fuel";
const frames  = parseInt(process.argv[3] ?? "120");
const W       = parseInt(process.argv[4] ?? "640");
const H       = parseInt(process.argv[5] ?? "480");
const outDir  = resolve(__dirname, process.argv[6] ?? "out");

const ds = DATASETS[dsName];
if (!ds) {
  console.error(`Unknown dataset: ${dsName}. Use: ${Object.keys(DATASETS).join(", ")}`);
  process.exit(1);
}

const rawPath = resolve(__dirname, "data", ds.file);
if (!existsSync(rawPath)) {
  console.error(`Missing: ${rawPath}\nRun: bash download.sh`);
  process.exit(1);
}

mkdirSync(outDir, { recursive: true });

// Pad volume rows to 256-byte alignment for copyBufferToTexture
function padVolume(data, volW, volH, volD) {
  const alignedRow = Math.ceil(volW / ALIGN) * ALIGN;
  if (alignedRow === volW) return { data, bytesPerRow: volW };
  const out = new Uint8Array(alignedRow * volH * volD);
  for (let z = 0; z < volD; z++) {
    for (let y = 0; y < volH; y++) {
      out.set(
        data.subarray((z * volH + y) * volW, (z * volH + y) * volW + volW),
        (z * volH + y) * alignedRow,
      );
    }
  }
  return { data: out, bytesPerRow: alignedRow };
}

function cameraForFrame(frame, total) {
  const angle  = (frame / total) * Math.PI * 2;
  const radius = 2.2;
  return {
    eye:    [0.5 + radius * Math.sin(angle), 0.9, 0.5 + radius * Math.cos(angle)],
    target: [0.5, 0.5, 0.5],
  };
}

function setCameraUniform(view, eye, target, width, height) {
  view.setFloat32( 0, eye[0],    true);
  view.setFloat32( 4, eye[1],    true);
  view.setFloat32( 8, eye[2],    true);
  view.setFloat32(12, 0.0,       true); // pad
  view.setFloat32(16, target[0], true);
  view.setFloat32(20, target[1], true);
  view.setFloat32(24, target[2], true);
  view.setFloat32(28, 0.0,       true); // pad
  view.setUint32 (32, width,     true);
  view.setUint32 (36, height,    true);
  view.setUint32 (40, 0,         true); // pad
  view.setUint32 (44, 0,         true); // pad
}

function writePPM(filePath, width, height, pixels) {
  // pixels is Uint32Array, each element: R | G<<8 | B<<16 | A<<24
  const header = `P6\n${width} ${height}\n255\n`;
  const rgb = Buffer.alloc(width * height * 3);
  for (let i = 0; i < width * height; i++) {
    const p = pixels[i];
    rgb[i * 3 + 0] = (p >>  0) & 0xFF;
    rgb[i * 3 + 1] = (p >>  8) & 0xFF;
    rgb[i * 3 + 2] = (p >> 16) & 0xFF;
  }
  writeFileSync(filePath, Buffer.concat([Buffer.from(header), rgb]));
}

console.log(`dataset: ${dsName} (${ds.w}×${ds.h}×${ds.d}), frames: ${frames}, output: ${W}×${H}`);

const device  = await requestDevice();
const { GPUBufferUsage, GPUTextureUsage } = globals;

// --- volume texture ---
const rawData = new Uint8Array(readFileSync(rawPath).buffer);
const { data: volPadded, bytesPerRow: volBytesPerRow } = padVolume(rawData, ds.w, ds.h, ds.d);

const volStagingBuf = device.createBuffer({
  size: volPadded.byteLength,
  usage: GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
});
device.queue.writeBuffer(volStagingBuf, 0, volPadded);

const volTexture = device.createTexture({
  dimension: "3d",
  size: { width: ds.w, height: ds.h, depthOrArrayLayers: ds.d },
  format: "r8unorm",
  usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST,
});

{
  const enc = device.createCommandEncoder();
  enc.copyBufferToTexture(
    { buffer: volStagingBuf, offset: 0, bytesPerRow: volBytesPerRow, rowsPerImage: ds.h },
    { texture: volTexture },
    { width: ds.w, height: ds.h, depthOrArrayLayers: ds.d },
  );
  device.queue.submit([enc.finish()]);
  await device.queue.onSubmittedWorkDone();
}

// --- output pixel buffer ---
const pixelBytes  = W * H * 4;
const pixelBuf    = device.createBuffer({
  size: pixelBytes,
  usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC,
});
const readbackBuf = device.createBuffer({
  size: pixelBytes,
  usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
});

// --- camera uniform (updated each frame) ---
const camBuf = device.createBuffer({
  size: 48,
  usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
});

// --- volume info uniform (constant) ---
const volInfoBuf = device.createBuffer({ size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
const volInfoData = new DataView(new ArrayBuffer(16));
volInfoData.setUint32(0,  ds.w, true);
volInfoData.setUint32(4,  ds.h, true);
volInfoData.setUint32(8,  ds.d, true);
volInfoData.setUint32(12, 0,    true);
device.queue.writeBuffer(volInfoBuf, 0, volInfoData.buffer);

// --- shader ---
const shaderSrc = readFileSync(resolve(__dirname, "volume-render.wgsl"), "utf8");
const shaderMod = device.createShaderModule({ code: shaderSrc });

const pipeline = device.createComputePipeline({
  layout: "auto",
  compute: { module: shaderMod, entryPoint: "main" },
});

const bindGroup = device.createBindGroup({
  layout: pipeline.getBindGroupLayout(0),
  entries: [
    { binding: 0, resource: { buffer: camBuf } },
    { binding: 1, resource: { buffer: volInfoBuf } },
    { binding: 2, resource: volTexture.createView() },
    { binding: 3, resource: { buffer: pixelBuf } },
  ],
});

const wgX = Math.ceil(W / 8);
const wgY = Math.ceil(H / 8);
const camData = new DataView(new ArrayBuffer(48));

console.log(`rendering ${frames} frames...`);
const t0 = Date.now();

for (let f = 0; f < frames; f++) {
  const { eye, target } = cameraForFrame(f, frames);
  setCameraUniform(camData, eye, target, W, H);
  device.queue.writeBuffer(camBuf, 0, camData.buffer);

  const enc  = device.createCommandEncoder();
  const pass = enc.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(wgX, wgY);
  pass.end();
  enc.copyBufferToBuffer(pixelBuf, 0, readbackBuf, 0, pixelBytes);
  device.queue.submit([enc.finish()]);
  await device.queue.onSubmittedWorkDone();

  await readbackBuf.mapAsync(globals.GPUMapMode.READ);
  const pixels = new Uint32Array(readbackBuf.getMappedRange().slice(0));
  readbackBuf.unmap();

  const framePath = resolve(outDir, `frame_${String(f).padStart(3, "0")}.ppm`);
  writePPM(framePath, W, H, pixels);

  if (f % 10 === 0 || f === frames - 1) {
    process.stdout.write(`  frame ${f + 1}/${frames}\r`);
  }
}

const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
console.log(`\ndone in ${elapsed}s → ${outDir}/`);
console.log(`\nstitch to video:`);
console.log(`  ffmpeg -framerate 30 -i "${outDir}/frame_%03d.ppm" -vf format=yuv420p orbit.mp4`);
