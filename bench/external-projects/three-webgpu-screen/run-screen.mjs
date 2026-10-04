// Existing upstream application; observer hooks only, no shader or graph rewrite.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const project = dirname(fileURLToPath(import.meta.url));
const root = resolve(project, '../../..');
const plan = JSON.parse(await readFile(resolve(project, 'screen.json')));
const scratch = resolve(root, plan.scratch);
const cache = resolve(scratch, 'upstream');
const captured = resolve(scratch, 'captured');
const { chromium } = await import(process.env.DOE_PLAYWRIGHT_MODULE ?? 'playwright');
await mkdir(captured, { recursive: true });
const tree = await (await fetch(`https://api.github.com/repos/mrdoob/three.js/git/trees/${plan.upstreamCommit}?recursive=1`)).json();
assert.equal(tree.truncated, false);
const files = new Map(tree.tree.filter((entry) => entry.type === 'blob').map((entry) => [entry.path, entry.sha]));
const acquired = new Map();
async function acquire(path) {
  assert(files.has(path), `Unknown pinned upstream path: ${path}`);
  const local = resolve(cache, path);
  assert(local.startsWith(cache + sep));
  let bytes;
  try { bytes = await readFile(local); } catch {
    const response = await fetch(`https://raw.githubusercontent.com/mrdoob/three.js/${plan.upstreamCommit}/${path}`);
    assert(response.ok, `${path}: HTTP ${response.status}`);
    bytes = Buffer.from(await response.arrayBuffer());
    await mkdir(dirname(local), { recursive: true });
    await writeFile(local, bytes);
  }
  const gitBlob = createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
  assert.equal(gitBlob, files.get(path), `Upstream bytes changed: ${path}`);
  acquired.set(path, { path, gitBlob, sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length });
  return bytes;
}
const application = (await acquire(plan.application)).toString();
const exposure = `\nwindow.threeScreen = { get renderer() { return renderer; }, get pipeline() { return renderPipeline; }, get camera() { return camera; } };\n`;
assert.equal(application.split('</script>').length, 3);
assert(application.includes('const scattering = uniform( 2 );'));
const exposed = application.replace('const scattering = uniform( 2 );', 'const scattering = uniform( 2 ); window.threeScreenScattering = scattering;');
const last = exposed.lastIndexOf('</script>');
const instrumentedHTML = exposed.slice(0, last) + exposure + exposed.slice(last);
await writeFile(resolve(captured, 'application-original.html'), application);
await writeFile(resolve(captured, 'application-observed.html'), instrumentedHTML);
await acquire('LICENSE');
const server = createServer(async (request, response) => {
  try {
    const path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname).slice(1);
    if (path === 'favicon.ico') { response.writeHead(204); response.end(); return; }
    const bytes = path === plan.application ? Buffer.from(instrumentedHTML) : await acquire(path);
    const type = path.endsWith('.js') ? 'text/javascript' : path.endsWith('.html') ? 'text/html'
      : path.endsWith('.css') ? 'text/css' : 'application/octet-stream';
    response.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });response.end(bytes);
  } catch (error) { response.writeHead(404);response.end(String(error)); }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const url = `http://127.0.0.1:${server.address().port}/${plan.application}`;
await writeFile(resolve(captured, 'frozen-plan.json'), JSON.stringify({ plan,
  runnerSha256: createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex') }, null, 2));
try {
  for (const capture of [true, false]) {
    const runs = capture ? 1 : plan.processes;
    for (let run = 0; run < runs; run++) {
      const browser = await chromium.launch({ executablePath: plan.browser, headless: false,
        args: plan.browserArgs, env: { ...process.env, ...(capture ? plan.driverCaptureEnv : {}) } });
      try {
        const page = await browser.newPage({ viewport: plan.viewport, deviceScaleFactor: plan.deviceScaleFactor });
        const errors = [];
        page.on('pageerror', (error) => errors.push(error.message));
        page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
        await page.addInitScript(() => {
          window.shaderCapture = [];
          const requestDevice = GPUAdapter.prototype.requestDevice;
          GPUAdapter.prototype.requestDevice = function (descriptor) {
            window.adapterIdentity = { vendor: this.info.vendor, architecture: this.info.architecture,
              device: this.info.device, description: this.info.description };
            return requestDevice.call(this, descriptor);
          };
          const create = GPUDevice.prototype.createShaderModule;
          GPUDevice.prototype.createShaderModule = function (descriptor) {
            window.shaderCapture.push({ label: descriptor.label ?? '', code: descriptor.code });
            return create.call(this, descriptor);
          };
        });
        await page.goto(url);
        await page.waitForFunction(() => window.threeScreen?.renderer?.hasInitialized(), { timeout: 120000 });
        await page.evaluate(async () => {
          const renderer = window.threeScreen.renderer;
          renderer.setAnimationLoop(null);
          await renderer.backend.device.queue.onSubmittedWorkDone();
        });
        const result = await page.evaluate(async ({ plan, capture, run }) => {
          const { renderer, pipeline, camera } = window.threeScreen;
          const backend = renderer.backend;
          const device = backend.device;
          const originalTimestamp = backend.initTimestampQuery.bind(backend);
          const contexts = new Map();
          let currentLabel = "";
          const originalBegin = backend.beginRender.bind(backend);
          backend.beginRender = function (context) {
            currentLabel = context.renderTarget?.texture?.name || "scene/composite";
            return originalBegin(context);
          };
          backend.initTimestampQuery = function (type, uid, descriptor) {
            contexts.set(uid, { type, label: currentLabel });
            return originalTimestamp(type, uid, descriptor);
          };
          backend.trackTimestamp = capture;
          const scattering = window.threeScreenScattering;
          const rows = [];
          for (let index = 0; index < plan.warmupFrames; index++) {
            pipeline.render(); await device.queue.onSubmittedWorkDone();
            if (capture) await renderer.resolveTimestampsAsync();
          }
          for (const value of capture ? plan.scattering : [plan.scattering[0]]) {
          scattering.value = value;
          for (const labels of plan.trialLabels.map((_, index) => plan.trialLabels[(index + run) % plan.trialLabels.length])) {
            for (const label of labels) {
              const start = performance.now();pipeline.render();
              const recordMs = performance.now() - start;
              await device.queue.onSubmittedWorkDone();
              const completedMs = performance.now() - start;
              let timestamps = [];
              if (capture) {
                await renderer.resolveTimestampsAsync();
                timestamps = [...backend.timestampQueryPool.render.timestamps].map(([uid, durationMs]) => ({ uid, durationMs, context: contexts.get(uid) }));
              }
              rows.push({ label, scattering: value, recordMs, completedMs, timestamps });
            }
          }
          }
          return { rows, shaders: window.shaderCapture, errors: [], userAgent: navigator.userAgent,
            timestampEnabled: backend.trackTimestamp, camera: camera.matrixWorld.elements.slice(),
            info: { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles },
            adapter: window.adapterIdentity,
            backend: backend.isWebGPUBackend === true };
        }, { plan, capture, run });
        assert.equal(result.backend, true);
        if (capture) assert(result.rows.every((row) => row.timestamps.length > 0), "Missing pass timestamp evidence");
        else assert.equal(result.timestampEnabled, false);
        assert.equal(errors.length, 0, errors.join('\n'));
        await writeFile(resolve(captured, `${capture ? 'profile' : 'aa'}-${run}.json`), JSON.stringify({
          browserVersion: browser.version(), ...result }, null, 2));
        if (capture) {
          for (let index = 0; index < result.shaders.length; index++) await writeFile(resolve(captured,
            `shader-${index}.wgsl`), result.shaders[index].code);
          await page.screenshot({ path: resolve(captured, 'application.png') });
        }
        console.log(`screen complete: ${capture ? 'profile' : 'aa'} ${run}`);
      } finally { await browser.close(); }
    }
  }
} catch (error) {
  await writeFile(resolve(captured, 'failure.json'), JSON.stringify({ error: error.message, stack: error.stack }, null, 2));
  throw error;
} finally {
  await writeFile(resolve(captured, 'dependencies.json'), JSON.stringify({ upstreamCommit: plan.upstreamCommit,
    acquired: [...acquired.values()] }, null, 2));
  await new Promise((done) => server.close(done));
}
