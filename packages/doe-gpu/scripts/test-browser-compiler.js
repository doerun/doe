#!/usr/bin/env node
// Physical browser acceptance for the independently downloadable compiler.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const packageRoot = resolve(process.env.DOE_BROWSER_PACKAGE_ROOT ?? resolve(root, 'packages/doe-gpu'));
const output = resolve(process.env.DOE_BROWSER_REPORT ?? resolve(root,
  'bench/out/browser-compiler/20261004'));
const { chromium } = await import(process.env.DOE_PLAYWRIGHT_MODULE ?? 'playwright');
await mkdir(output, { recursive: true });
const source = resolve(packageRoot, 'examples/browser-compiler/particles.wgsl');
const offlinePath = resolve(output, 'particles.optimized.wgsl');
const emitted = spawnSync(resolve(root, 'runtime/zig/zig-out/bin/doe-emit-wgsl'),
  [source, offlinePath], { encoding: 'utf8' });
assert.equal(emitted.status, 0, emitted.stderr);
const offline = await readFile(offlinePath, 'utf8');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.wasm': 'application/wasm', '.wgsl': 'text/plain' };
const server = createServer(async (request, response) => {
  try {
    const path = resolve(packageRoot, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`);
    if (!path.startsWith(packageRoot + sep)) throw new Error('Path outside package');
    const bytes = await readFile(path);
    response.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream',
      'Cache-Control': 'no-store' });
    response.end(bytes);
  } catch {
    response.writeHead(404);
    response.end();
  }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const url = `http://127.0.0.1:${server.address().port}/examples/browser-compiler/index.html`;
const args = JSON.parse(process.env.DOE_BROWSER_ARGS ?? JSON.stringify([
  '--no-sandbox', '--enable-unsafe-webgpu', '--ignore-gpu-blocklist',
  '--enable-webgpu-developer-features', '--use-angle=vulkan',
  '--enable-features=Vulkan', '--disable-vulkan-surface',
]));
const browser = await chromium.launch({ executablePath: process.env.DOE_BROWSER ?? '/usr/bin/google-chrome',
  headless: process.env.DOE_BROWSER_HEADFUL !== '1', args });
const errors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto(url);
  await page.waitForFunction(() => window.doeParticleLab?.ready || !document.getElementById('error').hidden);
  assert.equal(await page.locator('#error').isVisible(), false,
    await page.locator('#error').textContent());
  console.log('ok: ordinary browser initialized');
  const offlineResult = await page.evaluate((shader) => window.doeParticleLab.offlineCompare(shader), offline);
  await writeFile(resolve(output, 'offline.json'), JSON.stringify(offlineResult, null, 2));
  assert.equal(offlineResult.candidate.parity.passed, true);
  assert(offlineResult.rows.every((row) => row.oracle.passed && row.workerRoundTripMs === 0));
  const offlinePlain = await page.evaluate((shader) =>
    window.doeParticleLab.offlineCompare(shader, { timestamps: false }), offline);
  assert(offlinePlain.rows.every((row) => row.oracle.passed && row.gpuComputeMs === null
    && row.workerRoundTripMs === 0));
  await writeFile(resolve(output, 'offline-uninstrumented.json'), JSON.stringify(offlinePlain, null, 2));
  console.log('ok: offline-emitted WGSL matches browser and independent CPU oracle');
  const measured = await page.evaluate(() => window.doeParticleLab.compare());
  await writeFile(resolve(output, 'timestamped.json'), JSON.stringify(measured, null, 2));
  for (const row of measured.rows) {
    assert.equal(row.oracle.passed, true);
    assert.equal(row.dispatches, measured.contract.steps);
    assert.equal(row.draws, 1);
    if (row.mode === 'enabled') assert.equal(row.rewrites, 3);
    if (row.mode === 'disabled') assert.equal(row.wgslHash, measured.originalWGSLHash);
  }
  console.log('ok: all three modes execute matched work and verify every component');
  const plain = await page.evaluate(() => window.doeParticleLab.compare({ timestamps: false }));
  await writeFile(resolve(output, 'uninstrumented.json'), JSON.stringify(plain, null, 2));
  assert(plain.rows.every((row) => row.gpuComputeMs === null));
  await page.screenshot({ path: resolve(output, 'desktop.png'), fullPage: true });
  console.log('ok: confirmation runs with GPU query instrumentation disabled');
  const lifecycle = await page.evaluate(async () => {
    const gpu = navigator.gpu;
    const disabled = await window.doeParticleLab.switchMode('disabled');
    const enabled = await window.doeParticleLab.switchMode('enabled');
    const browser = await window.doeParticleLab.switchMode('browser');
    return { disabled, enabled, browser, gpuUnchanged: gpu === navigator.gpu };
  });
  assert(lifecycle.gpuUnchanged);
  assert(lifecycle.disabled.verification.passed && lifecycle.enabled.verification.passed
    && lifecycle.browser.verification.passed);
  console.log('ok: explicit switching drains, recreates and verifies state; navigator.gpu unchanged');
  await page.evaluate(() => window.doeParticleLab.pause());
  const workerLifecycle = await page.evaluate(async () => {
    const { createDoeCompiler } = await import('../../src/browser-compiler.js');
    const { compilerArtifact: metadata } = await import('../../src/browser-compiler-artifact.js');
    const artifact = { url: new URL(`../../assets/${metadata.asset}`, location.href).href,
      sha256: metadata.sha256, byteLength: metadata.byteLength };
    const compiler = await createDoeCompiler({ artifact });
    const limit = compiler.initialization.sourceLimit;
    const boundary = [];
    const prefix = 'fn f() {} //';
    for (const length of [limit - 1, limit]) {
      const text = prefix + 'x'.repeat(length - prefix.length);
      const result = await compiler.compile(text, { optimize: false });
      if (result.wgsl !== text) throw new Error('Boundary text changed');
      boundary.push({ bytes: new TextEncoder().encode(text).length, accepted: true });
    }
    const unicode = prefix + 'é'.repeat(Math.floor((limit - prefix.length) / 2))
      + 'x'.repeat((limit - prefix.length) % 2);
    const unicodeResult = await compiler.compile(unicode, { optimize: false });
    if (unicodeResult.wgsl !== unicode) throw new Error('Unicode boundary changed');
    boundary.push({ bytes: new TextEncoder().encode(unicode).length, nonASCII: true, accepted: true });
    for (const text of ['x'.repeat(limit + 1), unicode + 'x']) {
      let rejected = false;
      try { await compiler.compile(text, { optimize: true }); }
      catch (error) { rejected = error instanceof RangeError; }
      if (!rejected) throw new Error('Oversized source accepted');
      boundary.push({ bytes: new TextEncoder().encode(text).length, accepted: false });
    }
    const recovered = await compiler.compile(window.doeParticleLab.code, { optimize: true });
    if (!recovered.wgsl) throw new Error('Compiler did not recover after rejection');
    let diagnostic;
    try { await compiler.compile('fn alias() {}', { optimize: true }); }
    catch (error) { diagnostic = error.diagnostic; }
    const pending = compiler.compile(window.doeParticleLab.code, { optimize: true });
    compiler.close();
    compiler.close();
    let cancelled = false;
    try { await pending; } catch (error) { cancelled = error.message.includes('closed'); }
    return { diagnostic, cancelled, sourceBudgetUnit: 'UTF-8 bytes', boundary, recovered: true };
  });
  assert.equal(workerLifecycle.diagnostic.byteOffset, 3);
  assert(workerLifecycle.cancelled);
  console.log('ok: original-source Worker diagnostic and cancellation settlement');
  const integerOracle = await page.evaluate(async () => {
    const { createDoeShaderAdapter } = await import('../../src/browser-compiler.js');
    const compiler = await window.doeParticleLab.getCompiler();
    const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
    const device = await adapter.requestDevice();
    const inputs = new Uint32Array([0, 1, 7, 8, 0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff]);
    const source = `@group(0) @binding(0) var<storage,read> input:array<u32>;
      @group(0) @binding(1) var<storage,read_write> output:array<u32>;
      @compute @workgroup_size(1) fn main(@builtin(global_invocation_id) gid:vec3<u32>) {
        let x = input[gid.x]; output[gid.x*2u]=x/8u; output[gid.x*2u+1u]=x%4u; }`;
    const expected = Array.from(inputs).flatMap((value) => [Math.floor(value / 8), value % 4]);
    const rows = [];
    try {
      for (const mode of ['browser', 'disabled', 'enabled']) {
        const resources = [];
        try {
          const adapted = mode === 'browser' ? { module: device.createShaderModule({ code: source }) }
            : await createDoeShaderAdapter({ device, compiler, optimize: mode === 'enabled' })
              .createShaderModule({ code: source });
          const pipeline = await device.createComputePipelineAsync({ layout: 'auto',
            compute: { module: adapted.module, entryPoint: 'main' } });
          const input = device.createBuffer({ size: inputs.byteLength,
            usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
          resources.push(input);
          device.queue.writeBuffer(input, 0, inputs);
          const output = device.createBuffer({ size: inputs.byteLength * 2,
            usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC });
          resources.push(output);
          const read = device.createBuffer({ size: inputs.byteLength * 2,
            usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
          resources.push(read);
          const binding = device.createBindGroup({ layout: pipeline.getBindGroupLayout(0),
            entries: [{ binding: 0, resource: { buffer: input } },
              { binding: 1, resource: { buffer: output } }] });
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass();
          pass.setPipeline(pipeline); pass.setBindGroup(0, binding);
          pass.dispatchWorkgroups(inputs.length); pass.end();
          encoder.copyBufferToBuffer(output, 0, read, 0, inputs.byteLength * 2);
          device.queue.submit([encoder.finish()]);
          await read.mapAsync(GPUMapMode.READ);
          const actual = Array.from(new Uint32Array(read.getMappedRange()));
          read.unmap();
          if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error('Unsigned edge oracle failed');
          rows.push({ mode, actual, rewrites: adapted.rewrites ?? 0 });
        } finally {
          await device.queue.onSubmittedWorkDone();
          for (const resource of resources) resource.destroy();
        }
      }
    } finally { device.destroy(); }
    return { inputs: Array.from(inputs), expected, rows };
  });
  assert.equal(integerOracle.rows[2].rewrites, 2);
  console.log('ok: physical unsigned edge cases agree with independent arithmetic oracle');
  const cache = await page.evaluate(async () => {
    const { createDoeCompiler } = await import('../../src/browser-compiler.js');
    const { compilerArtifact: metadata } = await import('../../src/browser-compiler-artifact.js');
    const artifact = { url: new URL(`../../assets/${metadata.asset}`, location.href).href,
      sha256: metadata.sha256, byteLength: metadata.byteLength };
    const root = await navigator.storage.getDirectory();
    const directory = await root.getDirectoryHandle('doe-compiler-v1', { create: true });
    const name = `doe-wgsl-${metadata.sha256}.wasm`;
    async function open(cache = true) {
      const compiler = await createDoeCompiler({ artifact, cache });
      const metrics = compiler.initialization;
      compiler.close();
      return metrics;
    }
    const hit = await open();
    const handle = await directory.getFileHandle(name);
    const writable = await handle.createWritable();
    await writable.write(new Uint8Array(metadata.byteLength));
    await writable.close();
    const corrupt = await open();
    await directory.removeEntry(name);
    const lost = await open();
    const disabled = await open(false);
    let rejected = false;
    try { await createDoeCompiler({ artifact: { ...artifact, sha256: '0'.repeat(64) }, cache: false }); }
    catch (error) { rejected = error.message.includes('digest mismatch'); }
    return { hit, corrupt, lost, disabled, digestRejected: rejected };
  });
  assert.equal(cache.hit.cacheStatus, 'verified-hit');
  assert.equal(cache.hit.bytesDownloaded, 0);
  assert.equal(cache.corrupt.cacheStatus, 'rejected-stored');
  assert.equal(cache.lost.cacheStatus, 'miss-stored');
  assert.equal(cache.disabled.cacheStatus, 'disabled');
  assert(cache.digestRejected);
  console.log('ok: verified cache hit, corruption, loss, disabled cache and untrusted digest');
  const ceiling = await page.evaluate(() => window.doeParticleLab.capacity());
  await writeFile(resolve(output, 'capacity.json'), JSON.stringify(ceiling, null, 2));
  assert(ceiling.rows.length >= 3);
  assert(ceiling.rows.every((row) => row.samples.every((sample) => sample.oracle.passed)));
  console.log('ok: separate particle ceiling experiment verifies every sampled result');
  await page.evaluate(() => window.doeParticleLab.pause());
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: resolve(output, 'mobile.png'), fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  assert.equal(overflow, false);
  const receipt = { schemaVersion: 1, browser: await browser.version(), args,
    offline, offlineHash: createHash('sha256').update(offline).digest('hex'),
    lifecycle, workerLifecycle, integerOracle, cache, errors,
    measuredSummaries: measured.summaries, uninstrumentedSummaries: plain.summaries };
  await writeFile(resolve(output, 'acceptance.json'), JSON.stringify(receipt, null, 2));
  assert.deepEqual(errors, []);
  console.log(JSON.stringify(receipt.uninstrumentedSummaries));
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
}
