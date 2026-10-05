// Physical-browser application checks; these do not qualify a Doe browser runtime.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const { chromium } = await import(process.env.FAWN_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const resources = 'browser/chromium/resources';
const baselineRef = process.env.FAWN_BASELINE_REF || 'e7b7cb06b176a3660bd52bc848476d75271f2b0e';
const output = path.resolve(process.env.FAWN_REPORT_DIR || 'bench/out/fawn-demo-optimization');
const pages = ['start', 'heavy-particles', 'magnetic-fluids', 'prismatic-fluids'];
const sources = {};
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
mkdirSync(output, { recursive: true });
for (const name of pages) {
  const file = `${resources}/fawn-${name}.html`;
  sources[name] = {
    baseline: execFileSync('git', ['show', `${baselineRef}:${file}`], { cwd: root, encoding: 'utf8' }),
    candidate: readFileSync(path.join(root, file), 'utf8'),
  };
}
const server = http.createServer((request, response) => {
  const [, variant, name] = request.url.split('/');
  const source = sources[name]?.[variant];
  if (!source) { response.writeHead(404).end(); return; }
  response.setHeader('Content-Type', 'text/html');
  response.end(source);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-webgpu'] });
const report = {
  classification: 'Chrome application diagnostics on its existing WebGPU backend; no Doe-vs-Dawn claim',
  observedAt: new Date().toISOString(), baselineRef, browser: browser.version(),
  method: {
    fixedFrames: 12, simulationAbsoluteTolerance: 1e-6,
    slowFrameDelayMs: 70, warmupMs: 1500, measuredMs: 3500,
    order: ['baseline/candidate', 'candidate/baseline'],
    timing: 'queue-completed frames, including browser scheduling; GPU-only time is not measured',
  },
  sourceHashes: Object.fromEntries(pages.map(name => [name, Object.fromEntries(
    Object.entries(sources[name]).map(([variant, source]) => [variant, sha256(source)]),
  )])),
  correctness: [], lifecycle: [], performance: [],
};

function instrument({ fixed = false, delay = 0 } = {}) {
  const s = window.__fawnTest = {
    clock: 1000, callbacks: new Map(), nextId: 0, device: null, buffers: [],
    errors: [], submissions: [], completions: [], active: false, pending: 0, maxPending: 0,
    computePasses: 0, renderPasses: 0, dispatches: 0, draws: [], delay,
  };
  if (fixed) {
    Object.defineProperty(performance, 'now', { value: () => s.clock });
    window.requestAnimationFrame = cb => { s.callbacks.set(++s.nextId, cb); return s.nextId; };
    window.cancelAnimationFrame = id => s.callbacks.delete(id);
  } else {
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = cb => raf(t => {
      const until = performance.now() + s.delay;
      while (performance.now() < until) {}
      return cb(t);
    });
  }
  const request = GPUAdapter.prototype.requestDevice;
  GPUAdapter.prototype.requestDevice = async function(...args) {
    const device = await request.apply(this, args);
    s.device = device;
    s.adapter = { ...this.info.toJSON?.(), vendor: this.info.vendor,
      architecture: this.info.architecture, isFallbackAdapter: this.info.isFallbackAdapter };
    device.addEventListener('uncapturederror', event => s.errors.push(event.error.message));
    const create = device.createBuffer.bind(device);
    device.createBuffer = desc => {
      const storage = Boolean(desc.usage & GPUBufferUsage.STORAGE);
      const buffer = create(fixed && storage ? { ...desc, usage: desc.usage | GPUBufferUsage.COPY_SRC } : desc);
      if (fixed && storage) {
        const entry = { buffer, size: desc.size, destroyed: false };
        const destroy = buffer.destroy.bind(buffer);
        buffer.destroy = () => { entry.destroyed = true; destroy(); };
        s.buffers.push(entry);
      }
      return buffer;
    };
    const encode = device.createCommandEncoder.bind(device);
    device.createCommandEncoder = (...args) => {
      const encoder = encode(...args);
      for (const kind of ['Compute', 'Render']) {
        const begin = encoder[`begin${kind}Pass`].bind(encoder);
        encoder[`begin${kind}Pass`] = (...args) => {
          if (s.active) s[kind === 'Compute' ? 'computePasses' : 'renderPasses'] += 1;
          const pass = begin(...args);
          const method = kind === 'Compute' ? 'dispatchWorkgroups' : 'draw';
          const command = pass[method].bind(pass);
          pass[method] = (...args) => {
            if (s.active) { if (kind === 'Compute') s.dispatches += 1; else s.draws.push(args); }
            return command(...args);
          };
          return pass;
        };
      }
      return encoder;
    };
    const submit = device.queue.submit.bind(device.queue);
    const done = device.queue.onSubmittedWorkDone.bind(device.queue);
    device.queue.submit = (...args) => {
      submit(...args);
      if (s.active) {
        s.submissions.push(performance.now());
        s.maxPending = Math.max(s.maxPending, ++s.pending);
        done().then(() => { s.pending -= 1; s.completions.push(performance.now()); });
      }
    };
    return device;
  };
}

async function open(variant, name, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 },
    deviceScaleFactor: options.dpr || 1, reducedMotion: options.reducedMotion || 'no-preference' });
  const page = await context.newPage();
  page.on('pageerror', error => page.evaluate(message => window.__fawnTest?.errors.push(message), error.message).catch(() => {}));
  await page.addInitScript(instrument, options);
  await page.goto(`${origin}/${variant}/${name}`);
  try {
    await page.waitForFunction(() => window.__fawnTest?.device && /WebGPU active|Running|Paused/.test(document.querySelector('#status')?.textContent || ''), null, { timeout: 30000, polling: 50 });
  } catch (error) {
    const failure = await page.evaluate(() => ({ status: document.querySelector('#status')?.textContent,
      failure: document.querySelector('#failure')?.textContent, errors: window.__fawnTest?.errors,
      deviceReady: Boolean(window.__fawnTest?.device) }));
    throw new Error(`${variant}/${name} startup: ${JSON.stringify(failure)}`, { cause: error });
  }
  return { context, page };
}

async function state(variant, name) {
  const { context, page } = await open(variant, name, { fixed: true });
  const data = await page.evaluate(async () => {
    const s = window.__fawnTest;
    // Older secondary pages use one RAF solely to initialize their clock.
    if ([...s.callbacks.values()].some(cb => cb.name !== 'frame')) {
      const callbacks = [...s.callbacks.values()];
      s.callbacks.clear();
      await Promise.all(callbacks.map(cb => cb(s.clock)));
    }
    s.active = true;
    for (let i = 0; i < 12; i++) {
      s.clock += 1000 / 60;
      const callbacks = [...s.callbacks.values()];
      s.callbacks.clear();
      await Promise.all(callbacks.map(cb => cb(s.clock)));
      await s.device.queue.onSubmittedWorkDone();
    }
    s.active = false;
    const buffers = [];
    for (const entry of s.buffers.filter(entry => !entry.destroyed)) {
      const read = s.device.createBuffer({ size: entry.size, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
      const encoder = s.device.createCommandEncoder();
      encoder.copyBufferToBuffer(entry.buffer, 0, read, 0, entry.size);
      s.device.queue.submit([encoder.finish()]);
      await read.mapAsync(GPUMapMode.READ);
      buffers.push(Array.from(new Float32Array(read.getMappedRange())));
      read.unmap(); read.destroy();
    }
    return { buffers, errors: s.errors, adapter: s.adapter, dispatches: s.dispatches,
      computePasses: s.computePasses, renderPasses: s.renderPasses, draws: s.draws };
  });
  await page.locator('#view').screenshot({ path: path.join(output, `${name}-${variant}.png`) });
  await context.close();
  assert.deepEqual(data.errors, [], `${variant}/${name} GPU errors`);
  return data;
}

function statistics(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return { n: values.length, p50: sorted[Math.floor((sorted.length - 1) * .5)], p95: sorted[Math.floor((sorted.length - 1) * .95)] };
}

try {
  for (const name of pages) {
    const before = await state('baseline', name);
    const after = await state('candidate', name);
    assert.equal(before.buffers.length, after.buffers.length);
    let maxError = 0;
    before.buffers.forEach((original, index) => {
      const expected = name === 'prismatic-fluids' && (index === 4 || index === 5)
        ? original.filter((_, i) => i % 4 === 0) : original;
      const actual = after.buffers[index];
      assert.equal(expected.length, actual.length, `${name} buffer ${index} length`);
      for (let i = 0; i < expected.length; i++) {
        assert.ok(Number.isFinite(actual[i]), `${name} non-finite buffer value`);
        maxError = Math.max(maxError, Math.abs(expected[i] - actual[i]));
      }
    });
    assert.ok(maxError <= 1e-6, `${name} fixed-frame simulation error ${maxError}`);
    const screenshots = Object.fromEntries(['baseline', 'candidate'].map(variant => [
      variant, sha256(readFileSync(path.join(output, `${name}-${variant}.png`))),
    ]));
    assert.equal(screenshots.baseline, screenshots.candidate, `${name} fixed-frame image changed`);
    report.correctness.push({ name, maxAbsoluteError: maxError, adapter: after.adapter,
      screenshots,
      storageBytes: { before: before.buffers.reduce((n, a) => n + a.length * 4, 0), after: after.buffers.reduce((n, a) => n + a.length * 4, 0) },
      dispatches: { before: before.dispatches, after: after.dispatches },
      passes: { before: [before.computePasses, before.renderPasses], after: [after.computePasses, after.renderPasses] },
    });
    console.log(`Fixed-frame GPU state preserved: ${name}, max error ${maxError}`);
  }
  for (const name of pages) {
    const { context, page } = await open('candidate', name, { delay: 70 });
    await page.evaluate(() => { window.__fawnTest.active = true; });
    await page.waitForTimeout(2200);
    const result = await page.evaluate(async () => {
      const s = window.__fawnTest;
      s.active = false;
      await s.device.queue.onSubmittedWorkDone();
      return { name: location.pathname.split('/').at(-1), errors: s.errors,
        maxPending: s.maxPending, display: document.querySelector('#frame').textContent,
        measuredFps: 1000 * (s.completions.length - 1) / (s.completions.at(-1) - s.completions[0]) };
    });
    const displayed = Number(result.display.match(/([\d.]+)\s*fps/)?.[1]);
    assert.ok(displayed > 0 && displayed < 20, `${name} slow frame metric: ${result.display}`);
    assert.ok(Math.abs(displayed - result.measuredFps) < 3, `${name} completion metric mismatch`);
    assert.ok(result.maxPending <= 2, `${name} queue bound`);
    await page.locator('#restart').click();
    await page.setViewportSize({ width: 1000, height: 720 });
    await page.waitForTimeout(800);
    if (name === 'start') {
      await page.locator('#pause').click();
      await page.waitForTimeout(300);
      assert.equal(await page.locator('#frame').textContent(), 'Paused');
      await page.locator('#pause').click();
      await page.locator('details summary').click();
      await page.locator('#count-select').selectOption('131072');
      await page.locator('#steps-select').selectOption('8');
      await page.locator('details summary').click();
    } else if (name === 'heavy-particles') {
      await page.locator('#count-select').selectOption('131072');
      await page.locator('#steps-select').selectOption('8');
    } else {
      const settings = page.locator('details summary');
      if (await settings.count()) await settings.click();
      await page.locator('#grid-select').selectOption('256');
      await page.locator(name === 'magnetic-fluids' ? '#steps-select' : '#pressure-select')
        .selectOption(name === 'magnetic-fluids' ? '10' : '48');
      if (await settings.count()) await settings.click();
    }
    await page.mouse.move(640, 400);
    await page.mouse.down();
    await page.mouse.move(700, 450);
    await page.mouse.up();
    await page.evaluate(() => {
      window.__fawnTest.active = true;
      window.__fawnHidden = true;
      Object.defineProperty(document, 'hidden', { get: () => window.__fawnHidden, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(300);
    const hiddenSubmissions = await page.evaluate(() => window.__fawnTest.submissions.length);
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => window.__fawnTest.submissions.length), hiddenSubmissions,
      `${name} hidden-page scheduling`);
    await page.evaluate(() => {
      window.__fawnHidden = false;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(800);
    assert.ok(await page.evaluate(() => /\d/.test(document.querySelector('#frame').textContent)),
      `${name} resumed metrics`);
    assert.deepEqual(await page.evaluate(() => window.__fawnTest.errors), []);
    result.controlsAndVisibilityPassed = true;
    report.lifecycle.push(result);
    await context.close();
    console.log(`Slow-frame metric, queue bound, reset and resize passed: ${name}`);
  }
  {
    const { context, page } = await open('candidate', 'start', { reducedMotion: 'reduce' });
    await page.evaluate(() => { window.__fawnTest.active = true; });
    await page.waitForTimeout(300);
    assert.equal(await page.locator('#status').textContent(), 'Paused');
    const submissions = await page.evaluate(() => window.__fawnTest.submissions.length);
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => window.__fawnTest.submissions.length), submissions);
    await page.locator('#pause').click();
    await page.waitForTimeout(800);
    assert.ok(await page.evaluate(() => window.__fawnTest.submissions.length > 0));
    assert.deepEqual(await page.evaluate(() => window.__fawnTest.errors), []);
    report.lifecycle.push({ name: 'start', reducedMotionPauseAndResumePassed: true });
    await context.close();
  }
  const cases = [
    { name: 'start', count: '65536', dpr: 2 },
    { name: 'start', count: '1048576', dpr: 2 },
    { name: 'start', count: '4194304', dpr: 2 },
    { name: 'prismatic-fluids', dpr: 2 },
  ];
  for (let cohort = 0; cohort < 2; cohort++) {
    for (const scenario of cases) {
      for (const variant of cohort ? ['candidate', 'baseline'] : ['baseline', 'candidate']) {
        const { context, page } = await open(variant, scenario.name, scenario);
        if (scenario.count) {
          await page.locator('details summary').click();
          await page.locator('#count-select').selectOption(scenario.count);
          await page.locator('details summary').click();
        }
        await page.waitForTimeout(1500);
        await page.evaluate(() => { window.__fawnTest.active = true; });
        await page.waitForTimeout(3500);
        const raw = await page.evaluate(async () => {
          const s = window.__fawnTest;
          s.active = false;
          await s.device.queue.onSubmittedWorkDone();
          return { submissions: s.submissions, completions: s.completions, errors: s.errors,
            maxPending: s.maxPending, adapter: s.adapter,
            canvas: { width: document.querySelector('#view').width, height: document.querySelector('#view').height },
            display: document.querySelector('#frame').textContent };
        });
        assert.deepEqual(raw.errors, []);
        const times = raw.completions;
        const result = { ...scenario, variant, cohort, raw,
          completedFps: 1000 * (times.length - 1) / (times.at(-1) - times[0]),
          completedIntervalMs: statistics(times.slice(1).map((t, i) => t - times[i])) };
        report.performance.push(result);
        await context.close();
        console.log(`${scenario.name}/${scenario.count || 'default'} ${variant}: ${result.completedFps.toFixed(1)} completed fps`);
      }
    }
  }
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.error = error.stack;
  throw error;
} finally {
  writeFileSync(path.join(output, 'results.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
