// Application diagnostics on Chrome's WebGPU provider, not forced-Doe evidence.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import http from 'node:http';
import { resolve } from 'node:path';

const { chromium } = await import(process.env.FAWN_PLAYWRIGHT_MODULE || 'playwright');
const baselineRef = process.env.FAWN_BASELINE_REF || 'b5bcc3c04ac0cc469d6c16dd270e5f0d66e6546e';
const output = resolve(process.env.FAWN_REPORT_DIR || 'bench/out/fawn-demo-pages');
const names = ['heavy-particles', 'magnetic-fluids', 'prismatic-fluids', 'image-lab'];
const sources = {};
const hash = value => createHash('sha256').update(value).digest('hex');
const fixedStyle = '<style>#view{position:fixed!important;inset:0!important;width:640px!important;height:480px!important;z-index:100!important;border:0!important;border-radius:0!important;box-shadow:none!important}.chrome{display:none!important}</style>';
await mkdir(output, { recursive: true });
for (const name of names) {
  const file = `browser/chromium/resources/fawn-${name}.html`;
  sources[name] = {
    baseline: execFileSync('git', ['show', `${baselineRef}:${file}`], { encoding: 'utf8' }),
    candidate: await readFile(file, 'utf8'),
  };
}
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  const [, variant, name] = url.pathname.split('/');
  let source = sources[name]?.[variant];
  if (url.pathname.endsWith('fawn-icon.svg')) {
    response.setHeader('Content-Type', 'image/svg+xml');
    response.end(await readFile('browser/chromium/resources/fawn-icon.svg'));
    return;
  }
  if (!source) { response.writeHead(404).end(); return; }
  if (url.searchParams.has('fixed')) source = source.replace('</head>', fixedStyle + '</head>');
  response.setHeader('Content-Type', 'text/html');
  response.end(source);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-webgpu'] });
const errors = [];
const report = {
  classification: 'Physical Chrome application diagnostics; no Doe-vs-Dawn or portable speed claim',
  observedAt: new Date().toISOString(), baselineRef, browser: browser.version(),
  method: { fixedFrames: 12, absoluteTolerance: 1e-6, canvas: [640, 480],
    readback: 'Instrumented storage buffers add COPY_SRC on both variants; screenshots capture matched canvases',
    optimization: 'Resource and submission counts; no GPU latency comparison' },
  sourceHashes: Object.fromEntries(names.map(name => [name, Object.fromEntries(
    Object.entries(sources[name]).map(([variant, source]) => [variant, hash(source)]))])),
  correctness: [], controls: [], failures: [],
};

function instrument({ fixed = false, unsupported = false } = {}) {
  const s = window.fixture = { clock: 1000, callbacks: new Map(), nextId: 0,
    device: null, buffers: [], errors: [], submissions: 0, compute: 0, dispatches: 0,
    pending: 0, maxPending: 0, modules: 0, storageAllocations: 0, storageWriteBytes: 0,
    uniforms: new Set(), time: null };
  if (fixed) {
    Object.defineProperty(performance, 'now', { value: () => s.clock });
    window.requestAnimationFrame = callback => { s.callbacks.set(++s.nextId, callback); return s.nextId; };
    window.cancelAnimationFrame = id => s.callbacks.delete(id);
  }
  if (unsupported) { Object.defineProperty(navigator, 'gpu', { value: undefined }); return; }
  const request = GPUAdapter.prototype.requestDevice;
  GPUAdapter.prototype.requestDevice = async function(...args) {
    const device = await request.apply(this, args);
    s.device = device;
    s.adapter = { vendor: this.info.vendor, architecture: this.info.architecture,
      device: this.info.device, isFallbackAdapter: this.info.isFallbackAdapter };
    device.addEventListener('uncapturederror', event => s.errors.push(event.error.message));
    const create = device.createBuffer.bind(device);
    device.createBuffer = descriptor => {
      const storage = Boolean(descriptor.usage & GPUBufferUsage.STORAGE);
      const buffer = create(fixed && storage
        ? { ...descriptor, usage: descriptor.usage | GPUBufferUsage.COPY_SRC } : descriptor);
      if (storage) s.storageAllocations += 1;
      if (fixed && storage) {
        const entry = { buffer, size: descriptor.size, destroyed: false };
        const destroy = buffer.destroy.bind(buffer);
        buffer.destroy = () => { entry.destroyed = true; destroy(); };
        s.buffers.push(entry);
      }
      return buffer;
    };
    const module = device.createShaderModule.bind(device);
    device.createShaderModule = (...args) => { s.modules += 1; return module(...args); };
    const compute = GPUCommandEncoder.prototype.beginComputePass;
    if (!window.computeWrapped) {
      window.computeWrapped = true;
      GPUCommandEncoder.prototype.beginComputePass = function(...args) {
        s.compute += 1;
        const pass = compute.apply(this, args);
        const dispatch = pass.dispatchWorkgroups.bind(pass);
        pass.dispatchWorkgroups = (...args) => { s.dispatches += 1; return dispatch(...args); };
        return pass;
      };
    }
    const write = device.queue.writeBuffer.bind(device.queue);
    device.queue.writeBuffer = (buffer, offset, data, ...args) => {
      if (buffer.usage & GPUBufferUsage.STORAGE) s.storageWriteBytes += data.byteLength;
      if (buffer.usage & GPUBufferUsage.UNIFORM) {
        s.uniforms.add(data);
        s.time = data.length === 8 ? data[1] : data[9];
      }
      return write(buffer, offset, data, ...args);
    };
    const submit = device.queue.submit.bind(device.queue);
    const done = device.queue.onSubmittedWorkDone.bind(device.queue);
    device.queue.submit = (...args) => {
      submit(...args);
      s.submissions += 1;
      s.maxPending = Math.max(s.maxPending, ++s.pending);
      done().then(() => { s.pending -= 1; });
    };
    return device;
  };
}
async function open(name, { variant = 'candidate', fixed = false, unsupported = false,
  viewport = { width: 1440, height: 900 }, reducedMotion = 'no-preference' } = {}) {
  const context = await browser.newContext({ viewport, reducedMotion });
  await context.addInitScript(instrument, { fixed, unsupported });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(`${name}: ${error.message}`));
  await page.goto(`${origin}/${variant}/${name}${fixed ? '?fixed' : ''}`);
  await page.waitForFunction(unsupported
    ? () => !document.querySelector('#failure').hidden
    : () => /WebGPU active|Running|Paused/.test(document.querySelector('#status').textContent),
  null, { polling: 50 });
  return { context, page };
}
async function tick(page, frames = 1) {
  await page.evaluate(async frames => {
    const s = window.fixture;
    for (let i = 0; i < frames; i++) {
      s.clock += 1000 / 60;
      const callbacks = [...s.callbacks.values()];
      s.callbacks.clear();
      await Promise.all(callbacks.map(callback => callback(s.clock)));
      await s.device.queue.onSubmittedWorkDone();
    }
  }, frames);
}
async function activity(page) {
  return page.evaluate(() => {
    const s = window.fixture;
    return { submissions: s.submissions, compute: s.compute, time: s.time,
      maxPending: s.maxPending, modules: s.modules, storageAllocations: s.storageAllocations,
      storageWriteBytes: s.storageWriteBytes, uniformObjects: s.uniforms.size,
      errors: s.errors, adapter: s.adapter, dispatches: s.dispatches };
  });
}
async function settled(page) {
  await page.waitForTimeout(200);
  return activity(page);
}
async function layout(page) {
  const boxes = await page.evaluate(() => {
    const box = selector => {
      const r = document.querySelector(selector).getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    };
    return { canvas: box('#view'), header: box('header'), footer: box('.bottom'),
      panel: document.querySelector('.details').open ? box('.details-panel') : null,
      width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth > innerWidth };
  });
  assert.equal(boxes.overflow, false);
  assert.deepEqual(boxes.canvas, { x: 0, y: 0, width: boxes.width, height: boxes.height });
  for (const box of [boxes.header, boxes.footer, boxes.panel].filter(Boolean)) {
    assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= boxes.width
      && box.y + box.height <= boxes.height, JSON.stringify(boxes));
  }
  assert.equal(await page.locator('#search').count(), 0);
  assert.equal(await page.locator('.project-link').getAttribute('href'),
    'https://github.com/doerun/doe/tree/main/browser/chromium');
  return boxes;
}
async function fixedState(name, variant) {
  const { context, page } = await open(name, { variant, fixed: true });
  // Wait for initial ResizeObserver delivery before driving the controlled clock.
  await page.waitForTimeout(100);
  const setup = await activity(page);
  if (name !== 'image-lab') {
    await page.evaluate(() => {
      const s = window.fixture;
      for (const [id, callback] of s.callbacks) {
        if (callback.name !== 'frame') { s.callbacks.delete(id); callback(s.clock); }
      }
    });
    await tick(page, 6);
    await page.mouse.move(200, 180);
    await page.mouse.down();
    await page.mouse.move(350, 220);
    await tick(page, 6);
    await page.mouse.up();
  } else await tick(page);
  const data = await page.evaluate(async () => {
    const s = window.fixture;
    const buffers = [];
    for (const entry of s.buffers.filter(entry => !entry.destroyed)) {
      const read = s.device.createBuffer({ size: entry.size,
        usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
      const encoder = s.device.createCommandEncoder();
      encoder.copyBufferToBuffer(entry.buffer, 0, read, 0, entry.size);
      s.device.queue.submit([encoder.finish()]);
      await read.mapAsync(GPUMapMode.READ);
      buffers.push(Array.from(new Float32Array(read.getMappedRange())));
      read.unmap(); read.destroy();
    }
    return buffers;
  });
  const images = {};
  for (const mode of name === 'image-lab' ? [0, 1, 2, 3] : [null]) {
    if (mode !== null) {
      await page.evaluate(mode => document.querySelector(`[data-mode="${mode}"]`).click(), mode);
      await tick(page);
    }
    const file = `${output}/${name}-${variant}${mode === null ? '' : `-${mode}`}.png`;
    images[mode ?? 'simulation'] = hash(await page.locator('#view').screenshot({ path: file }));
  }
  const after = await activity(page);
  assert.deepEqual(after.errors, []);
  assert.equal(after.adapter.isFallbackAdapter, false, 'Physical adapter required');
  await context.close();
  return { data, images, setup, after };
}

try {
  for (const name of names) {
    const shaderSources = source => [...source.matchAll(/const (\w*(?:WGSL|SHADER)) = `([\s\S]*?)`;/g)]
      .map(match => [match[1], hash(match[2])]);
    assert.deepEqual(shaderSources(sources[name].baseline), shaderSources(sources[name].candidate),
      `${name}: shader algorithms must remain unchanged`);
    const before = await fixedState(name, 'baseline');
    const after = await fixedState(name, 'candidate');
    assert.equal(before.data.length, after.data.length);
    let maxAbsoluteError = 0;
    before.data.forEach((buffer, index) => {
      assert.equal(buffer.length, after.data[index].length);
      buffer.forEach((value, i) => {
        assert.ok(Number.isFinite(value) && Number.isFinite(after.data[index][i]));
        maxAbsoluteError = Math.max(maxAbsoluteError, Math.abs(value - after.data[index][i]));
      });
    });
    assert.ok(maxAbsoluteError <= 1e-6, `${name}: simulation error ${maxAbsoluteError}`);
    assert.deepEqual(before.images, after.images, `${name}: rendered pixels changed`);
    assert.equal(before.after.dispatches, after.after.dispatches);
    if (name === 'heavy-particles') {
      assert.ok(after.setup.storageAllocations < before.setup.storageAllocations);
      assert.ok(after.setup.modules < before.setup.modules);
    } else if (name !== 'image-lab') {
      assert.ok(after.setup.storageWriteBytes < before.setup.storageWriteBytes);
      assert.ok(after.setup.modules < before.setup.modules);
    } else assert.ok(after.after.uniformObjects < before.after.uniformObjects);
    report.correctness.push({ name, shaderHashes: shaderSources(sources[name].candidate),
      maxAbsoluteError, images: after.images, setup: { before: before.setup, after: after.setup },
      uniformObjects: { before: before.after.uniformObjects, after: after.after.uniformObjects } });
    console.log(`Matched GPU state and canvas pixels: ${name}`);
  }
  for (const name of names) {
    for (const [screen, viewport] of [
      ['desktop', { width: 1440, height: 900 }],
      ['mobile', { width: 390, height: 844 }],
      ['small', { width: 320, height: 568 }],
    ]) {
      const { context, page } = await open(name, { viewport });
      await page.waitForFunction(() => /\d/.test(document.querySelector('#frame').textContent));
      await layout(page);
      await page.screenshot({ path: `${output}/${name}-${screen}.png` });
      await page.locator('.details > summary').click();
      const boxes = await layout(page);
      await page.screenshot({ path: `${output}/${name}-${screen}-settings.png` });
      if (name !== 'image-lab') {
        await page.locator('.details > summary').click();
        await page.mouse.move(viewport.width * .3, viewport.height * .35);
        await page.mouse.down();
        await page.mouse.move(viewport.width * .6, viewport.height * .45, { steps: 8 });
        await page.mouse.up();
        await page.locator('#pause').click();
        const frozen = await settled(page);
        await page.waitForTimeout(200);
        const idle = await activity(page);
        assert.equal(idle.submissions, frozen.submissions, 'Paused GPU work stops');
        await page.locator('.details > summary').click();
        await page.locator(name === 'heavy-particles' ? '#count-select' : '#grid-select')
          .selectOption(name === 'heavy-particles' ? '32768' : name === 'magnetic-fluids' ? '256' : '192');
        await page.locator(name === 'prismatic-fluids' ? '#pressure-select' : '#steps-select')
          .selectOption(name === 'prismatic-fluids' ? '48' : name === 'heavy-particles' ? '8' : '10');
        await page.locator('.details > summary').click();
        await page.locator('#restart').click();
        const reset = await settled(page);
        assert.ok(reset.submissions > frozen.submissions);
        assert.equal(reset.compute, frozen.compute, 'Paused reset skips compute');
        assert.equal(reset.time, frozen.time, 'Paused redraw freezes shader time');
        await page.setViewportSize({ width: viewport.width, height: viewport.height - 40 });
        const resized = await settled(page);
        assert.ok(resized.submissions > reset.submissions);
        assert.equal(resized.compute, reset.compute);
        await page.locator('#pause').click();
        await page.waitForFunction(previous => window.fixture.compute > previous, resized.compute);
        assert.ok((await activity(page)).maxPending <= 2);
      } else {
        for (const mode of [0, 1, 2, 3]) {
          await page.locator(`[data-mode="${mode}"]`).click();
          await page.waitForFunction(() => window.fixture.pending === 0);
          assert.equal(await page.locator(`[data-mode="${mode}"]`).getAttribute('aria-pressed'), 'true');
        }
        const initial = await settled(page);
        await page.evaluate(() => {
          for (let i = 0; i < 100; i++) {
            const input = document.querySelector('#strength');
            input.value = String(i);
            input.dispatchEvent(new Event('input', { bubbles: true }));
          }
        });
        const burst = await settled(page);
        assert.equal(burst.submissions - initial.submissions, 1, 'Image updates coalesce');
        assert.equal(burst.uniformObjects, 1, 'Uniform staging is reused');
        assert.equal(burst.maxPending, 1, 'Only one image submission in flight');
        assert.equal(await page.locator('#strength-value').textContent(), '99%');
        await page.waitForTimeout(200);
        assert.equal((await activity(page)).submissions, burst.submissions, 'Static image consumes no idle frames');
        await page.locator('.details > summary').click();
        await page.locator('#restart').click();
        assert.equal(await page.locator('#strength').inputValue(), '70');
        assert.equal(await page.locator('#split').inputValue(), '50');
      }
      assert.deepEqual((await activity(page)).errors, []);
      report.controls.push({ name, screen, boxes, activity: await settled(page) });
      await context.close();
    }
    if (name !== 'image-lab') {
      const { context, page } = await open(name, { reducedMotion: 'reduce' });
      const initial = await settled(page);
      assert.equal(initial.compute, 0);
      assert.ok(initial.submissions > 0);
      assert.equal(await page.locator('#pause').textContent(), 'Resume');
      await page.locator('#pause').click();
      await page.waitForFunction(() => window.fixture.compute > 0);
      report.controls.push({ name, reducedMotion: 'initial render without simulation; resume works' });
      await context.close();
    }
    const unsupported = await open(name, { unsupported: true });
    assert.equal(await unsupported.page.locator('#failure').textContent(), 'WebGPU unavailable');
    assert.equal(await unsupported.page.locator('#restart').isDisabled(), true);
    await unsupported.context.close();
    const lost = await open(name);
    await lost.page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const hidden = await settled(lost.page);
    await lost.page.waitForTimeout(200);
    assert.equal((await activity(lost.page)).submissions, hidden.submissions, 'Hidden page stops GPU work');
    await lost.page.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await lost.page.waitForFunction(previous => window.fixture.submissions > previous, hidden.submissions);
    await lost.page.evaluate(() => window.fixture.device.destroy());
    await lost.page.waitForFunction(() => !document.querySelector('#failure').hidden);
    assert.equal(await lost.page.locator('#restart').isDisabled(), true);
    const stopped = await settled(lost.page);
    await lost.page.waitForTimeout(200);
    assert.equal((await activity(lost.page)).submissions, stopped.submissions);
    await lost.context.close();
    report.failures.push({ name, unsupported: 'visible error; controls disabled', deviceLost: 'work stops; visible error; controls disabled', hidden: 'scheduling stops; visible redraw resumes' });
    console.log(`Fullscreen layout, controls, and device lifecycle: ${name}`);
  }
  const { context, page } = await open('image-lab');
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 32; canvas.height = 24;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#e13a62'; ctx.fillRect(0, 0, 32, 24);
    return canvas.toDataURL().split(',')[1];
  });
  await page.locator('#file').setInputFiles({ name: 'sample.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await page.waitForFunction(() => document.querySelector('#image-info').textContent.startsWith('32 × 24'));
  await page.locator('#file').setInputFiles({ name: 'invalid.png', mimeType: 'image/png', buffer: Buffer.from('invalid image') });
  await page.waitForFunction(() => document.querySelector('#image-info').textContent.startsWith('Image error:'));
  assert.equal(await page.locator('#failure').isHidden(), true, 'Decode failure preserves working image');
  await page.locator('#restart').click();
  await page.waitForFunction(() => document.querySelector('#image-info').textContent.startsWith('1024 × 768'));
  await page.locator('#file').setInputFiles({ name: 'invalid.png', mimeType: 'image/png', buffer: Buffer.from('invalid image') });
  await page.waitForFunction(() => document.querySelector('#image-info').textContent.startsWith('Image error:'));
  await page.locator('#restart').click();
  assert.match(await page.locator('#image-info').textContent(), /^1024 × 768/, 'Reset clears sample upload errors');
  await page.evaluate(() => {
    const decode = window.createImageBitmap;
    window.createImageBitmap = async (...args) => {
      const image = await decode(...args);
      await new Promise(resolve => { window.releaseDecode = resolve; });
      return image;
    };
  });
  await page.locator('#file').setInputFiles({ name: 'delayed.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await page.waitForFunction(() => Boolean(window.releaseDecode));
  await page.locator('#restart').click();
  await page.evaluate(() => window.releaseDecode());
  await page.waitForTimeout(200);
  assert.match(await page.locator('#image-info').textContent(), /^1024 × 768/, 'Reset cancels pending upload');
  assert.deepEqual((await settled(page)).errors, []);
  report.controls.push({ name: 'image-lab', upload: 'PNG upload, invalid-file recovery, sample reset, and late-decode cancellation passed' });
  await context.close();
  for (const name of names.filter(name => name !== 'image-lab')) {
    const tiny = await open(name, { viewport: { width: 300, height: 150 }, reducedMotion: 'reduce' });
    const initial = await settled(tiny.page);
    assert.ok(initial.submissions > 0, 'Default-sized canvas is configured');
    assert.deepEqual(initial.errors, []);
    report.controls.push({ name, canvasDefaultDimensions: 'configured and rendered' });
    await tiny.context.close();
  }
  assert.deepEqual(errors, []);
  report.errors = errors;
  await writeFile(`${output}/results.json`, JSON.stringify(report, null, 2) + '\n');
  console.log(`Fawn standalone page checks passed: ${output}`);
} catch (error) {
  report.failure = String(error.stack || error);
  report.errors = errors;
  await writeFile(`${output}/failure.json`, JSON.stringify(report, null, 2) + '\n');
  throw error;
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
