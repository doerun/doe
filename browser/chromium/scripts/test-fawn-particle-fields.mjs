// Compare optimized fields with the frozen deployed WGSL on a physical browser GPU.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const { chromium } = await import(process.env.FAWN_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const file = 'browser/chromium/resources/fawn-start.html';
const baselineRef = process.env.FAWN_BASELINE_REF || 'e7b7cb06b176a3660bd52bc848476d75271f2b0e';
const output = path.resolve(process.env.FAWN_REPORT_DIR || 'bench/out/fawn-demo-optimization');
const source = {
  baseline: execFileSync('git', ['show', `${baselineRef}:${file}`], { cwd: root, encoding: 'utf8' }),
  candidate: readFileSync(path.join(root, file), 'utf8'),
};
const shaders = Object.values(source).map(html => vm.runInNewContext(
  html.split('<script>')[1].split('(async () => {')[0] + '; COMPUTE_WGSL',
));
const server = http.createServer((request, response) => response.end('<title>GPU field oracle</title>'));
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-webgpu'] });
try {
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const results = await page.evaluate(async shaders => {
    const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
    const device = await adapter.requestDevice();
    const errors = [];
    device.addEventListener('uncapturederror', event => errors.push(event.error.message));
    const count = 257;
    const initial = new Float32Array(count * 8);
    for (let i = 0; i < count; i++) {
      initial[i * 8] = Math.sin(i * 17) * 1.65;
      initial[i * 8 + 1] = Math.cos(i * 11) * 1.03;
      initial[i * 8 + 2] = Math.sin(i) * 1.5;
      initial[i * 8 + 3] = Math.cos(i) * 1.5;
      initial.set([.3, .7, .9, .002], i * 8 + 4);
    }
    initial[0] = 0; initial[1] = 0;
    const input = device.createBuffer({ size: initial.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(input, 0, initial);
    const uniform = device.createBuffer({ size: 32, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    const outputs = shaders.map(() => device.createBuffer({ size: initial.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC }));
    const reads = shaders.map(() => device.createBuffer({ size: initial.byteLength, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ }));
    const pipelines = shaders.map(code => device.createComputePipeline({ layout: 'auto', compute: { module: device.createShaderModule({ code }), entryPoint: 'main' } }));
    const groups = pipelines.map((pipeline, i) => device.createBindGroup({ layout: pipeline.getBindGroupLayout(0), entries: [
      { binding: 0, resource: { buffer: uniform } },
      { binding: 1, resource: { buffer: input } },
      { binding: 2, resource: { buffer: outputs[i] } },
    ] }));
    const cases = [];
    for (const phase of [0, .001, .25, .5, .999, 1, 1.001, 1.5, 1.999, 2, 2.5, 2.999]) {
      for (const force of [0, 4]) {
        device.queue.writeBuffer(uniform, 0, new Float32Array([1 / 240, 13.7, 1.6, force, .2, -.3, 1, phase]));
        const encoder = device.createCommandEncoder();
        const pass = encoder.beginComputePass();
        pipelines.forEach((pipeline, i) => {
          pass.setPipeline(pipeline); pass.setBindGroup(0, groups[i]);
          pass.dispatchWorkgroups(2, 2);
        });
        pass.end();
        outputs.forEach((buffer, i) => encoder.copyBufferToBuffer(buffer, 0, reads[i], 0, initial.byteLength));
        device.queue.submit([encoder.finish()]);
        await Promise.all(reads.map(read => read.mapAsync(GPUMapMode.READ)));
        const values = reads.map(read => new Float32Array(read.getMappedRange()));
        let maxAbsoluteError = 0;
        for (let i = 0; i < initial.length; i++) {
          if (!Number.isFinite(values[1][i])) throw new Error('Non-finite particle output');
          maxAbsoluteError = Math.max(maxAbsoluteError, Math.abs(values[0][i] - values[1][i]));
        }
        reads.forEach(read => read.unmap());
        cases.push({ phase, force, maxAbsoluteError });
      }
    }
    const result = { cases, errors, adapter: { vendor: adapter.info.vendor, architecture: adapter.info.architecture, isFallbackAdapter: adapter.info.isFallbackAdapter } };
    device.destroy();
    return result;
  }, shaders);
  assert.deepEqual(results.errors, []);
  for (const result of results.cases) assert.ok(result.maxAbsoluteError <= 1e-6, JSON.stringify(result));
  mkdirSync(output, { recursive: true });
  writeFileSync(path.join(output, 'particle-fields.json'), JSON.stringify({
    classification: 'Physical Chrome application-shader regression, not runtime qualification',
    baselineRef, browser: browser.version(), observedAt: new Date().toISOString(),
    sourceHashes: Object.fromEntries(Object.entries(source).map(([variant, html]) => [variant, createHash('sha256').update(html).digest('hex')])),
    absoluteTolerance: 1e-6, ...results, passed: true,
  }, null, 2) + '\n');
  console.log('All particle fields, blend boundaries, pointer forces, and 2D dispatch passed.');
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
