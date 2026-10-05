import assert from 'node:assert/strict';
import http from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const { chromium } = await import(process.env.FAWN_PLAYWRIGHT_MODULE || 'playwright');
const resources = new URL('../resources/', import.meta.url);
const output = resolve(process.env.FAWN_UI_OUTPUT || 'bench/out/fawn-prismatic-ui');
await mkdir(output, { recursive: true });
const server = http.createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://localhost').pathname;
    const file = new URL('.' + path, resources);
    if (!file.href.startsWith(resources.href)) throw new Error('Outside resources');
    response.setHeader('Content-Type', path.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
    response.end(await readFile(file));
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = process.env.FAWN_UI_ORIGIN || `http://127.0.0.1:${server.address().port}`;
const route = origin + '/fawn-prismatic-fluids.html';
const browser = await chromium.launch({
  channel: 'chrome', headless: true, args: ['--enable-unsafe-webgpu'],
});
const results = [];
const errors = [];
async function openPage(options = {}) {
  const context = await browser.newContext(options);
  await context.addInitScript(() => {
    window.gpuActivity = { submissions: 0, computePasses: 0, simulationTime: null };
    if (!navigator.gpu) return;
    const submit = GPUQueue.prototype.submit;
    GPUQueue.prototype.submit = function (...args) {
      window.gpuActivity.submissions += 1;
      return submit.apply(this, args);
    };
    const compute = GPUCommandEncoder.prototype.beginComputePass;
    GPUCommandEncoder.prototype.beginComputePass = function (...args) {
      window.gpuActivity.computePasses += 1;
      return compute.apply(this, args);
    };
    const write = GPUQueue.prototype.writeBuffer;
    GPUQueue.prototype.writeBuffer = function (buffer, offset, data, ...args) {
      if (data instanceof Float32Array && data.length === 16) {
        window.gpuActivity.simulationTime = data[9];
      }
      return write.call(this, buffer, offset, data, ...args);
    };
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto(route);
  await page.waitForFunction(() => !document.querySelector('#pause').disabled);
  return { context, page };
}
async function settledActivity(page) {
  await page.waitForTimeout(150);
  return page.evaluate(() => ({ ...window.gpuActivity }));
}
async function layout(page) {
  const boxes = await page.evaluate(() => {
    const box = selector => {
      const r = document.querySelector(selector).getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    };
    return { canvas: box('#view'), header: box('header'), footer: box('.bottom'),
      viewport: { width: innerWidth, height: innerHeight },
      overflow: document.documentElement.scrollWidth > innerWidth };
  });
  assert.equal(boxes.overflow, false);
  assert.deepEqual(boxes.canvas, { x: 0, y: 0, ...boxes.viewport });
  for (const box of [boxes.header, boxes.footer]) {
    assert.ok(box.x >= 0 && box.y >= 0);
    assert.ok(box.x + box.width <= boxes.viewport.width);
    assert.ok(box.y + box.height <= boxes.viewport.height);
  }
  return boxes;
}
try {
  for (const [name, viewport] of [
    ['desktop', { width: 1440, height: 900 }],
    ['mobile', { width: 390, height: 844 }],
  ]) {
    const { context, page } = await openPage({ viewport });
    await page.waitForFunction(() => /\d/.test(document.querySelector('#frame').textContent));
    const boxes = await layout(page);
    await page.mouse.move(viewport.width * .35, viewport.height * .4);
    await page.mouse.down();
    await page.mouse.move(viewport.width * .65, viewport.height * .55, { steps: 16 });
    await page.mouse.up();
    await page.locator('#pause').click();
    assert.equal(await page.locator('#status').textContent(), 'Paused');
    const frozen = await settledActivity(page);
    await page.waitForTimeout(200);
    assert.deepEqual(await settledActivity(page), frozen, 'paused GPU work must stop');
    await page.screenshot({ path: `${output}/${name}.png` });
    await page.locator('summary').click();
    const panel = await page.locator('.details-panel').boundingBox();
    assert.ok(panel.x >= 0 && panel.y >= 0);
    assert.ok(panel.x + panel.width <= viewport.width);
    assert.ok(panel.y + panel.height <= viewport.height);
    await page.locator('#grid-select').selectOption('192');
    await page.locator('#pressure-select').selectOption('48');
    assert.match(await page.locator('#load').textContent(), /192² selected · 96² sim · 48/);
    const rebuilt = await settledActivity(page);
    assert.equal(rebuilt.computePasses, frozen.computePasses, 'paused grid rebuild skips simulation');
    assert.equal(rebuilt.simulationTime, frozen.simulationTime, 'paused redraw freezes shader time');
    await page.screenshot({ path: `${output}/${name}-settings.png` });
    await page.locator('summary').click();
    await page.locator('#restart').click();
    const reset = await settledActivity(page);
    assert.ok(reset.submissions > rebuilt.submissions, 'paused reset redraws');
    assert.equal(reset.computePasses, rebuilt.computePasses);
    await page.setViewportSize({ width: viewport.width, height: viewport.height - 80 });
    const resized = await settledActivity(page);
    assert.ok(resized.submissions > reset.submissions, 'paused resize redraws');
    assert.equal(resized.computePasses, reset.computePasses);
    await layout(page);
    await page.locator('#pause').click();
    await page.waitForFunction(previous => window.gpuActivity.computePasses > previous,
      resized.computePasses);
    await page.waitForFunction(() => /\d/.test(document.querySelector('#frame').textContent));
    assert.equal(await page.locator('#status').textContent(), 'WebGPU active');
    results.push({ name, boxes, frozen, rebuilt, reset, resized, controls: 'passed' });
    await context.close();
  }
  const { context, page } = await openPage({ reducedMotion: 'reduce' });
  assert.equal(await page.locator('#pause').textContent(), 'Resume');
  const initial = await settledActivity(page);
  assert.equal(initial.computePasses, 0, 'reduced motion starts without simulation');
  assert.ok(initial.submissions > 0, 'reduced motion still renders the initial field');
  await page.locator('#pause').click();
  await page.waitForFunction(() => window.gpuActivity.computePasses > 0);
  results.push({ reducedMotion: 'passed' });
  await context.close();
  const unsupported = await browser.newContext();
  await unsupported.addInitScript(() => Object.defineProperty(navigator, 'gpu', { value: undefined }));
  const failurePage = await unsupported.newPage();
  await failurePage.goto(route);
  await failurePage.waitForFunction(() => !document.querySelector('#failure').hidden);
  assert.equal(await failurePage.locator('#failure').textContent(), 'WebGPU unavailable');
  assert.equal(await failurePage.locator('#pause').isDisabled(), true);
  results.push({ unsupportedGpu: 'visible error; disabled controls' });
  await unsupported.close();
  assert.deepEqual(errors, []);
  await writeFile(`${output}/results.json`, JSON.stringify({ origin, results, errors }, null, 2) + '\n');
  console.log(`Prismatic desktop/mobile layout, paused GPU work, reset, settings, resize, reduced motion, and error UI passed: ${output}`);
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
