// Direct WGSL attribution. No compiler Worker or adapter is instantiated.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const plan = JSON.parse(await readFile(resolve(root, 'config/browser-compiler-output.json')));
const packageRoot = resolve(root, process.env.DOE_BROWSER_PACKAGE_ROOT ?? 'packages/doe-gpu');
const output = resolve(root, process.env.DOE_BROWSER_REPORT ?? plan.output);
const { chromium } = await import(process.env.DOE_PLAYWRIGHT_MODULE ?? 'playwright');
await mkdir(output, { recursive: true });
const original = await readFile(resolve(packageRoot, 'examples/browser-compiler/particles.wgsl'), 'utf8');
const emitter = spawnSync(resolve(root, 'runtime/zig/zig-out/bin/doe-emit-wgsl'),
  [resolve(packageRoot, 'examples/browser-compiler/particles.wgsl'), resolve(output, 'transformed.wgsl')],
  { encoding: 'utf8' });
assert.equal(emitter.status, 0, emitter.stderr);
const transformed = await readFile(resolve(output, 'transformed.wgsl'), 'utf8');
const { compilerArtifact } = await import(new URL(`file://${packageRoot}/src/browser-compiler-artifact.js`));
const { exports: wasm } = await WebAssembly.instantiate(await WebAssembly.compile(
  await readFile(resolve(packageRoot, 'assets', compilerArtifact.asset))));
const bytes = new TextEncoder().encode(original);
const input = wasm.reserve_source(bytes.length);
assert(input);
new Uint8Array(wasm.memory.buffer, input, bytes.length).set(bytes);
const pointer = wasm.compile(bytes.length, 0);
assert(pointer);
const disabled = JSON.parse(new TextDecoder().decode(
  new Uint8Array(wasm.memory.buffer, pointer, wasm.output_length())));
wasm.release_job();
assert(disabled.ok);
assert.equal(disabled.wgsl, original);
await writeFile(resolve(output, 'original.wgsl'), original);
await writeFile(resolve(output, 'disabled.wgsl'), disabled.wgsl);
const types = { '.js': 'text/javascript' };
const server = createServer(async (request, response) => {
  if (request.url === '/fixture') {
    response.writeHead(200, { 'Content-Type': 'text/html' });
    response.end('<!doctype html><html><head><link rel="icon" href="data:,"></head><body><canvas width="1440" height="1100"></canvas></body></html>');
    return;
  }
  try {
    const path = resolve(packageRoot, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`);
    if (!path.startsWith(packageRoot + sep)) throw new Error('Path outside package');
    const data = await readFile(path);
    response.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream' });
    response.end(data);
  } catch { response.writeHead(404); response.end(); }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
let browser;
try {
  browser = await chromium.launch({ executablePath: process.env.DOE_BROWSER ?? plan.browser,
    headless: false, args: plan.args });
  const versions = [];
  for (let session = 0; session < plan.sessions; session++) {
    const context = await browser.newContext({ viewport: plan.viewport });
    try {
      const page = await context.newPage();
      await page.goto(`http://127.0.0.1:${server.address().port}/fixture`);
      const result = await page.evaluate(async ({ variants, contract }) => {
        const { measureMode } = await import('/examples/browser-compiler/benchmark.js');
        const { initialParticles, referenceParticles } = await import('/examples/browser-compiler/particles.js');
        const adapter = await navigator.gpu.requestAdapter();
        if (!adapter || !adapter.features.has('timestamp-query')) throw new Error('Physical timestamp adapter required');
        const device = await adapter.requestDevice({ requiredFeatures: ['timestamp-query'] });
        const canvas = document.querySelector('canvas');
        const gpuContext = canvas.getContext('webgpu');
        const format = navigator.gpu.getPreferredCanvasFormat();
        gpuContext.configure({ device, format, alphaMode: 'opaque' });
        const initial = initialParticles(contract.particleCount, contract.seed);
        const expected = referenceParticles(initial, contract.steps, contract.dt);
        const names = Object.keys(variants);
        const evidence = [];
        try {
          for (const timestamps of [true, false]) {
            const rows = [];
            let reference;
            for (let cohort = 0; cohort < contract.repeats; cohort++) {
              for (const variant of names.map((_, index) => names[(index + cohort) % names.length])) {
                const result = await measureMode({ device, context: gpuContext, format, initial,
                  contract, code: variants[variant], mode: 'offline', timestamps }, expected, reference);
                reference ??= result.positions;
                rows.push({ cohort, variant, ...result.row });
              }
            }
            const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
            const summaries = Object.fromEntries(names.map((name) => [name, Object.fromEntries(
              ['pipelinePreparationMs', 'gpuComputeMs', 'completeOperationMs', 'applicationMs'].map((metric) =>
                [metric, rows[0][metric] === null ? null
                  : median(rows.filter((row) => row.variant === name).map((row) => row[metric]))]))]));
            evidence.push({ schemaVersion: 1, classification: 'diagnostic', contract, timestamps,
              scope: 'Direct shader text, no Worker/adapter. Fresh buffers and pipelines; rotated cohorts. '
                + 'Browser device/driver caches shared within session; context/device recreated between sessions.',
              rows, summaries, baseline: rows.find((row) => row.variant === 'original'),
              candidate: rows.find((row) => row.variant === 'transformed') });
          }
          return { evidence, userAgent: navigator.userAgent, adapter: { vendor: adapter.info.vendor,
            architecture: adapter.info.architecture, device: adapter.info.device, description: adapter.info.description } };
        } finally { gpuContext.unconfigure(); device.destroy(); }
      }, { variants: { original, disabled: disabled.wgsl, transformed },
        contract: JSON.parse(await readFile(resolve(packageRoot, 'examples/browser-compiler/contract.json'))) });
      versions.push({ session, userAgent: result.userAgent, adapter: result.adapter });
      for (const evidence of result.evidence) {
        assert(evidence.rows.every((row) => row.oracle.passed && row.workerRoundTripMs === 0));
        await writeFile(resolve(output, `session-${session}-${evidence.timestamps ? 'timestamped' : 'plain'}.json`),
          JSON.stringify(evidence, null, 2));
      }
      console.log(`Verified direct WGSL session ${session}`);
    } finally { await context.close(); }
  }
  await writeFile(resolve(output, 'environment.json'), JSON.stringify({ schemaVersion: 1,
    browserVersion: browser.version(), plan, sessions: versions }, null, 2));
} finally { await browser?.close(); await new Promise((done) => server.close(done)); }
