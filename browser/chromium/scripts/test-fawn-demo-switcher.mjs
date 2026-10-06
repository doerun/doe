// Local application navigation and RAF-clock regression checks on physical Chrome.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import http from 'node:http';
import { resolve } from 'node:path';

const { chromium } = await import(process.env.FAWN_PLAYWRIGHT_MODULE || 'playwright');
const output = resolve(process.env.FAWN_REPORT_DIR || 'bench/out/fawn-demo-switcher');
const baselineRef = 'b599d2e3a8ad09fa3aff66a2d08d3fa1515647fb';
const names = ['start', 'heavy-particles', 'magnetic-fluids', 'prismatic-fluids'];
const sources = {};
const hash = source => createHash('sha256').update(source).digest('hex');
await mkdir(output, { recursive: true });
for (const name of names) {
  const path = `browser/chromium/resources/fawn-${name}.html`;
  sources[name] = { candidate: await readFile(path, 'utf8'),
    baseline: execFileSync('git', ['show', `${baselineRef}:${path}`], { encoding: 'utf8' }) };
}
const server = http.createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname;
  const [, variant, filename] = path.split('/');
  if (filename === 'fawn-icon.svg') {
    response.setHeader('Content-Type', 'image/svg+xml');
    response.end(await readFile('browser/chromium/resources/fawn-icon.svg')); return;
  }
  const name = filename?.replace(/^fawn-/, '').replace(/\.html$/, '');
  const source = sources[name]?.[variant];
  if (!source) { response.writeHead(404).end(); return; }
  response.setHeader('Content-Type', 'text/html'); response.end(source);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-webgpu'] });
const errors = [];
const report = { classification: 'Chrome application diagnostics; no Doe-vs-Dawn performance claim',
  observedAt: new Date().toISOString(), browser: browser.version(), baselineRef,
  sourceHashes: Object.fromEntries(names.map(name => [name, Object.fromEntries(
    Object.entries(sources[name]).map(([variant, source]) => [variant, hash(source)]))])),
  navigation: [], clocks: [], cycle: null };
function instrument({ fixed = false } = {}) {
  const s = window.switcherTest = { callbacks: new Map(), id: 0, device: null,
    uniforms: [], fields: [], wrapped: false, errors: [] };
  if (fixed) {
    Object.defineProperty(performance, 'now', { value: () => 1000 });
    requestAnimationFrame = callback => { s.callbacks.set(++s.id, callback); return s.id; };
    cancelAnimationFrame = id => s.callbacks.delete(id);
  }
  const request = GPUAdapter.prototype.requestDevice;
  GPUAdapter.prototype.requestDevice = async function (...args) {
    const device = await request.apply(this, args);
    s.device = device;
    s.adapter = { vendor: this.info.vendor, architecture: this.info.architecture,
      isFallbackAdapter: this.info.isFallbackAdapter };
    device.addEventListener('uncapturederror', event => s.errors.push(event.error.message));
    const write = device.queue.writeBuffer.bind(device.queue);
    device.queue.writeBuffer = (buffer, offset, data, ...args) => {
      if (buffer.usage & GPUBufferUsage.UNIFORM) {
        const dt = data.length === 8 ? data[0] : data[8];
        const phase = location.pathname.endsWith('fawn-start.html') ? data[7] : null;
        if (fixed) s.uniforms.push({ dt, phase });
        if (phase !== null) {
          const field = Math.floor(phase) % 3;
          if (s.fields.at(-1) !== field) {
            if (field === 0 && s.fields.includes(2)) s.wrapped = true;
            s.fields.push(field);
          }
        }
      }
      return write(buffer, offset, data, ...args);
    };
    return device;
  };
}
async function open(name, { variant = 'candidate', fixed = false,
  viewport = { width: 1440, height: 900 } } = {}) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript(instrument, { fixed });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/${variant}/fawn-${name}.html`);
  await page.waitForFunction(() => /WebGPU active/.test(document.querySelector('#status').textContent),
    null, { polling: 50 });
  return { context, page };
}
try {
  for (const name of names.filter(name => name !== 'image-lab')) {
    const results = {};
    for (const variant of ['baseline', 'candidate']) {
      const { context, page } = await open(name, { variant, fixed: true });
      const result = await page.evaluate(async () => {
        const s = window.switcherTest;
        const callbacks = [...s.callbacks.values()]; s.callbacks.clear();
        await Promise.all(callbacks.map(callback => callback(990)));
        await s.device.queue.onSubmittedWorkDone();
        return { uniforms: s.uniforms, errors: s.errors, adapter: s.adapter };
      });
      assert.ok(result.uniforms.length > 0);
      assert.equal(result.adapter.isFallbackAdapter, false);
      assert.deepEqual(result.errors, []);
      if (variant === 'baseline') assert.ok(result.uniforms.some(row => row.dt < 0));
      else assert.ok(result.uniforms.every(row => row.dt >= 0));
      if (name === 'start') {
        assert.ok(variant === 'baseline'
          ? result.uniforms.some(row => row.phase < 0) : result.uniforms.every(row => row.phase >= 0));
      }
      results[variant] = result;
      await context.close();
    }
    report.clocks.push({ name, rafTimestamp: 990, initializationClock: 1000, ...results });
  }
  for (const [screen, viewport] of [
    ['desktop', { width: 1440, height: 900 }],
    ['mobile', { width: 390, height: 844 }],
    ['small', { width: 320, height: 568 }],
  ]) {
    for (const [index, name] of names.entries()) {
      const { context, page } = await open(name, { viewport });
      const summary = page.locator('.demo-switcher > summary');
      const menu = page.locator('.demo-menu');
      assert.equal(await menu.isVisible(), false);
      await summary.focus(); await page.keyboard.press('Enter');
      assert.equal(await menu.isVisible(), true);
      const box = await menu.boundingBox();
      assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width
        && box.y + box.height <= viewport.height);
      assert.equal(await menu.locator('a').count(), names.length);
      assert.equal(await menu.locator('[aria-current="page"]').getAttribute('href'), `./fawn-${name}.html`);
      await page.keyboard.press('Escape');
      assert.equal(await menu.isVisible(), false);
      assert.equal(await summary.evaluate(element => element === document.activeElement), true);
      await summary.click(); await page.mouse.click(viewport.width / 2, viewport.height / 2);
      assert.equal(await menu.isVisible(), false, 'Canvas interaction dismisses menu');
      await summary.click(); await page.locator('.details > summary').click();
      assert.equal(await menu.isVisible(), false, 'Settings interaction dismisses menu');
      assert.equal(await page.locator('.details').getAttribute('open'), '');
      await page.locator('.details > summary').click();
      await summary.click();
      if (name === 'start') await page.screenshot({ path: `${output}/${screen}.png` });
      const next = names[(index + 1) % names.length];
      await menu.locator(`a[href="./fawn-${next}.html"]`).click();
      await page.waitForURL(`**/fawn-${next}.html`);
      await page.waitForFunction(() => /WebGPU active/.test(document.querySelector('#status').textContent));
      assert.equal(await page.locator('.demo-menu [aria-current="page"]').getAttribute('href'), `./fawn-${next}.html`);
      assert.deepEqual(await page.evaluate(() => window.switcherTest.errors), []);
      report.navigation.push({ name, next, screen, menuBox: box,
        keyboard: 'open and Escape restore focus', dismissal: 'outside canvas and Settings', gpuStartup: 'passed' });
      await context.close();
    }
  }
  const { context, page } = await open('start');
  await page.waitForFunction(() => window.switcherTest.wrapped, null, { timeout: 60000, polling: 250 });
  report.cycle = await page.evaluate(() => ({ fields: window.switcherTest.fields,
    errors: window.switcherTest.errors, adapter: window.switcherTest.adapter }));
  assert.deepEqual(report.cycle.fields.slice(0, 4), [0, 1, 2, 0]);
  assert.deepEqual(report.cycle.errors, []);
  await context.close();
  assert.deepEqual(errors, []);
  report.passed = true;
  console.log('Demo switching, keyboard dismissal, desktop/mobile layout, nonnegative RAF time, and real particle cycle passed');
} catch (error) {
  report.passed = false; report.error = error.stack; throw error;
} finally {
  report.errors = errors;
  await writeFile(`${output}/results.json`, JSON.stringify(report, null, 2) + '\n');
  await browser.close(); await new Promise(resolve => server.close(resolve));
}
